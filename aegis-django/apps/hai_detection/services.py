"""
HAI Detection Service - Django adaptation of monitor.py.

Orchestrates the HAI detection pipeline:
1. Run candidate detectors (rule-based screening)
2. Run LLM classification on pending candidates
3. Create review queue entries for IP review

Uses Django ORM instead of SQLite HAIDatabase.
"""

import logging
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from apps.alerts.models import Alert, AlertType, AlertSeverity, AlertStatus

from .models import (
    HAICandidate, HAIClassification, HAIReview, LLMAuditLog,
    HAIType, CandidateStatus, ClassificationDecision,
    ReviewQueueType,
)

logger = logging.getLogger(__name__)

# Map HAIType to AlertType
HAI_TYPE_TO_ALERT_TYPE = {
    HAIType.CLABSI: AlertType.CLABSI,
    HAIType.SSI: AlertType.SSI,
    HAIType.CAUTI: AlertType.CAUTI,
    HAIType.VAE: AlertType.VAE,
    HAIType.CDI: AlertType.CDI,
}


class HAIDetectionService:
    """
    Orchestrates HAI detection, classification, and review pipeline.

    Django adaptation of Flask HAIMonitor class.
    """

    def __init__(self):
        self._classifiers = {}
        self._detectors = {}

    def _get_detector(self, hai_type):
        """Lazy-load a candidate detector."""
        if hai_type not in self._detectors:
            try:
                from .logic.candidates import (
                    CLABSICandidateDetector,
                    SSICandidateDetector,
                    VAECandidateDetector,
                    CAUTICandidateDetector,
                    CDICandidateDetector,
                )
                detector_map = {
                    HAIType.CLABSI: CLABSICandidateDetector,
                    HAIType.SSI: SSICandidateDetector,
                    HAIType.CAUTI: CAUTICandidateDetector,
                    HAIType.VAE: VAECandidateDetector,
                    HAIType.CDI: CDICandidateDetector,
                }
                cls = detector_map.get(hai_type)
                if cls:
                    self._detectors[hai_type] = cls()
            except ImportError as e:
                logger.warning(f"Could not import detector for {hai_type}: {e}")
                return None
        return self._detectors.get(hai_type)

    def _get_classifier(self, hai_type):
        """Lazy-load a classifier for the given HAI type."""
        if hai_type not in self._classifiers:
            try:
                from .logic.classifiers import (
                    CLABSIClassifierV2,
                    SSIClassifierV2,
                    VAEClassifier,
                    CAUTIClassifier,
                    CDIClassifier,
                )
                classifier_map = {
                    HAIType.CLABSI: CLABSIClassifierV2,
                    HAIType.SSI: SSIClassifierV2,
                    HAIType.CAUTI: CAUTIClassifier,
                    HAIType.VAE: VAEClassifier,
                    HAIType.CDI: CDIClassifier,
                }
                cls = classifier_map.get(hai_type)
                if cls:
                    self._classifiers[hai_type] = cls()
            except ImportError as e:
                logger.warning(f"Could not import classifier for {hai_type}: {e}")
                return None
        return self._classifiers.get(hai_type)

    def run_detection(self, dry_run=False):
        """
        Run all 5 HAI candidate detectors.

        Returns:
            Dict with detection results.
        """
        results = {'new_candidates': 0, 'by_type': {}, 'errors': []}

        for hai_type in HAIType:
            detector = self._get_detector(hai_type)
            if not detector:
                continue

            try:
                candidates = detector.detect_candidates()
                type_count = 0

                for candidate in candidates:
                    # Check for duplicate
                    exists = HAICandidate.objects.filter(
                        hai_type=hai_type,
                        culture_id=candidate.culture.fhir_id,
                    ).exists()

                    if exists:
                        continue

                    if dry_run:
                        logger.info(f"[DRY RUN] Would create {hai_type.value} candidate: {candidate.patient.mrn}")
                        type_count += 1
                        continue

                    # Create HAICandidate record
                    hai_candidate = HAICandidate.objects.create(
                        hai_type=hai_type,
                        patient_id=candidate.patient.fhir_id,
                        patient_mrn=candidate.patient.mrn,
                        patient_name=candidate.patient.name or '',
                        patient_location=candidate.patient.location or '',
                        culture_id=candidate.culture.fhir_id,
                        culture_date=candidate.culture.collection_date,
                        organism=candidate.culture.organism or '',
                        device_info=candidate.device_info.__dict__ if candidate.device_info else None,
                        device_days_at_culture=candidate.device_days_at_culture,
                        meets_initial_criteria=candidate.meets_initial_criteria,
                        exclusion_reason=candidate.exclusion_reason or '',
                        status=CandidateStatus.PENDING if candidate.meets_initial_criteria else CandidateStatus.EXCLUDED,
                        type_specific_data=self._extract_type_specific_data(candidate),
                    )

                    # Create corresponding Alert for main dashboard visibility
                    self._create_alert(hai_candidate, candidate)
                    type_count += 1

                results['by_type'][hai_type.value] = type_count
                results['new_candidates'] += type_count

            except Exception as e:
                logger.error(f"Error in {hai_type.value} detection: {e}", exc_info=True)
                results['errors'].append(f"{hai_type.value}: {str(e)}")

        logger.info(f"Detection complete: {results['new_candidates']} new candidates")
        return results

    def run_classification(self, limit=None, dry_run=False):
        """
        Classify pending candidates using LLM extraction + rules engine.

        Returns:
            Dict with classification results.
        """
        results = {'classified': 0, 'errors': 0, 'by_decision': {}, 'details': []}

        candidates = HAICandidate.objects.filter(
            status=CandidateStatus.PENDING,
        ).order_by('created_at')

        if limit:
            candidates = candidates[:limit]

        if not candidates:
            logger.info("No pending candidates to classify")
            return results

        logger.info(f"Found {len(candidates)} pending candidates")

        for candidate in candidates:
            try:
                classifier = self._get_classifier(HAIType(candidate.hai_type))
                if not classifier:
                    logger.warning(f"No classifier for {candidate.hai_type}")
                    continue

                # Note: In production, notes are retrieved via FHIR/Clarity
                # For now, classification works with available data
                classification_result = classifier.classify(candidate, [])

                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would classify {candidate.id} as "
                        f"{classification_result.decision.value} "
                        f"(confidence={classification_result.confidence:.2f})"
                    )
                else:
                    # Save classification
                    hai_classification = HAIClassification.objects.create(
                        candidate=candidate,
                        decision=classification_result.decision.value,
                        confidence=classification_result.confidence,
                        alternative_source=getattr(classification_result, 'alternative_source', '') or '',
                        is_mbi_lcbi=getattr(classification_result, 'is_mbi_lcbi', False),
                        supporting_evidence=[
                            {'text': e.text, 'source': e.source}
                            for e in (classification_result.supporting_evidence or [])
                        ],
                        contradicting_evidence=[
                            {'text': e.text, 'source': e.source}
                            for e in (classification_result.contradicting_evidence or [])
                        ],
                        reasoning=classification_result.reasoning or '',
                        model_used=classification_result.model_used,
                        prompt_version=classification_result.prompt_version,
                        tokens_used=classification_result.tokens_used or 0,
                        processing_time_ms=classification_result.processing_time_ms or 0,
                        extraction_data=getattr(classification_result, 'extraction_data', None),
                        rules_result=getattr(classification_result, 'rules_result', None),
                        strictness_level=getattr(classification_result, 'strictness_level', '') or '',
                    )

                    # Update candidate status
                    candidate.status = CandidateStatus.PENDING_REVIEW
                    candidate.save(update_fields=['status', 'updated_at'])

                    # Create review queue entry
                    HAIReview.objects.create(
                        candidate=candidate,
                        classification=hai_classification,
                        queue_type=ReviewQueueType.IP_REVIEW,
                    )

                decision = classification_result.decision.value
                results['by_decision'][decision] = results['by_decision'].get(decision, 0) + 1
                results['classified'] += 1

            except Exception as e:
                logger.error(f"Error classifying candidate {candidate.id}: {e}", exc_info=True)
                results['errors'] += 1

        logger.info(f"Classification complete: {results['classified']} classified, {results['errors']} errors")
        return results

    def run_full_pipeline(self, dry_run=False):
        """Run full pipeline: detection + classification."""
        results = {'detection': {}, 'classification': {}}

        logger.info("=== Step 1: Detection ===")
        results['detection'] = self.run_detection(dry_run=dry_run)

        if not dry_run:
            logger.info("=== Step 2: Classification ===")
            results['classification'] = self.run_classification(dry_run=dry_run)

        return results

    def get_stats(self):
        """Get summary statistics for dashboard."""
        from .views import _get_summary_stats
        return _get_summary_stats()

    def _extract_type_specific_data(self, candidate):
        """Extract type-specific data from a detection candidate."""
        data = {}

        # SSI data
        ssi_data = getattr(candidate, '_ssi_data', None)
        if ssi_data:
            proc = ssi_data.procedure
            data['ssi'] = {
                'procedure_name': proc.procedure_name,
                'procedure_code': proc.procedure_code,
                'nhsn_category': proc.nhsn_category,
                'procedure_date': proc.procedure_date.isoformat() if proc.procedure_date else None,
                'wound_class': proc.wound_class,
                'implant_used': proc.implant_used,
                'implant_type': proc.implant_type,
                'days_post_op': ssi_data.days_post_op,
                'surveillance_days': proc.get_surveillance_days(),
            }

        # VAE data
        vae_data = getattr(candidate, '_vae_data', None)
        if vae_data:
            data['vae'] = {
                'vac_onset_date': vae_data.vac_onset_date.isoformat() if vae_data.vac_onset_date else None,
                'ventilator_day_at_onset': vae_data.ventilator_day_at_onset,
                'baseline_min_fio2': vae_data.baseline_min_fio2,
                'baseline_min_peep': vae_data.baseline_min_peep,
                'fio2_increase': vae_data.fio2_increase,
                'peep_increase': vae_data.peep_increase,
            }
            if vae_data.episode:
                data['vae']['intubation_date'] = vae_data.episode.intubation_date.isoformat() if vae_data.episode.intubation_date else None

        # CAUTI data
        cauti_data = getattr(candidate, '_cauti_data', None)
        if cauti_data:
            data['cauti'] = {
                'catheter_days': cauti_data.catheter_days,
                'patient_age': cauti_data.patient_age,
                'culture_cfu_ml': cauti_data.culture_cfu_ml,
            }
            if cauti_data.catheter_episode:
                data['cauti']['catheter_type'] = cauti_data.catheter_episode.catheter_type
                data['cauti']['insertion_date'] = cauti_data.catheter_episode.insertion_date.isoformat() if cauti_data.catheter_episode.insertion_date else None

        # CDI data
        cdi_data = getattr(candidate, '_cdi_data', None)
        if cdi_data:
            data['cdi'] = {
                'onset_type': cdi_data.onset_type,
                'specimen_day': cdi_data.specimen_day,
                'is_recurrent': cdi_data.is_recurrent,
                'is_duplicate': cdi_data.is_duplicate,
                'days_since_last_cdi': cdi_data.days_since_last_cdi,
                'admission_date': cdi_data.admission_date.isoformat() if cdi_data.admission_date else None,
            }
            if cdi_data.test_result:
                data['cdi']['test_type'] = cdi_data.test_result.test_type
                data['cdi']['test_date'] = cdi_data.test_result.test_date.isoformat() if cdi_data.test_result.test_date else None

        return data

    def _create_alert(self, hai_candidate, detection_candidate):
        """Create an Alert record for main dashboard visibility."""
        alert_type = HAI_TYPE_TO_ALERT_TYPE.get(HAIType(hai_candidate.hai_type))
        if not alert_type:
            return

        summary = self._build_alert_summary(hai_candidate, detection_candidate)

        Alert.objects.create(
            alert_type=alert_type,
            source_module='hai_detection',
            source_id=str(hai_candidate.id),
            title=f"{hai_candidate.get_hai_type_display()} Candidate: {hai_candidate.patient_mrn}",
            summary=summary,
            details={
                'organism': hai_candidate.organism,
                'culture_date': hai_candidate.culture_date.isoformat(),
                'device_days': hai_candidate.device_days_at_culture,
                'type_specific': hai_candidate.type_specific_data,
            },
            patient_id=hai_candidate.patient_id,
            patient_mrn=hai_candidate.patient_mrn,
            patient_name=hai_candidate.patient_name,
            patient_location=hai_candidate.patient_location,
            severity=AlertSeverity.HIGH,
            status=AlertStatus.PENDING,
        )

    def _build_alert_summary(self, hai_candidate, detection_candidate):
        """Build alert summary based on HAI type."""
        hai_type = hai_candidate.hai_type

        if hai_type == HAIType.SSI:
            type_data = hai_candidate.type_specific_data.get('ssi', {})
            return (
                f"Possible SSI after {type_data.get('procedure_name', 'procedure')}: "
                f"{hai_candidate.organism or 'infection signal detected'}"
            )
        elif hai_type == HAIType.VAE:
            return f"Ventilator-associated condition detected for patient {hai_candidate.patient_mrn}"
        elif hai_type == HAIType.CAUTI:
            type_data = hai_candidate.type_specific_data.get('cauti', {})
            return (
                f"Positive urine culture ({hai_candidate.organism or 'organism pending'}) "
                f"with catheter {type_data.get('catheter_days', '?')} days"
            )
        elif hai_type == HAIType.CDI:
            type_data = hai_candidate.type_specific_data.get('cdi', {})
            onset = type_data.get('onset_type', 'unknown')
            return f"C. difficile test detected - {onset.upper()} onset"
        else:
            # CLABSI default
            return (
                f"Positive blood culture ({hai_candidate.organism or 'organism pending'}) "
                f"with central line {hai_candidate.device_days_at_culture or '?'} days"
            )
