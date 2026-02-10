"""
Tests for Guideline Adherence module.

Tests cover:
- Model creation and properties
- Enum values
- Bundle definitions
- Checker base class
- Service layer (stats, adherence calculation)
- Template rendering
- URL resolution
- Alert type integration
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse, resolve
from django.utils import timezone
from django.template.loader import render_to_string

from apps.alerts.models import (
    Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity,
)

from .models import (
    BundleEpisode, ElementResult, EpisodeAssessment, EpisodeReview,
    MonitorState, EpisodeStatus, ElementCheckStatus, AdherenceLevel,
    ReviewDecision,
)
from .bundles import (
    GUIDELINE_BUNDLES, get_bundle, get_enabled_bundles,
    identify_applicable_bundles,
)


# ============================================================================
# Alert Type Tests
# ============================================================================

class AlertTypeTests(TestCase):
    """Verify guideline adherence alert types exist."""

    def test_guideline_adherence_exists(self):
        self.assertEqual(AlertType.GUIDELINE_ADHERENCE, 'guideline_adherence')

    def test_bundle_incomplete_exists(self):
        self.assertEqual(AlertType.BUNDLE_INCOMPLETE, 'bundle_incomplete')

    def test_create_guideline_alert(self):
        alert = Alert.objects.create(
            alert_type=AlertType.GUIDELINE_ADHERENCE,
            source_module='guideline_adherence',
            source_id='test-1',
            title='Test Guideline Alert',
            summary='Bundle element overdue',
            severity=AlertSeverity.HIGH,
        )
        self.assertEqual(alert.alert_type, 'guideline_adherence')
        self.assertEqual(alert.status, AlertStatus.PENDING)

    def test_create_bundle_incomplete_alert(self):
        alert = Alert.objects.create(
            alert_type=AlertType.BUNDLE_INCOMPLETE,
            source_module='guideline_adherence',
            source_id='test-2',
            title='Test Bundle Alert',
            summary='Bundle incomplete',
            severity=AlertSeverity.HIGH,
        )
        self.assertEqual(alert.alert_type, 'bundle_incomplete')


# ============================================================================
# Enum Tests
# ============================================================================

class EnumTests(TestCase):
    """Test TextChoices enum values."""

    def test_episode_status_values(self):
        self.assertEqual(EpisodeStatus.ACTIVE, 'active')
        self.assertEqual(EpisodeStatus.COMPLETE, 'complete')
        self.assertEqual(EpisodeStatus.CLOSED, 'closed')

    def test_element_check_status_values(self):
        self.assertEqual(ElementCheckStatus.MET, 'met')
        self.assertEqual(ElementCheckStatus.NOT_MET, 'not_met')
        self.assertEqual(ElementCheckStatus.PENDING, 'pending')
        self.assertEqual(ElementCheckStatus.NOT_APPLICABLE, 'na')
        self.assertEqual(ElementCheckStatus.UNABLE_TO_ASSESS, 'unable')

    def test_adherence_level_values(self):
        self.assertEqual(AdherenceLevel.FULL, 'full')
        self.assertEqual(AdherenceLevel.PARTIAL, 'partial')
        self.assertEqual(AdherenceLevel.LOW, 'low')
        self.assertEqual(AdherenceLevel.NOT_APPLICABLE, 'na')

    def test_review_decision_values(self):
        self.assertEqual(ReviewDecision.GUIDELINE_APPROPRIATE, 'guideline_appropriate')
        self.assertEqual(ReviewDecision.GUIDELINE_DEVIATION, 'guideline_deviation')
        self.assertEqual(ReviewDecision.NEEDS_MORE_INFO, 'needs_more_info')


# ============================================================================
# Model Tests
# ============================================================================

class BundleEpisodeModelTests(TestCase):
    """Test BundleEpisode model."""

    def _create_episode(self, **kwargs):
        defaults = {
            'patient_id': 'fhir-patient-001',
            'patient_mrn': 'GA-TEST-001',
            'patient_name': 'Test Patient',
            'encounter_id': 'enc-001',
            'bundle_id': 'sepsis_peds_2024',
            'bundle_name': 'Pediatric Sepsis Bundle',
            'trigger_type': 'diagnosis',
            'trigger_code': 'A41.9',
            'trigger_description': 'Sepsis',
            'trigger_time': timezone.now() - timedelta(hours=2),
            'patient_age_days': 1095,
            'patient_age_months': 36.0,
            'patient_unit': 'G3 PICU',
            'status': EpisodeStatus.ACTIVE,
            'elements_total': 6,
        }
        defaults.update(kwargs)
        return BundleEpisode.objects.create(**defaults)

    def test_create_episode(self):
        episode = self._create_episode()
        self.assertIsNotNone(episode.id)
        self.assertEqual(episode.bundle_id, 'sepsis_peds_2024')
        self.assertEqual(episode.status, EpisodeStatus.ACTIVE)

    def test_default_adherence(self):
        episode = self._create_episode()
        self.assertEqual(episode.adherence_percentage, 0)
        self.assertEqual(episode.adherence_level, AdherenceLevel.NOT_APPLICABLE)

    def test_unique_together(self):
        trigger_time = timezone.now()
        self._create_episode(trigger_time=trigger_time)
        with self.assertRaises(Exception):
            self._create_episode(trigger_time=trigger_time)

    def test_calculate_adherence_full(self):
        episode = self._create_episode(elements_total=3)
        for i in range(3):
            ElementResult.objects.create(
                episode=episode,
                element_id=f'elem_{i}',
                element_name=f'Element {i}',
                status=ElementCheckStatus.MET,
                required=True,
            )
        episode.calculate_adherence()
        self.assertEqual(episode.adherence_percentage, 100.0)
        self.assertEqual(episode.adherence_level, AdherenceLevel.FULL)
        self.assertEqual(episode.elements_met, 3)

    def test_calculate_adherence_partial(self):
        episode = self._create_episode(elements_total=3)
        ElementResult.objects.create(
            episode=episode, element_id='e1', element_name='E1',
            status=ElementCheckStatus.MET, required=True,
        )
        ElementResult.objects.create(
            episode=episode, element_id='e2', element_name='E2',
            status=ElementCheckStatus.MET, required=True,
        )
        ElementResult.objects.create(
            episode=episode, element_id='e3', element_name='E3',
            status=ElementCheckStatus.NOT_MET, required=True,
        )
        episode.calculate_adherence()
        self.assertAlmostEqual(episode.adherence_percentage, 66.7, places=1)
        self.assertEqual(episode.adherence_level, AdherenceLevel.PARTIAL)

    def test_calculate_adherence_with_na(self):
        episode = self._create_episode(elements_total=3)
        ElementResult.objects.create(
            episode=episode, element_id='e1', element_name='E1',
            status=ElementCheckStatus.MET, required=True,
        )
        ElementResult.objects.create(
            episode=episode, element_id='e2', element_name='E2',
            status=ElementCheckStatus.NOT_APPLICABLE, required=True,
        )
        ElementResult.objects.create(
            episode=episode, element_id='e3', element_name='E3',
            status=ElementCheckStatus.MET, required=True,
        )
        episode.calculate_adherence()
        self.assertEqual(episode.adherence_percentage, 100.0)
        self.assertEqual(episode.elements_applicable, 2)

    def test_str_representation(self):
        episode = self._create_episode()
        s = str(episode)
        self.assertIn('Pediatric Sepsis Bundle', s)
        self.assertIn('GA-TEST-001', s)


class ElementResultModelTests(TestCase):
    """Test ElementResult model."""

    def setUp(self):
        self.episode = BundleEpisode.objects.create(
            patient_id='p1', patient_mrn='MRN-1', encounter_id='e1',
            bundle_id='sepsis_peds_2024', bundle_name='Sepsis',
            trigger_type='diagnosis', trigger_time=timezone.now(),
            elements_total=1,
        )

    def test_create_element(self):
        elem = ElementResult.objects.create(
            episode=self.episode,
            element_id='sepsis_blood_cx',
            element_name='Blood Culture',
            status=ElementCheckStatus.PENDING,
            required=True,
            time_window_hours=1.0,
        )
        self.assertEqual(elem.element_id, 'sepsis_blood_cx')
        self.assertEqual(elem.status, ElementCheckStatus.PENDING)

    def test_unique_together(self):
        ElementResult.objects.create(
            episode=self.episode,
            element_id='sepsis_blood_cx',
            element_name='Blood Culture',
        )
        with self.assertRaises(Exception):
            ElementResult.objects.create(
                episode=self.episode,
                element_id='sepsis_blood_cx',
                element_name='Blood Culture',
            )

    def test_is_overdue_no_deadline(self):
        elem = ElementResult.objects.create(
            episode=self.episode,
            element_id='test_elem',
            element_name='Test',
        )
        self.assertFalse(elem.is_overdue)

    def test_is_overdue_with_deadline(self):
        elem = ElementResult.objects.create(
            episode=self.episode,
            element_id='test_overdue',
            element_name='Test Overdue',
            status=ElementCheckStatus.PENDING,
            deadline=timezone.now() - timedelta(hours=1),
        )
        self.assertTrue(elem.is_overdue)

    def test_is_not_overdue_if_met(self):
        elem = ElementResult.objects.create(
            episode=self.episode,
            element_id='test_met',
            element_name='Test Met',
            status=ElementCheckStatus.MET,
            deadline=timezone.now() - timedelta(hours=1),
        )
        self.assertFalse(elem.is_overdue)


class EpisodeAssessmentModelTests(TestCase):
    """Test EpisodeAssessment model."""

    def test_create_assessment(self):
        episode = BundleEpisode.objects.create(
            patient_id='p1', patient_mrn='MRN-1', encounter_id='e1',
            bundle_id='test', bundle_name='Test',
            trigger_type='diagnosis', trigger_time=timezone.now(),
            elements_total=1,
        )
        assessment = EpisodeAssessment.objects.create(
            episode=episode,
            assessment_type='clinical_impression',
            primary_determination='guideline_appropriate',
            confidence='high',
            model_used='llama3.3:70b',
        )
        self.assertEqual(assessment.assessment_type, 'clinical_impression')
        self.assertEqual(assessment.primary_determination, 'guideline_appropriate')


class EpisodeReviewModelTests(TestCase):
    """Test EpisodeReview model."""

    def test_create_review(self):
        episode = BundleEpisode.objects.create(
            patient_id='p1', patient_mrn='MRN-1', encounter_id='e1',
            bundle_id='test', bundle_name='Test',
            trigger_type='diagnosis', trigger_time=timezone.now(),
            elements_total=1,
        )
        review = EpisodeReview.objects.create(
            episode=episode,
            reviewer='dr_smith',
            reviewer_decision=ReviewDecision.GUIDELINE_APPROPRIATE,
        )
        self.assertEqual(review.reviewer_decision, 'guideline_appropriate')
        self.assertFalse(review.is_override)

    def test_override_review(self):
        episode = BundleEpisode.objects.create(
            patient_id='p1', patient_mrn='MRN-1', encounter_id='e1',
            bundle_id='test', bundle_name='Test',
            trigger_type='diagnosis', trigger_time=timezone.now(),
            elements_total=1,
        )
        review = EpisodeReview.objects.create(
            episode=episode,
            reviewer='dr_jones',
            reviewer_decision=ReviewDecision.GUIDELINE_DEVIATION,
            llm_decision='guideline_appropriate',
            is_override=True,
            override_reason_category='extraction_error',
        )
        self.assertTrue(review.is_override)
        self.assertEqual(review.override_reason_category, 'extraction_error')


class MonitorStateModelTests(TestCase):
    """Test MonitorState model."""

    def test_create_monitor_state(self):
        state = MonitorState.objects.create(
            monitor_type='trigger',
            last_poll_time=timezone.now(),
            last_run_status='success',
        )
        self.assertEqual(state.monitor_type, 'trigger')

    def test_unique_monitor_type(self):
        MonitorState.objects.create(monitor_type='trigger')
        with self.assertRaises(Exception):
            MonitorState.objects.create(monitor_type='trigger')


# ============================================================================
# Bundle Definition Tests
# ============================================================================

class BundleDefinitionTests(TestCase):
    """Test bundle definitions."""

    def test_all_bundles_loaded(self):
        self.assertEqual(len(GUIDELINE_BUNDLES), 9)

    def test_sepsis_bundle(self):
        bundle = get_bundle('sepsis_peds_2024')
        self.assertIsNotNone(bundle)
        self.assertEqual(bundle.name, 'Pediatric Sepsis Bundle')
        self.assertEqual(len(bundle.elements), 6)

    def test_febrile_infant_bundle(self):
        bundle = get_bundle('febrile_infant_2024')
        self.assertIsNotNone(bundle)
        self.assertEqual(len(bundle.elements), 14)

    def test_neonatal_hsv_bundle(self):
        bundle = get_bundle('neonatal_hsv_2024')
        self.assertIsNotNone(bundle)
        self.assertEqual(len(bundle.elements), 11)

    def test_cdiff_bundle(self):
        bundle = get_bundle('cdiff_testing_2024')
        self.assertIsNotNone(bundle)
        self.assertEqual(len(bundle.elements), 8)

    def test_cap_bundle(self):
        bundle = get_bundle('cap_peds_2024')
        self.assertIsNotNone(bundle)
        self.assertEqual(len(bundle.elements), 6)

    def test_uti_bundle(self):
        bundle = get_bundle('uti_peds_2024')
        self.assertIsNotNone(bundle)
        self.assertEqual(len(bundle.elements), 7)

    def test_ssti_bundle(self):
        bundle = get_bundle('ssti_peds_2024')
        self.assertIsNotNone(bundle)
        self.assertEqual(len(bundle.elements), 6)

    def test_fn_bundle(self):
        bundle = get_bundle('fn_peds_2024')
        self.assertIsNotNone(bundle)
        self.assertEqual(len(bundle.elements), 6)

    def test_surgical_bundle(self):
        bundle = get_bundle('surgical_prophy_2024')
        self.assertIsNotNone(bundle)
        self.assertEqual(len(bundle.elements), 5)

    def test_get_nonexistent_bundle(self):
        bundle = get_bundle('nonexistent')
        self.assertIsNone(bundle)

    def test_get_enabled_bundles(self):
        bundles = get_enabled_bundles()
        self.assertTrue(len(bundles) > 0)
        # surgical_prophy_2024 excluded by default
        ids = [b.bundle_id for b in bundles]
        self.assertNotIn('surgical_prophy_2024', ids)

    def test_identify_applicable_bundles_sepsis(self):
        bundles = identify_applicable_bundles(['A41.9'])
        ids = [b.bundle_id for b in bundles]
        self.assertIn('sepsis_peds_2024', ids)

    def test_identify_applicable_bundles_febrile_infant(self):
        bundles = identify_applicable_bundles(['R50.9'], patient_age_days=14)
        ids = [b.bundle_id for b in bundles]
        self.assertIn('febrile_infant_2024', ids)

    def test_identify_applicable_bundles_age_filter(self):
        # Febrile infant bundle should NOT match for 2-year-old
        bundles = identify_applicable_bundles(['R50.9'], patient_age_days=730)
        ids = [b.bundle_id for b in bundles]
        self.assertNotIn('febrile_infant_2024', ids)

    def test_bundle_elements_have_ids(self):
        for bundle_id, bundle in GUIDELINE_BUNDLES.items():
            for elem in bundle.elements:
                self.assertTrue(
                    len(elem.element_id) > 0,
                    f"Empty element_id in bundle {bundle_id}",
                )

    def test_bundle_elements_have_checker_types(self):
        for bundle_id, bundle in GUIDELINE_BUNDLES.items():
            for elem in bundle.elements:
                self.assertTrue(
                    len(elem.checker_type) > 0,
                    f"Empty checker_type for {elem.element_id} in {bundle_id}",
                )


# ============================================================================
# Checker Tests
# ============================================================================

class BaseCheckerTests(TestCase):
    """Test base checker functionality."""

    def test_calculate_deadline(self):
        from .logic.checkers.base import ElementChecker, CheckResult
        from datetime import datetime

        class DummyChecker(ElementChecker):
            def check(self, element, patient_id, trigger_time, **kwargs):
                return CheckResult(
                    element_id='test', element_name='Test',
                    status='pending',
                )

        checker = DummyChecker()
        trigger = datetime(2024, 1, 1, 12, 0, 0)
        deadline = checker._calculate_deadline(trigger, 1.0)
        self.assertEqual(deadline, datetime(2024, 1, 1, 13, 0, 0))

    def test_calculate_deadline_none(self):
        from .logic.checkers.base import ElementChecker, CheckResult

        class DummyChecker(ElementChecker):
            def check(self, element, patient_id, trigger_time, **kwargs):
                return CheckResult(
                    element_id='test', element_name='Test', status='pending',
                )

        checker = DummyChecker()
        from datetime import datetime
        deadline = checker._calculate_deadline(datetime.now(), None)
        self.assertIsNone(deadline)


# ============================================================================
# Service Layer Tests
# ============================================================================

class ServiceStatsTests(TestCase):
    """Test service layer stats."""

    def test_get_stats_empty(self):
        from .services import GuidelineAdherenceService
        service = GuidelineAdherenceService.__new__(GuidelineAdherenceService)
        # Manually set attributes to avoid FHIR connection
        service.fhir_client = None
        service._checkers = {}

        stats = service.get_stats()
        self.assertEqual(stats['active_episodes'], 0)
        self.assertEqual(stats['completed_30d'], 0)
        self.assertEqual(stats['overall_compliance'], 0)

    def test_get_stats_with_data(self):
        from .services import GuidelineAdherenceService

        # Create some completed episodes
        for i in range(3):
            ep = BundleEpisode.objects.create(
                patient_id=f'p{i}', patient_mrn=f'MRN-{i}',
                encounter_id=f'e{i}',
                bundle_id='sepsis_peds_2024', bundle_name='Sepsis',
                trigger_type='diagnosis',
                trigger_time=timezone.now() - timedelta(hours=i+1),
                elements_total=3,
                status=EpisodeStatus.COMPLETE,
                completed_at=timezone.now(),
                adherence_percentage=100.0,
                adherence_level=AdherenceLevel.FULL,
            )

        service = GuidelineAdherenceService.__new__(GuidelineAdherenceService)
        service.fhir_client = None
        service._checkers = {}

        stats = service.get_stats()
        self.assertEqual(stats['completed_30d'], 3)
        self.assertEqual(stats['full_adherence'], 3)
        self.assertEqual(stats['overall_compliance'], 100.0)


# ============================================================================
# URL Tests
# ============================================================================

class URLTests(TestCase):
    """Test URL resolution."""

    def test_dashboard_url(self):
        url = reverse('guideline_adherence:dashboard')
        self.assertEqual(url, '/guideline-adherence/')

    def test_active_episodes_url(self):
        url = reverse('guideline_adherence:active_episodes')
        self.assertEqual(url, '/guideline-adherence/active/')

    def test_episode_detail_url(self):
        import uuid
        pk = uuid.uuid4()
        url = reverse('guideline_adherence:episode_detail', kwargs={'pk': pk})
        self.assertIn(str(pk), url)

    def test_bundle_detail_url(self):
        url = reverse('guideline_adherence:bundle_detail', kwargs={'bundle_id': 'sepsis_peds_2024'})
        self.assertIn('sepsis_peds_2024', url)

    def test_metrics_url(self):
        url = reverse('guideline_adherence:metrics')
        self.assertEqual(url, '/guideline-adherence/metrics/')

    def test_history_url(self):
        url = reverse('guideline_adherence:history')
        self.assertEqual(url, '/guideline-adherence/history/')

    def test_help_url(self):
        url = reverse('guideline_adherence:help')
        self.assertEqual(url, '/guideline-adherence/help/')

    def test_api_stats_url(self):
        url = reverse('guideline_adherence:api_stats')
        self.assertEqual(url, '/guideline-adherence/api/stats/')

    def test_api_export_url(self):
        url = reverse('guideline_adherence:api_export')
        self.assertEqual(url, '/guideline-adherence/api/export/')


# ============================================================================
# Template Rendering Tests
# ============================================================================

class TemplateRenderingTests(TestCase):
    """Test templates render without errors using render_to_string."""

    def _create_test_episode(self):
        episode = BundleEpisode.objects.create(
            patient_id='p1', patient_mrn='TEST-001',
            patient_name='Test Patient', encounter_id='e1',
            bundle_id='sepsis_peds_2024', bundle_name='Pediatric Sepsis',
            trigger_type='diagnosis', trigger_code='A41.9',
            trigger_description='Sepsis',
            trigger_time=timezone.now() - timedelta(hours=2),
            patient_age_days=1095, patient_unit='G3 PICU',
            status=EpisodeStatus.ACTIVE,
            elements_total=6, adherence_percentage=66.7,
            adherence_level=AdherenceLevel.PARTIAL,
            elements_met=4, elements_not_met=2,
        )
        for i in range(6):
            ElementResult.objects.create(
                episode=episode,
                element_id=f'elem_{i}',
                element_name=f'Element {i}',
                status=ElementCheckStatus.MET if i < 4 else ElementCheckStatus.NOT_MET,
                required=True,
            )
        return episode

    def test_render_dashboard(self):
        from .bundles import get_enabled_bundles
        context = {
            'stats': {
                'overall_compliance': 75.0,
                'bundles_tracked': 8,
                'active_episodes': 3,
                'active_alerts': 1,
                'completed_30d': 10,
            },
            'bundle_stats': [],
            'active_episodes': BundleEpisode.objects.none(),
        }
        html = render_to_string('guideline_adherence/dashboard.html', context)
        self.assertIn('75%', html)

    def test_render_active_episodes(self):
        self._create_test_episode()
        context = {
            'episodes': BundleEpisode.objects.filter(status=EpisodeStatus.ACTIVE),
            'bundles': get_enabled_bundles(),
            'current_filters': {'bundle': None, 'review_status': None},
        }
        html = render_to_string('guideline_adherence/active_episodes.html', context)
        self.assertIn('TEST-001', html)

    def test_render_episode_detail(self):
        episode = self._create_test_episode()
        context = {
            'episode': episode,
            'elements': episode.element_results.all(),
            'assessments': episode.assessments.all(),
            'reviews': episode.reviews.all(),
            'latest_assessment': None,
            'alerts': Alert.objects.none(),
            'resolution_reasons': [],
            'review_decisions': ReviewDecision.choices,
        }
        html = render_to_string('guideline_adherence/episode_detail.html', context)
        self.assertIn('Pediatric Sepsis', html)

    def test_render_bundle_detail(self):
        bundle = get_bundle('sepsis_peds_2024')
        context = {
            'bundle': bundle,
            'recent_episodes': BundleEpisode.objects.none(),
            'element_stats': [],
        }
        html = render_to_string('guideline_adherence/bundle_detail.html', context)
        self.assertIn('Sepsis', html)

    def test_render_metrics(self):
        context = {
            'days': 30,
            'total': 10,
            'full': 7,
            'partial': 2,
            'low': 1,
            'overall_compliance': 70.0,
            'bundle_metrics': [],
            'review_count': 5,
            'override_count': 1,
            'override_rate': 20.0,
        }
        html = render_to_string('guideline_adherence/metrics.html', context)
        self.assertIn('70%', html)

    def test_render_history(self):
        context = {
            'episodes': BundleEpisode.objects.none(),
            'bundles': get_enabled_bundles(),
            'days': 30,
            'current_filters': {
                'status': None, 'bundle': None,
                'adherence': None, 'days': 30,
            },
        }
        html = render_to_string('guideline_adherence/history.html', context)
        self.assertIn('History', html)

    def test_render_help(self):
        context = {
            'bundles': GUIDELINE_BUNDLES,
        }
        html = render_to_string('guideline_adherence/help.html', context)
        self.assertIn('Sepsis', html)


# ============================================================================
# Config Tests
# ============================================================================

class ConfigTests(TestCase):
    """Test configuration values."""

    def test_loinc_codes_defined(self):
        from .logic import config as cfg
        self.assertEqual(cfg.LOINC_LACTATE, '2524-7')
        self.assertEqual(cfg.LOINC_BLOOD_CULTURE, '600-7')
        self.assertEqual(cfg.LOINC_PROCALCITONIN, '33959-8')
        self.assertEqual(cfg.LOINC_CRP, '1988-5')

    def test_clinical_thresholds(self):
        from .logic import config as cfg
        self.assertEqual(cfg.FI_PCT_ABNORMAL, 0.5)
        self.assertEqual(cfg.FI_ANC_ABNORMAL, 4000)
        self.assertEqual(cfg.FI_CRP_ABNORMAL, 2.0)
        self.assertEqual(cfg.FI_CSF_WBC_PLEOCYTOSIS, 15)

    def test_icd10_codes_defined(self):
        from .logic import config as cfg
        self.assertIn('A41', cfg.ICD10_SEPSIS)
        self.assertIn('R50', cfg.ICD10_FEBRILE_INFANT)
        self.assertIn('A04.7', cfg.ICD10_CDIFF)


# ============================================================================
# Febrile Infant Checker Tests
# ============================================================================

class FebrileInfantCheckerTests(TestCase):
    """Test febrile infant age stratification logic."""

    def test_age_groups(self):
        from .logic.checkers.febrile_infant_checker import get_age_group, InfantAgeGroup
        self.assertEqual(get_age_group(3), InfantAgeGroup.DAYS_0_7)
        self.assertEqual(get_age_group(10), InfantAgeGroup.DAYS_8_21)
        self.assertEqual(get_age_group(25), InfantAgeGroup.DAYS_22_28)
        self.assertEqual(get_age_group(45), InfantAgeGroup.DAYS_29_60)


# ============================================================================
# HSV Checker Tests
# ============================================================================

class HSVCheckerTests(TestCase):
    """Test HSV classification logic."""

    def test_hsv_classifications(self):
        from .logic.checkers.hsv_checker import HSVClassification
        self.assertEqual(HSVClassification.SEM.value, 'SEM')
        self.assertEqual(HSVClassification.CNS.value, 'CNS')
        self.assertEqual(HSVClassification.DISSEMINATED.value, 'Disseminated')

    def test_treatment_durations(self):
        from .logic.checkers.hsv_checker import HSVChecker, HSVClassification
        self.assertEqual(HSVChecker.TREATMENT_DURATION[HSVClassification.SEM], 14)
        self.assertEqual(HSVChecker.TREATMENT_DURATION[HSVClassification.CNS], 21)
        self.assertEqual(HSVChecker.TREATMENT_DURATION[HSVClassification.DISSEMINATED], 21)


# ============================================================================
# C.diff Checker Tests
# ============================================================================

class CDiffCheckerTests(TestCase):
    """Test C.diff testing appropriateness logic."""

    def test_appropriateness_enum(self):
        from .logic.checkers.cdiff_testing_checker import TestAppropriateness
        self.assertEqual(TestAppropriateness.APPROPRIATE.value, 'appropriate')
        self.assertEqual(TestAppropriateness.INAPPROPRIATE.value, 'inappropriate')

    def test_min_age(self):
        from .logic.checkers.cdiff_testing_checker import CDiffTestingChecker
        self.assertEqual(CDiffTestingChecker.MIN_AGE_YEARS, 3)
        self.assertEqual(CDiffTestingChecker.MIN_LIQUID_STOOLS, 3)
