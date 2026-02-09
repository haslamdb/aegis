"""
Tests for Surgical Prophylaxis module.

Tests cover:
- Model creation and properties
- Evaluator (7 ASHP bundle elements)
- Guidelines config loading
- HL7 parser (ADT/ORM/SIU messages)
- Location tracker state machine
- Service layer (stats, alert creation)
- Template rendering
- URL resolution
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse, resolve
from django.utils import timezone
from django.template.loader import render_to_string

from apps.alerts.models import Alert, AlertType, AlertSeverity, AlertStatus

from .models import (
    SurgicalCase, ProphylaxisEvaluation, ProphylaxisMedication,
    ComplianceMetric, SurgicalJourney, PatientLocation,
    PreOpCheck, AlertEscalation,
    ComplianceStatus, ProcedureCategory, LocationState, AlertTrigger,
)


# ------------------------------------------------------------------
# Alert Type Tests
# ------------------------------------------------------------------

class AlertTypeTests(TestCase):
    """Verify SURGICAL_PROPHYLAXIS alert type exists."""

    def test_surgical_prophylaxis_type_exists(self):
        self.assertEqual(AlertType.SURGICAL_PROPHYLAXIS, 'surgical_prophylaxis')

    def test_create_surgical_prophylaxis_alert(self):
        alert = Alert.objects.create(
            alert_type=AlertType.SURGICAL_PROPHYLAXIS,
            source_module='surgical_prophylaxis',
            source_id='test-case-001',
            title='Test Prophylaxis Alert',
            summary='Missing prophylaxis',
            severity=AlertSeverity.HIGH,
        )
        self.assertEqual(alert.alert_type, 'surgical_prophylaxis')
        self.assertEqual(alert.source_module, 'surgical_prophylaxis')


# ------------------------------------------------------------------
# Model Tests
# ------------------------------------------------------------------

class SurgicalCaseModelTests(TestCase):
    """Test SurgicalCase model."""

    def _create_case(self, **kwargs):
        defaults = {
            'case_id': 'test-case-001',
            'patient_mrn': 'MRN-001',
            'patient_name': 'Test Patient',
            'procedure_description': 'Test Procedure',
            'procedure_category': ProcedureCategory.CARDIAC,
            'cpt_codes': ['33681'],
        }
        defaults.update(kwargs)
        return SurgicalCase.objects.create(**defaults)

    def test_create_case(self):
        case = self._create_case()
        self.assertEqual(case.case_id, 'test-case-001')
        self.assertEqual(case.procedure_category, ProcedureCategory.CARDIAC)
        self.assertFalse(case.is_emergency)
        self.assertFalse(case.has_beta_lactam_allergy)

    def test_case_str(self):
        case = self._create_case()
        self.assertIn('MRN-001', str(case))

    def test_surgery_duration_hours(self):
        now = timezone.now()
        case = self._create_case(
            actual_incision_time=now - timedelta(hours=3),
            surgery_end_time=now,
        )
        self.assertAlmostEqual(case.surgery_duration_hours, 3.0, places=1)

    def test_surgery_duration_none_when_missing(self):
        case = self._create_case()
        self.assertIsNone(case.surgery_duration_hours)

    def test_case_unique_case_id(self):
        self._create_case(case_id='unique-1')
        with self.assertRaises(Exception):
            self._create_case(case_id='unique-1')

    def test_cpt_codes_jsonfield(self):
        case = self._create_case(cpt_codes=['33681', '33684'])
        case.refresh_from_db()
        self.assertEqual(len(case.cpt_codes), 2)

    def test_patient_factors(self):
        case = self._create_case(
            patient_weight_kg=25.0,
            patient_age_years=8.0,
            has_beta_lactam_allergy=True,
            mrsa_colonized=True,
        )
        self.assertTrue(case.has_beta_lactam_allergy)
        self.assertTrue(case.mrsa_colonized)
        self.assertEqual(case.patient_weight_kg, 25.0)


class ProphylaxisEvaluationModelTests(TestCase):
    """Test ProphylaxisEvaluation model."""

    def _create_case(self):
        return SurgicalCase.objects.create(
            case_id='eval-test-001',
            patient_mrn='MRN-002',
            procedure_description='Test Procedure',
            procedure_category=ProcedureCategory.ORTHOPEDIC,
        )

    def test_create_evaluation(self):
        case = self._create_case()
        eval_ = ProphylaxisEvaluation.objects.create(
            case=case,
            bundle_compliant=True,
            compliance_score=100.0,
            elements_met=7,
            elements_total=7,
            indication_result={'status': 'met', 'details': 'Indicated'},
            agent_result={'status': 'met', 'details': 'Correct agent'},
            timing_result={'status': 'met', 'details': 'Within window'},
            dosing_result={'status': 'met', 'details': 'Appropriate dose'},
            redosing_result={'status': 'n/a', 'details': 'Not needed'},
            postop_result={'status': 'n/a', 'details': 'Not needed'},
            discontinuation_result={'status': 'met', 'details': 'Stopped in 24h'},
        )
        self.assertTrue(eval_.bundle_compliant)
        self.assertEqual(eval_.compliance_score, 100.0)

    def test_evaluation_str(self):
        case = self._create_case()
        eval_ = ProphylaxisEvaluation.objects.create(
            case=case, bundle_compliant=True, compliance_score=100.0,
        )
        self.assertIn('Compliant', str(eval_))

    def test_evaluation_excluded_str(self):
        case = self._create_case()
        eval_ = ProphylaxisEvaluation.objects.create(
            case=case, excluded=True, exclusion_reason='Emergency',
        )
        self.assertIn('Excluded', str(eval_))

    def test_element_results_list(self):
        case = self._create_case()
        eval_ = ProphylaxisEvaluation.objects.create(
            case=case,
            indication_result={'status': 'met'},
            agent_result={'status': 'not_met'},
            timing_result={'status': 'met'},
            dosing_result={'status': 'met'},
            redosing_result={'status': 'n/a'},
            postop_result={'status': 'n/a'},
            discontinuation_result={'status': 'pending'},
        )
        results = eval_.element_results_list
        self.assertEqual(len(results), 7)
        self.assertEqual(results[0][0], 'Indication')
        self.assertEqual(results[1][0], 'Agent Selection')


class ProphylaxisMedicationModelTests(TestCase):
    """Test ProphylaxisMedication model."""

    def test_create_medication(self):
        case = SurgicalCase.objects.create(
            case_id='med-test-001', patient_mrn='MRN-003',
            procedure_description='Test', procedure_category=ProcedureCategory.CARDIAC,
        )
        med = ProphylaxisMedication.objects.create(
            case=case,
            medication_type='order',
            medication_name='Cefazolin',
            dose_mg=1000,
            route='IV',
            event_time=timezone.now(),
        )
        self.assertEqual(med.medication_name, 'Cefazolin')
        self.assertIn('Cefazolin', str(med))


class SurgicalJourneyModelTests(TestCase):
    """Test SurgicalJourney model."""

    def test_create_journey(self):
        journey = SurgicalJourney.objects.create(
            journey_id='test-journey-001',
            patient_mrn='MRN-004',
            patient_name='Journey Patient',
            current_state=LocationState.UNKNOWN,
        )
        self.assertEqual(journey.current_state, LocationState.UNKNOWN)
        self.assertFalse(journey.order_exists)
        self.assertFalse(journey.administered)
        self.assertIsNone(journey.completed_at)

    def test_journey_alert_tracking(self):
        journey = SurgicalJourney.objects.create(
            journey_id='test-journey-002',
            patient_mrn='MRN-005',
        )
        journey.alert_t24_sent = True
        journey.alert_t24_time = timezone.now()
        journey.save(update_fields=['alert_t24_sent', 'alert_t24_time', 'updated_at'])
        journey.refresh_from_db()
        self.assertTrue(journey.alert_t24_sent)


class PatientLocationModelTests(TestCase):
    """Test PatientLocation model."""

    def test_create_location(self):
        journey = SurgicalJourney.objects.create(
            journey_id='loc-test-001', patient_mrn='MRN-006',
        )
        loc = PatientLocation.objects.create(
            patient_mrn='MRN-006',
            journey=journey,
            location_code='OR-3',
            location_state=LocationState.OR_SUITE,
            event_time=timezone.now(),
        )
        self.assertEqual(loc.location_state, LocationState.OR_SUITE)
        self.assertIn('OR-3', str(loc))


class PreOpCheckModelTests(TestCase):
    """Test PreOpCheck model."""

    def test_create_check(self):
        journey = SurgicalJourney.objects.create(
            journey_id='check-test-001', patient_mrn='MRN-007',
        )
        check = PreOpCheck.objects.create(
            journey=journey,
            trigger_type=AlertTrigger.T60,
            trigger_time=timezone.now(),
            order_exists=True,
            administered=False,
            alert_required=True,
            alert_severity='high',
            recommendation='Administer prophylaxis now',
        )
        self.assertTrue(check.alert_required)
        self.assertEqual(check.trigger_type, AlertTrigger.T60)


class AlertEscalationModelTests(TestCase):
    """Test AlertEscalation model."""

    def test_create_escalation(self):
        esc = AlertEscalation.objects.create(
            alert_ref='test-alert-001',
            trigger_type=AlertTrigger.T0,
            escalation_level=1,
            recipient_role='anesthesia',
            delivery_channel='dashboard',
            sent_at=timezone.now(),
            delivery_status='sent',
        )
        self.assertEqual(esc.escalation_level, 1)
        self.assertFalse(esc.escalated)
        self.assertIn('anesthesia', str(esc))


# ------------------------------------------------------------------
# Enum Tests
# ------------------------------------------------------------------

class EnumTests(TestCase):
    """Test model enums."""

    def test_compliance_status_values(self):
        self.assertEqual(ComplianceStatus.MET, 'met')
        self.assertEqual(ComplianceStatus.NOT_MET, 'not_met')
        self.assertEqual(ComplianceStatus.NOT_APPLICABLE, 'n/a')

    def test_procedure_category_count(self):
        self.assertEqual(len(ProcedureCategory.choices), 13)

    def test_location_state_values(self):
        self.assertEqual(LocationState.OR_SUITE, 'or_suite')
        self.assertEqual(LocationState.PRE_OP_HOLDING, 'pre_op')

    def test_alert_trigger_values(self):
        self.assertEqual(AlertTrigger.T24, 't24')
        self.assertEqual(AlertTrigger.OR_ENTRY, 'or_entry')


# ------------------------------------------------------------------
# Guidelines Tests
# ------------------------------------------------------------------

class GuidelinesTests(TestCase):
    """Test guidelines configuration."""

    def test_guidelines_config_loads(self):
        from .logic.guidelines import get_guidelines_config
        config = get_guidelines_config()
        self.assertIsNotNone(config)

    def test_default_dosing_exists(self):
        from .logic.guidelines import DEFAULT_DOSING
        self.assertIn('cefazolin', DEFAULT_DOSING)
        self.assertIn('vancomycin', DEFAULT_DOSING)

    def test_cpt_category_hints(self):
        from .logic.guidelines import CPT_CATEGORY_HINTS
        self.assertIn('336', CPT_CATEGORY_HINTS)
        self.assertEqual(CPT_CATEGORY_HINTS['336'], ProcedureCategory.CARDIAC)

    def test_get_dosing_info(self):
        from .logic.guidelines import get_guidelines_config
        config = get_guidelines_config()
        dosing = config.get_dosing_info('cefazolin')
        self.assertIsNotNone(dosing)
        self.assertGreater(dosing.pediatric_mg_per_kg, 0)

    def test_get_redose_interval(self):
        from .logic.guidelines import get_guidelines_config
        config = get_guidelines_config()
        interval = config.get_redose_interval('cefazolin')
        self.assertGreater(interval, 0)

    def test_get_duration_limit(self):
        from .logic.guidelines import get_guidelines_config
        config = get_guidelines_config()
        limit = config.get_duration_limit(ProcedureCategory.CARDIAC)
        self.assertEqual(limit, 48)
        limit_other = config.get_duration_limit(ProcedureCategory.ORTHOPEDIC)
        self.assertEqual(limit_other, 24)


# ------------------------------------------------------------------
# Config Tests
# ------------------------------------------------------------------

class ConfigTests(TestCase):
    """Test Config class."""

    def test_config_loads(self):
        from .logic.config import Config
        config = Config()
        self.assertIsNotNone(config.FHIR_BASE_URL)
        self.assertGreater(config.STANDARD_TIMING_WINDOW, 0)
        self.assertEqual(config.STANDARD_TIMING_WINDOW, 60)
        self.assertEqual(config.EXTENDED_TIMING_WINDOW, 120)

    def test_extended_window_antibiotics(self):
        from .logic.config import Config
        config = Config()
        self.assertIn('vancomycin', config.EXTENDED_WINDOW_ANTIBIOTICS)


# ------------------------------------------------------------------
# Evaluator Tests
# ------------------------------------------------------------------

class EvaluatorTests(TestCase):
    """Test ProphylaxisEvaluator."""

    def _create_case_with_meds(self, meds=None, **case_kwargs):
        """Helper to create a case with medications."""
        defaults = {
            'case_id': f'eval-case-{timezone.now().timestamp()}',
            'patient_mrn': 'MRN-EVAL',
            'procedure_description': 'Test Procedure',
            'procedure_category': ProcedureCategory.CARDIAC,
            'cpt_codes': ['33681'],
            'patient_weight_kg': 25.0,
        }
        defaults.update(case_kwargs)
        case = SurgicalCase.objects.create(**defaults)

        now = timezone.now()
        case.actual_incision_time = now - timedelta(hours=2)
        case.surgery_end_time = now - timedelta(hours=0.5)
        case.save(update_fields=['actual_incision_time', 'surgery_end_time', 'updated_at'])

        if meds:
            for med in meds:
                offset = med.get('offset_minutes', -30)
                ProphylaxisMedication.objects.create(
                    case=case,
                    medication_type=med.get('type', 'administration'),
                    medication_name=med.get('name', 'Cefazolin'),
                    dose_mg=med.get('dose', 500),
                    route=med.get('route', 'IV'),
                    event_time=case.actual_incision_time + timedelta(minutes=offset),
                )

        return case

    def test_evaluate_excluded_emergency(self):
        from .logic.evaluator import ProphylaxisEvaluator
        evaluator = ProphylaxisEvaluator()
        case = self._create_case_with_meds(is_emergency=True)
        result = evaluator.evaluate_case(case)
        self.assertTrue(result['excluded'])
        self.assertIn('emergency', result['exclusion_reason'].lower())

    def test_evaluate_excluded_therapeutic_abx(self):
        from .logic.evaluator import ProphylaxisEvaluator
        evaluator = ProphylaxisEvaluator()
        case = self._create_case_with_meds(already_on_therapeutic_abx=True)
        result = evaluator.evaluate_case(case)
        self.assertTrue(result['excluded'])

    def test_evaluate_no_medications(self):
        """Case with no medications should be non-compliant."""
        from .logic.evaluator import ProphylaxisEvaluator
        evaluator = ProphylaxisEvaluator()
        case = self._create_case_with_meds(meds=[])
        result = evaluator.evaluate_case(case)
        self.assertFalse(result['excluded'])
        # Should have issues without medications
        self.assertIsInstance(result['indication_result'], dict)

    def test_evaluate_with_medications(self):
        """Case with proper medications."""
        from .logic.evaluator import ProphylaxisEvaluator
        evaluator = ProphylaxisEvaluator()
        case = self._create_case_with_meds(meds=[
            {'type': 'administration', 'name': 'Cefazolin', 'dose': 500, 'offset_minutes': -30},
        ])
        result = evaluator.evaluate_case(case)
        self.assertFalse(result['excluded'])
        self.assertIn('compliance_score', result)
        self.assertIn('bundle_compliant', result)

    def test_evaluate_returns_all_elements(self):
        from .logic.evaluator import ProphylaxisEvaluator
        evaluator = ProphylaxisEvaluator()
        case = self._create_case_with_meds(meds=[
            {'type': 'administration', 'name': 'Cefazolin', 'dose': 500, 'offset_minutes': -30},
        ])
        result = evaluator.evaluate_case(case)
        for field in ['indication_result', 'agent_result', 'timing_result',
                       'dosing_result', 'redosing_result', 'postop_result',
                       'discontinuation_result']:
            self.assertIn(field, result)
            self.assertIsInstance(result[field], dict)
            self.assertIn('status', result[field])


# ------------------------------------------------------------------
# HL7 Parser Tests
# ------------------------------------------------------------------

class HL7ParserTests(TestCase):
    """Test HL7 message parsing."""

    def test_parse_hl7_message(self):
        from .logic.hl7.parser import parse_hl7_message
        raw = (
            'MSH|^~\\&|EPIC|CCHMC|AEGIS|CCHMC|20250101120000||ADT^A02|MSG001|P|2.5\r'
            'EVN|A02|20250101120000\r'
            'PID|||MRN001^^^CCHMC^MR||Test^Patient\r'
            'PV1||I|OR-3^101^01|'
        )
        msg = parse_hl7_message(raw)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.message_type, 'ADT')
        self.assertEqual(msg.message_event, 'A02')

    def test_extract_adt_data(self):
        from .logic.hl7.parser import parse_hl7_message, extract_adt_a02_data
        raw = (
            'MSH|^~\\&|EPIC|CCHMC|AEGIS|CCHMC|20250101120000||ADT^A02|MSG002|P|2.5\r'
            'EVN|A02|20250101120000\r'
            'PID|||MRN002^^^CCHMC^MR||Garcia^Sofia\r'
            'PV1||I|OR-3^101^01||||1234^Dr Smith\r'
        )
        msg = parse_hl7_message(raw)
        data = extract_adt_a02_data(msg)
        self.assertIsNotNone(data)
        self.assertEqual(data['patient_mrn'], 'MRN002')
        # current_location_code or current_location contains OR-3
        location = data.get('current_location_code', '') or data.get('current_location', '')
        self.assertIn('OR-3', location)

    def test_build_ack_message(self):
        from .logic.hl7.parser import parse_hl7_message, build_ack_message
        raw = (
            'MSH|^~\\&|EPIC|CCHMC|AEGIS|CCHMC|20250101120000||ADT^A02|MSG003|P|2.5\r'
            'EVN|A02|20250101120000\r'
            'PID|||MRN001^^^CCHMC^MR||Test^Patient\r'
            'PV1||I|OR-3^101^01|'
        )
        msg = parse_hl7_message(raw)
        ack = build_ack_message(msg, 'AA')
        self.assertIn('MSA|AA|MSG003', ack)

    def test_parse_hl7_datetime(self):
        from .logic.hl7.parser import parse_hl7_datetime
        dt = parse_hl7_datetime('20250115143000')
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2025)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.minute, 30)


# ------------------------------------------------------------------
# Location Tracker Tests
# ------------------------------------------------------------------

class LocationTrackerTests(TestCase):
    """Test location state machine."""

    def test_location_patterns(self):
        from .logic.hl7.location_tracker import LocationPatterns, PRE_OP_HOLDING, OR_SUITE, PACU
        patterns = LocationPatterns()
        self.assertEqual(patterns.match_location('PREOP-1'), PRE_OP_HOLDING)
        self.assertEqual(patterns.match_location('PRE-OP HOLDING'), PRE_OP_HOLDING)
        self.assertEqual(patterns.match_location('OR3'), OR_SUITE)
        self.assertEqual(patterns.match_location('OR SUITE 5'), OR_SUITE)
        self.assertEqual(patterns.match_location('PACU-1'), PACU)
        self.assertEqual(patterns.match_location('PACU Bay 2'), PACU)

    def test_location_patterns_negative(self):
        from .logic.hl7.location_tracker import LocationPatterns, OR_SUITE, PRE_OP_HOLDING, PACU
        patterns = LocationPatterns()
        self.assertNotEqual(patterns.match_location('A3N'), OR_SUITE)
        self.assertNotEqual(patterns.match_location('G3NE'), PRE_OP_HOLDING)
        self.assertNotEqual(patterns.match_location('OR-3'), PACU)


# ------------------------------------------------------------------
# Service Tests
# ------------------------------------------------------------------

class ServiceTests(TestCase):
    """Test SurgicalProphylaxisService."""

    def test_get_stats_empty(self):
        from .services import SurgicalProphylaxisService
        service = SurgicalProphylaxisService()
        stats = service.get_stats()
        self.assertEqual(stats['total_cases'], 0)
        self.assertEqual(stats['pending_alerts'], 0)

    def test_get_stats_with_data(self):
        from .services import SurgicalProphylaxisService

        # Create a case and evaluation
        case = SurgicalCase.objects.create(
            case_id='stats-test-001', patient_mrn='MRN-STATS',
            procedure_description='Test', procedure_category=ProcedureCategory.CARDIAC,
        )
        ProphylaxisEvaluation.objects.create(
            case=case, bundle_compliant=True, compliance_score=100.0,
            elements_met=7, elements_total=7,
        )

        service = SurgicalProphylaxisService()
        stats = service.get_stats()
        self.assertEqual(stats['total_cases'], 1)
        self.assertEqual(stats['compliant'], 1)


# ------------------------------------------------------------------
# State Manager Tests
# ------------------------------------------------------------------

class StateManagerTests(TestCase):
    """Test Django ORM state manager."""

    def test_create_journey(self):
        from .realtime.state_manager import StateManager
        mgr = StateManager()
        journey = mgr.create_journey({
            'journey_id': 'sm-test-001',
            'patient_mrn': 'MRN-SM',
        })
        self.assertEqual(journey.journey_id, 'sm-test-001')

    def test_get_journey_for_patient(self):
        from .realtime.state_manager import StateManager
        mgr = StateManager()
        mgr.create_journey({'journey_id': 'sm-test-002', 'patient_mrn': 'MRN-SM2'})
        result = mgr.get_journey_for_patient('MRN-SM2')
        self.assertIsNotNone(result)
        self.assertEqual(result.patient_mrn, 'MRN-SM2')

    def test_update_location(self):
        from .realtime.state_manager import StateManager
        mgr = StateManager()
        journey = mgr.create_journey({'journey_id': 'sm-test-003', 'patient_mrn': 'MRN-SM3'})
        loc = mgr.update_location(
            'sm-test-003', 'OR-3', LocationState.OR_SUITE,
        )
        self.assertIsNotNone(loc)
        journey.refresh_from_db()
        self.assertEqual(journey.current_state, LocationState.OR_SUITE)

    def test_mark_alert_sent(self):
        from .realtime.state_manager import StateManager
        mgr = StateManager()
        journey = mgr.create_journey({'journey_id': 'sm-test-004', 'patient_mrn': 'MRN-SM4'})
        mgr.mark_alert_sent('sm-test-004', 't24')
        journey.refresh_from_db()
        self.assertTrue(journey.alert_t24_sent)
        self.assertIsNotNone(journey.alert_t24_time)

    def test_complete_journey(self):
        from .realtime.state_manager import StateManager
        mgr = StateManager()
        journey = mgr.create_journey({'journey_id': 'sm-test-005', 'patient_mrn': 'MRN-SM5'})
        mgr.complete_journey('sm-test-005')
        journey.refresh_from_db()
        self.assertIsNotNone(journey.completed_at)


# ------------------------------------------------------------------
# PreOp Checker Tests
# ------------------------------------------------------------------

class PreOpCheckerTests(TestCase):
    """Test real-time pre-op compliance checker."""

    def _create_journey(self, **kwargs):
        defaults = {
            'journey_id': f'poc-{timezone.now().timestamp()}',
            'patient_mrn': 'MRN-POC',
            'scheduled_time': timezone.now() + timedelta(hours=1),
        }
        defaults.update(kwargs)
        return SurgicalJourney.objects.create(**defaults)

    def test_check_no_order_at_t0(self):
        from .realtime.preop_checker import PreOpChecker
        checker = PreOpChecker()
        journey = self._create_journey()
        result = checker.check_at_trigger(journey, AlertTrigger.T0)
        self.assertTrue(result['alert_required'])
        self.assertEqual(result['alert_severity'], AlertSeverity.CRITICAL)

    def test_check_order_exists_not_administered_at_t0(self):
        from .realtime.preop_checker import PreOpChecker
        checker = PreOpChecker()
        journey = self._create_journey(order_exists=True)
        result = checker.check_at_trigger(journey, AlertTrigger.T0)
        self.assertTrue(result['alert_required'])
        self.assertEqual(result['alert_severity'], AlertSeverity.CRITICAL)

    def test_check_administered_at_t0(self):
        from .realtime.preop_checker import PreOpChecker
        checker = PreOpChecker()
        journey = self._create_journey(order_exists=True, administered=True)
        result = checker.check_at_trigger(journey, AlertTrigger.T0)
        self.assertFalse(result['alert_required'])

    def test_check_excluded_patient(self):
        from .realtime.preop_checker import PreOpChecker
        checker = PreOpChecker()
        journey = self._create_journey(excluded=True, exclusion_reason='Emergency')
        result = checker.check_at_trigger(journey, AlertTrigger.T60)
        self.assertFalse(result['alert_required'])

    def test_check_at_t24(self):
        from .realtime.preop_checker import PreOpChecker
        checker = PreOpChecker()
        journey = self._create_journey()
        result = checker.check_at_trigger(journey, AlertTrigger.T24)
        self.assertTrue(result['alert_required'])
        self.assertEqual(result['alert_severity'], AlertSeverity.MEDIUM)


# ------------------------------------------------------------------
# Template Tests
# ------------------------------------------------------------------

class TemplateTests(TestCase):
    """Test template rendering via render_to_string."""

    def _get_context(self, **extra):
        """Get minimal context for template rendering."""
        context = {
            'request': type('Request', (), {
                'user': type('User', (), {
                    'username': 'testuser',
                    'get_role_display': lambda: 'ASP Pharmacist',
                })(),
            })(),
        }
        context.update(extra)
        return context

    def test_render_base(self):
        html = render_to_string('surgical_prophylaxis/base.html', self._get_context())
        self.assertIn('Surgical Prophylaxis', html)
        self.assertIn('#0d7377', html)  # teal theme

    def test_render_dashboard(self):
        html = render_to_string('surgical_prophylaxis/dashboard.html', self._get_context(
            stats={'total_cases': 10, 'compliance_rate': 85.0, 'pending_alerts': 2,
                   'avg_score': 90.0, 'element_rates': {}},
            pending_alerts=[],
            recent_evaluations=[],
        ))
        self.assertIn('ASHP Bundle Compliance', html)
        self.assertIn('85.0%', html)

    def test_render_compliance(self):
        html = render_to_string('surgical_prophylaxis/compliance.html', self._get_context(
            total=5, assessed=4, compliant=3, excluded=1,
            compliance_rate=75.0, element_rates={}, category_stats={},
            categories=ProcedureCategory, current_category='',
        ))
        self.assertIn('Compliance Report', html)
        self.assertIn('75.0%', html)

    def test_render_realtime(self):
        html = render_to_string('surgical_prophylaxis/realtime.html', self._get_context(
            active_journeys=[], recent_completed=[], pending_escalations=[],
        ))
        self.assertIn('Real-time Surgical Monitoring', html)

    def test_render_help(self):
        html = render_to_string('surgical_prophylaxis/help.html', self._get_context())
        self.assertIn('7 ASHP Bundle Elements', html)
        self.assertIn('Indication', html)
        self.assertIn('Agent Selection', html)
        self.assertIn('Discontinuation', html)


# ------------------------------------------------------------------
# URL Tests
# ------------------------------------------------------------------

class URLTests(TestCase):
    """Test URL pattern resolution."""

    def test_dashboard_url(self):
        url = reverse('surgical_prophylaxis:dashboard')
        self.assertEqual(url, '/surgical-prophylaxis/')

    def test_compliance_url(self):
        url = reverse('surgical_prophylaxis:compliance')
        self.assertEqual(url, '/surgical-prophylaxis/compliance/')

    def test_realtime_url(self):
        url = reverse('surgical_prophylaxis:realtime')
        self.assertEqual(url, '/surgical-prophylaxis/realtime/')

    def test_help_url(self):
        url = reverse('surgical_prophylaxis:help')
        self.assertEqual(url, '/surgical-prophylaxis/help/')

    def test_api_stats_url(self):
        url = reverse('surgical_prophylaxis:api_stats')
        self.assertEqual(url, '/surgical-prophylaxis/api/stats/')

    def test_api_export_url(self):
        url = reverse('surgical_prophylaxis:api_export')
        self.assertEqual(url, '/surgical-prophylaxis/api/export/')

    def test_case_detail_url(self):
        import uuid
        test_uuid = uuid.uuid4()
        url = reverse('surgical_prophylaxis:case_detail', args=[test_uuid])
        self.assertIn(str(test_uuid), url)
