"""Guideline Adherence - Services Layer

Orchestrates the three monitoring modes:
1. Trigger monitoring - Poll FHIR for new diagnoses matching bundle triggers
2. Episode monitoring - Check active episodes for deadline violations
3. Adherence monitoring - Run element checkers, update adherence percentages

Adapted from Flask bundle_monitor.py, episode_monitor.py, and monitor.py.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity

from .bundles import get_bundle, get_enabled_bundles, identify_applicable_bundles
from .fhir_client import GuidelineAdherenceFHIRClient, get_fhir_client
from .logic.checkers.base import CheckResult
from .logic.checkers.lab_checker import LabChecker
from .logic.checkers.medication_checker import MedicationChecker
from .logic.checkers.note_checker import NoteChecker
from .logic.checkers.febrile_infant_checker import FebrileInfantChecker
from .logic.checkers.hsv_checker import HSVChecker
from .logic.checkers.cdiff_testing_checker import CDiffTestingChecker
from .models import (
    BundleEpisode, ElementResult, EpisodeAssessment, EpisodeReview,
    MonitorState, EpisodeStatus, ElementCheckStatus, AdherenceLevel,
)

logger = logging.getLogger(__name__)


class GuidelineAdherenceService:
    """Orchestrator for guideline adherence monitoring."""

    def __init__(self, fhir_client=None):
        self.fhir_client = fhir_client or get_fhir_client()

        # Initialize checkers
        self.lab_checker = LabChecker(fhir_client=self.fhir_client)
        self.medication_checker = MedicationChecker(fhir_client=self.fhir_client)
        self.note_checker = NoteChecker(fhir_client=self.fhir_client)
        self.febrile_infant_checker = FebrileInfantChecker(
            fhir_client=self.fhir_client, use_nlp=True, use_triage=True,
        )
        self.hsv_checker = HSVChecker(fhir_client=self.fhir_client)
        self.cdiff_checker = CDiffTestingChecker(
            fhir_client=self.fhir_client, use_nlp=True,
        )

        # Checker routing by checker_type
        self._checkers = {
            'lab': self.lab_checker,
            'medication': self.medication_checker,
            'note': self.note_checker,
            'febrile_infant': self.febrile_infant_checker,
            'hsv': self.hsv_checker,
            'cdiff': self.cdiff_checker,
        }

    # =========================================================================
    # Mode 1: Trigger Monitoring
    # =========================================================================

    def check_triggers(self, hours_back=24):
        """Poll FHIR for new diagnoses matching bundle triggers, create episodes.

        Returns list of newly created BundleEpisode objects.
        """
        new_episodes = []
        bundles = get_enabled_bundles()

        for bundle in bundles:
            for trigger in bundle.trigger_criteria:
                try:
                    patients = self._find_triggered_patients(trigger, hours_back)
                    for patient_data in patients:
                        episode = self._create_episode_if_new(bundle, trigger, patient_data)
                        if episode:
                            new_episodes.append(episode)
                except Exception as e:
                    logger.error(f"Error checking triggers for {bundle.bundle_id}: {e}")

        # Update monitor state
        self._update_monitor_state('trigger', len(new_episodes))

        logger.info(f"Trigger check complete: {len(new_episodes)} new episodes created")
        return new_episodes

    def _find_triggered_patients(self, trigger, hours_back):
        """Find patients matching a trigger criteria."""
        patients = []

        if trigger.icd10_prefixes:
            found = self.fhir_client.get_patients_by_condition(
                icd10_prefixes=trigger.icd10_prefixes,
                min_age_days=trigger.min_age_days,
                max_age_days=trigger.max_age_days,
            )
            patients.extend(found)

        return patients

    @transaction.atomic
    def _create_episode_if_new(self, bundle, trigger, patient_data):
        """Create a new episode if one doesn't already exist for this trigger."""
        patient_id = patient_data['patient_id']
        encounter_id = patient_data.get('encounter_id', '')
        trigger_time = patient_data.get('onset_time') or timezone.now()

        # Dedup: check for existing episode
        existing = BundleEpisode.objects.filter(
            patient_id=patient_id,
            encounter_id=encounter_id,
            bundle_id=bundle.bundle_id,
            trigger_time=trigger_time,
        ).exists()

        if existing:
            return None

        # Get patient info
        patient_info = self.fhir_client.get_patient(patient_id)
        if not patient_info:
            logger.warning(f"Could not get patient info for {patient_id}")
            return None

        age_days = patient_data.get('age_days') or patient_info.get('age_days')

        episode = BundleEpisode.objects.create(
            patient_id=patient_id,
            patient_mrn=patient_info.get('mrn', ''),
            patient_name=patient_info.get('name', ''),
            encounter_id=encounter_id,
            bundle_id=bundle.bundle_id,
            bundle_name=bundle.name,
            trigger_type=trigger.trigger_type,
            trigger_code=patient_data.get('condition_code', ''),
            trigger_description=trigger.description,
            trigger_time=trigger_time,
            patient_age_days=age_days,
            patient_age_months=age_days / 30.44 if age_days else None,
            status=EpisodeStatus.ACTIVE,
            elements_total=len(bundle.elements),
        )

        # Create element results for each bundle element
        for elem in bundle.elements:
            ElementResult.objects.create(
                episode=episode,
                element_id=elem.element_id,
                element_name=elem.name,
                element_description=elem.description,
                status=ElementCheckStatus.PENDING,
                required=elem.required,
                time_window_hours=elem.time_window_hours,
                deadline=trigger_time + timedelta(hours=elem.time_window_hours) if elem.time_window_hours else None,
            )

        logger.info(
            f"Created episode {episode.id} for {bundle.bundle_id} "
            f"patient={patient_info.get('name')} MRN={patient_info.get('mrn')}"
        )
        return episode

    # =========================================================================
    # Mode 2: Episode Monitoring
    # =========================================================================

    def check_episodes(self, dry_run=False):
        """Check active episodes for element deadline violations, create alerts.

        Returns list of alerts created.
        """
        alerts_created = []
        active_episodes = BundleEpisode.objects.filter(
            status=EpisodeStatus.ACTIVE,
        ).prefetch_related('element_results')

        for episode in active_episodes:
            try:
                episode_alerts = self._check_episode_deadlines(episode, dry_run)
                alerts_created.extend(episode_alerts)
            except Exception as e:
                logger.error(f"Error checking episode {episode.id}: {e}")

        self._update_monitor_state('episode', len(alerts_created))

        logger.info(f"Episode check complete: {len(alerts_created)} alerts created")
        return alerts_created

    def _check_episode_deadlines(self, episode, dry_run=False):
        """Check an episode's elements for deadline violations."""
        alerts = []
        now = timezone.now()

        for element in episode.element_results.filter(status=ElementCheckStatus.PENDING):
            if element.deadline and now > element.deadline:
                # Deadline passed, element overdue
                if not dry_run:
                    alert = self._create_alert(
                        episode, element,
                        alert_type=AlertType.BUNDLE_INCOMPLETE,
                        severity=AlertSeverity.HIGH,
                        message=(
                            f"Overdue: {element.element_name} for {episode.bundle_name} "
                            f"(deadline was {element.deadline.strftime('%H:%M')})"
                        ),
                    )
                    if alert:
                        alerts.append(alert)

                    # Update element status
                    element.status = ElementCheckStatus.NOT_MET
                    element.notes = f"Deadline expired at {element.deadline.strftime('%Y-%m-%d %H:%M')}"
                    element.save(update_fields=['status', 'notes', 'updated_at'])

        return alerts

    # =========================================================================
    # Mode 3: Adherence Monitoring
    # =========================================================================

    def check_adherence(self, bundle_id=None, dry_run=False):
        """Run element checkers on active episodes, update adherence percentages.

        Returns dict with counts of episodes checked and elements updated.
        """
        episodes = BundleEpisode.objects.filter(
            status=EpisodeStatus.ACTIVE,
        ).prefetch_related('element_results')

        if bundle_id:
            episodes = episodes.filter(bundle_id=bundle_id)

        results = {
            'episodes_checked': 0,
            'elements_updated': 0,
            'alerts_created': 0,
        }

        for episode in episodes:
            try:
                updated = self._check_episode_adherence(episode, dry_run)
                results['episodes_checked'] += 1
                results['elements_updated'] += updated
            except Exception as e:
                logger.error(f"Error checking adherence for episode {episode.id}: {e}")

        self._update_monitor_state('adherence', results['episodes_checked'])

        logger.info(
            f"Adherence check complete: {results['episodes_checked']} episodes, "
            f"{results['elements_updated']} elements updated"
        )
        return results

    def _check_episode_adherence(self, episode, dry_run=False):
        """Run element checkers for an episode and update adherence."""
        bundle = get_bundle(episode.bundle_id)
        if not bundle:
            logger.warning(f"Bundle {episode.bundle_id} not found for episode {episode.id}")
            return 0

        elements_updated = 0

        for element_result in episode.element_results.filter(status=ElementCheckStatus.PENDING):
            # Find matching bundle element
            bundle_element = None
            for be in bundle.elements:
                if be.element_id == element_result.element_id:
                    bundle_element = be
                    break

            if not bundle_element:
                continue

            # Get appropriate checker
            checker = self._get_checker(bundle_element.checker_type)
            if not checker:
                continue

            # Run check
            try:
                check_result = checker.check(
                    element=bundle_element,
                    patient_id=episode.patient_id,
                    trigger_time=episode.trigger_time,
                    age_days=episode.patient_age_days,
                    episode_id=str(episode.id),
                )

                if not dry_run:
                    self._apply_check_result(element_result, check_result)
                    elements_updated += 1
            except Exception as e:
                logger.error(
                    f"Error checking element {element_result.element_id} "
                    f"for episode {episode.id}: {e}"
                )

        # Recalculate adherence
        if not dry_run:
            episode.calculate_adherence()

            # Check if episode is complete (no more pending elements)
            pending = episode.element_results.filter(status=ElementCheckStatus.PENDING).count()
            if pending == 0:
                episode.status = EpisodeStatus.COMPLETE
                episode.completed_at = timezone.now()
                episode.save(update_fields=['status', 'completed_at', 'updated_at'])
                logger.info(f"Episode {episode.id} completed: {episode.adherence_percentage}% adherence")

        return elements_updated

    def _get_checker(self, checker_type):
        """Get the appropriate checker for an element type."""
        return self._checkers.get(checker_type)

    def _apply_check_result(self, element_result, check_result):
        """Apply a CheckResult to an ElementResult."""
        # Map status strings to enum values
        status_map = {
            'met': ElementCheckStatus.MET,
            'not_met': ElementCheckStatus.NOT_MET,
            'pending': ElementCheckStatus.PENDING,
            'na': ElementCheckStatus.NOT_APPLICABLE,
            'unable': ElementCheckStatus.UNABLE_TO_ASSESS,
        }

        new_status = status_map.get(check_result.status, ElementCheckStatus.PENDING)

        # Only update if status changed from pending
        if new_status != ElementCheckStatus.PENDING or element_result.value != check_result.value:
            element_result.status = new_status
            element_result.value = check_result.value or ''
            element_result.notes = check_result.notes or ''
            if check_result.completed_at:
                element_result.completed_at = check_result.completed_at
            if check_result.deadline:
                element_result.deadline = check_result.deadline
            element_result.save(update_fields=[
                'status', 'value', 'notes', 'completed_at', 'deadline', 'updated_at',
            ])

    # =========================================================================
    # Alert Creation
    # =========================================================================

    def _create_alert(self, episode, element, alert_type, severity, message):
        """Create an alert for a guideline violation."""
        # Dedup: check for existing active alert
        existing = Alert.objects.active().filter(
            alert_type=alert_type,
            source_module='guideline_adherence',
            source_id=str(episode.id),
            details__element_id=element.element_id,
        ).exists()

        if existing:
            return None

        alert = Alert.objects.create(
            alert_type=alert_type,
            severity=severity,
            patient_id=episode.patient_mrn,
            patient_name=episode.patient_name,
            encounter_id=episode.encounter_id,
            source_module='guideline_adherence',
            source_id=str(episode.id),
            title=f"{episode.bundle_name}: {element.element_name}",
            description=message,
            details={
                'episode_id': str(episode.id),
                'bundle_id': episode.bundle_id,
                'bundle_name': episode.bundle_name,
                'element_id': element.element_id,
                'element_name': element.element_name,
                'patient_unit': episode.patient_unit,
                'trigger_time': episode.trigger_time.isoformat() if episode.trigger_time else '',
                'deadline': element.deadline.isoformat() if element.deadline else '',
            },
        )

        AlertAudit.objects.create(
            alert=alert,
            action='created',
            details=f"Auto-generated: {message}",
        )

        return alert

    # =========================================================================
    # Review
    # =========================================================================

    def submit_review(self, episode_id, reviewer, decision, notes='',
                      override_reason='', deviation_type=''):
        """Submit a review decision for an episode."""
        episode = BundleEpisode.objects.get(id=episode_id)

        latest_assessment = episode.assessments.order_by('-created_at').first()
        llm_decision = ''
        if latest_assessment:
            llm_decision = latest_assessment.primary_determination

        is_override = llm_decision != '' and decision != llm_decision

        review = EpisodeReview.objects.create(
            episode=episode,
            assessment=latest_assessment,
            reviewer=reviewer,
            reviewer_decision=decision,
            llm_decision=llm_decision,
            is_override=is_override,
            override_reason_category=override_reason,
            deviation_type=deviation_type,
            notes=notes,
        )

        episode.review_status = 'reviewed'
        episode.overall_determination = decision
        episode.save(update_fields=['review_status', 'overall_determination', 'updated_at'])

        return review

    # =========================================================================
    # Stats
    # =========================================================================

    def get_stats(self):
        """Get compliance statistics."""
        now = timezone.now()
        start_30d = now - timedelta(days=30)

        active = BundleEpisode.objects.filter(status=EpisodeStatus.ACTIVE).count()

        completed_30d = BundleEpisode.objects.filter(
            status__in=[EpisodeStatus.COMPLETE, EpisodeStatus.CLOSED],
            completed_at__gte=start_30d,
        )
        total_completed = completed_30d.count()
        full_adherence = completed_30d.filter(adherence_level=AdherenceLevel.FULL).count()

        active_alerts = Alert.objects.active().filter(
            alert_type__in=[AlertType.GUIDELINE_ADHERENCE, AlertType.BUNDLE_INCOMPLETE],
        ).count()

        # Per-bundle breakdown
        bundle_stats = []
        for bundle in get_enabled_bundles():
            b_completed = completed_30d.filter(bundle_id=bundle.bundle_id)
            b_total = b_completed.count()
            b_full = b_completed.filter(adherence_level=AdherenceLevel.FULL).count()
            b_active = BundleEpisode.objects.filter(
                bundle_id=bundle.bundle_id, status=EpisodeStatus.ACTIVE,
            ).count()
            bundle_stats.append({
                'bundle_id': bundle.bundle_id,
                'bundle_name': bundle.name,
                'total': b_total,
                'full_adherence': b_full,
                'compliance_pct': round((b_full / b_total * 100) if b_total > 0 else 0, 1),
                'active_count': b_active,
            })

        return {
            'active_episodes': active,
            'completed_30d': total_completed,
            'full_adherence': full_adherence,
            'overall_compliance': round(
                (full_adherence / total_completed * 100) if total_completed > 0 else 0, 1
            ),
            'active_alerts': active_alerts,
            'bundle_stats': bundle_stats,
        }

    # =========================================================================
    # Monitor State
    # =========================================================================

    def _update_monitor_state(self, monitor_type, count):
        """Update monitor state checkpoint."""
        state, _ = MonitorState.objects.get_or_create(
            monitor_type=monitor_type,
            defaults={'state_data': {}},
        )
        state.last_poll_time = timezone.now()
        state.last_run_status = 'success'
        state.state_data['last_count'] = count
        state.save(update_fields=['last_poll_time', 'last_run_status', 'state_data', 'updated_at'])
