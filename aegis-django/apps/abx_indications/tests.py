"""
Tests for ABX Indication Monitoring module.

Tests cover:
- Model creation and properties
- Service layer (stats, alert determination, auto-accept)
- Template rendering
- Alert type integration
- Taxonomy and guidelines logic
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.template.loader import render_to_string

from apps.alerts.models import (
    Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity,
)

from .models import (
    IndicationCandidate, IndicationReview, IndicationLLMAuditLog,
    CandidateStatus, SyndromeConfidence, TherapyIntent,
    AgentCategoryChoice, SyndromeDecision, AgentDecision,
)


class AlertTypeTests(TestCase):
    """Verify ABX indication alert types exist."""

    def test_abx_no_indication_exists(self):
        self.assertEqual(AlertType.ABX_NO_INDICATION, 'abx_no_indication')

    def test_abx_never_appropriate_exists(self):
        self.assertEqual(AlertType.ABX_NEVER_APPROPRIATE, 'abx_never_appropriate')

    def test_abx_off_guideline_exists(self):
        self.assertEqual(AlertType.ABX_OFF_GUIDELINE, 'abx_off_guideline')

    def test_create_abx_alert(self):
        alert = Alert.objects.create(
            alert_type=AlertType.ABX_NO_INDICATION,
            source_module='abx_indications',
            source_id='test-1',
            title='Test ABX Alert',
            summary='No indication documented',
            severity=AlertSeverity.HIGH,
        )
        self.assertEqual(alert.alert_type, 'abx_no_indication')
        self.assertEqual(alert.get_alert_type_display(), 'ABX: No Indication Documented')


class IndicationCandidateModelTests(TestCase):
    """Test IndicationCandidate model."""

    def _create_candidate(self, **kwargs):
        """Helper to create a candidate with defaults."""
        defaults = {
            'patient_id': 'fhir-patient-001',
            'patient_mrn': 'MRN-001',
            'patient_name': 'Test Patient',
            'patient_location': 'G3NE - PICU',
            'medication_request_id': f'med-req-{kwargs.get("medication_request_id", "001")}',
            'medication_name': 'Meropenem',
            'rxnorm_code': '29561',
            'order_date': timezone.now(),
            'location': 'G3NE - PICU',
            'service': 'PICU',
            'clinical_syndrome': 'sepsis',
            'clinical_syndrome_display': 'Sepsis',
            'syndrome_category': 'bloodstream',
            'syndrome_confidence': SyndromeConfidence.DEFINITE,
            'therapy_intent': TherapyIntent.EMPIRIC,
        }
        defaults.update(kwargs)
        return IndicationCandidate.objects.create(**defaults)

    def test_create_candidate(self):
        candidate = self._create_candidate()
        self.assertIsNotNone(candidate.id)
        self.assertEqual(candidate.medication_name, 'Meropenem')
        self.assertEqual(candidate.status, CandidateStatus.PENDING)

    def test_unique_medication_request_id(self):
        self._create_candidate(medication_request_id='unique-001')
        with self.assertRaises(Exception):
            self._create_candidate(medication_request_id='unique-001')

    def test_has_red_flag_false(self):
        candidate = self._create_candidate()
        self.assertFalse(candidate.has_red_flag)

    def test_has_red_flag_indication_not_documented(self):
        candidate = self._create_candidate(
            medication_request_id='red-1',
            indication_not_documented=True,
        )
        self.assertTrue(candidate.has_red_flag)

    def test_has_red_flag_likely_viral(self):
        candidate = self._create_candidate(
            medication_request_id='red-2',
            likely_viral=True,
        )
        self.assertTrue(candidate.has_red_flag)

    def test_has_red_flag_never_appropriate(self):
        candidate = self._create_candidate(
            medication_request_id='red-3',
            never_appropriate=True,
        )
        self.assertTrue(candidate.has_red_flag)

    def test_has_red_flag_asb(self):
        candidate = self._create_candidate(
            medication_request_id='red-4',
            asymptomatic_bacteriuria=True,
        )
        self.assertTrue(candidate.has_red_flag)

    def test_latest_review_none(self):
        candidate = self._create_candidate()
        self.assertIsNone(candidate.latest_review)

    def test_latest_review_returns_most_recent(self):
        candidate = self._create_candidate()
        review1 = IndicationReview.objects.create(
            candidate=candidate,
            syndrome_decision=SyndromeDecision.CONFIRM_SYNDROME,
        )
        review2 = IndicationReview.objects.create(
            candidate=candidate,
            syndrome_decision=SyndromeDecision.CORRECT_SYNDROME,
            confirmed_syndrome='cap',
            confirmed_syndrome_display='Community-Acquired Pneumonia',
        )
        latest = candidate.latest_review
        self.assertEqual(latest.id, review2.id)

    def test_str_representation(self):
        candidate = self._create_candidate()
        s = str(candidate)
        self.assertIn('Meropenem', s)
        self.assertIn('MRN-001', s)
        self.assertIn('Sepsis', s)

    def test_default_json_fields(self):
        candidate = self._create_candidate()
        self.assertEqual(candidate.supporting_evidence, [])
        self.assertEqual(candidate.evidence_quotes, [])
        self.assertEqual(candidate.guideline_disease_ids, [])

    def test_ordering(self):
        """Candidates are ordered by -created_at."""
        c1 = self._create_candidate(medication_request_id='order-1')
        c2 = self._create_candidate(medication_request_id='order-2')
        candidates = list(IndicationCandidate.objects.all())
        # Most recent first
        self.assertEqual(candidates[0].id, c2.id)
        self.assertEqual(candidates[1].id, c1.id)


class IndicationReviewModelTests(TestCase):
    """Test IndicationReview model."""

    def setUp(self):
        self.candidate = IndicationCandidate.objects.create(
            patient_id='fhir-patient-review',
            patient_mrn='MRN-REV-001',
            patient_name='Review Patient',
            patient_location='A6N',
            medication_request_id='med-req-review-001',
            medication_name='Ceftriaxone',
            order_date=timezone.now(),
            clinical_syndrome='cap',
            clinical_syndrome_display='Community-Acquired Pneumonia',
            syndrome_category='respiratory',
            syndrome_confidence=SyndromeConfidence.PROBABLE,
        )

    def test_create_review(self):
        review = IndicationReview.objects.create(
            candidate=self.candidate,
            syndrome_decision=SyndromeDecision.CONFIRM_SYNDROME,
            agent_decision=AgentDecision.APPROPRIATE,
        )
        self.assertIsNotNone(review.id)
        self.assertEqual(review.syndrome_decision, SyndromeDecision.CONFIRM_SYNDROME)
        self.assertIsNotNone(review.reviewed_at)

    def test_review_with_correction(self):
        review = IndicationReview.objects.create(
            candidate=self.candidate,
            syndrome_decision=SyndromeDecision.CORRECT_SYNDROME,
            confirmed_syndrome='hap',
            confirmed_syndrome_display='Hospital-Acquired Pneumonia',
            agent_decision=AgentDecision.ACCEPTABLE,
        )
        self.assertEqual(review.confirmed_syndrome, 'hap')

    def test_review_override(self):
        review = IndicationReview.objects.create(
            candidate=self.candidate,
            syndrome_decision=SyndromeDecision.CONFIRM_SYNDROME,
            agent_decision=AgentDecision.INAPPROPRIATE,
            is_override=True,
            notes='Clinical team discussed, adjusting',
        )
        self.assertTrue(review.is_override)

    def test_str_representation(self):
        review = IndicationReview.objects.create(
            candidate=self.candidate,
            syndrome_decision=SyndromeDecision.CONFIRM_SYNDROME,
        )
        s = str(review)
        self.assertIn('System', s)  # No reviewer
        self.assertIn('Confirm Syndrome', s)


class IndicationLLMAuditLogTests(TestCase):
    """Test IndicationLLMAuditLog model."""

    def test_create_audit_log(self):
        log = IndicationLLMAuditLog.objects.create(
            model='qwen2.5:7b',
            success=True,
            input_tokens=1200,
            output_tokens=180,
            response_time_ms=850,
        )
        self.assertTrue(log.success)
        self.assertEqual(log.input_tokens, 1200)

    def test_audit_log_with_candidate(self):
        candidate = IndicationCandidate.objects.create(
            patient_id='fhir-patient-llm',
            patient_mrn='MRN-LLM-001',
            medication_request_id='med-req-llm-001',
            medication_name='Vancomycin',
            order_date=timezone.now(),
        )
        log = IndicationLLMAuditLog.objects.create(
            candidate=candidate,
            model='qwen2.5:7b',
            success=True,
            input_tokens=1000,
            output_tokens=150,
            response_time_ms=700,
        )
        self.assertEqual(candidate.llm_calls.count(), 1)

    def test_audit_log_error(self):
        log = IndicationLLMAuditLog.objects.create(
            model='qwen2.5:7b',
            success=False,
            error_message='Connection refused',
            response_time_ms=50,
        )
        self.assertFalse(log.success)
        self.assertIn('Connection', log.error_message)

    def test_str_representation(self):
        log = IndicationLLMAuditLog.objects.create(
            model='qwen2.5:7b',
            success=True,
            input_tokens=1000,
            output_tokens=200,
        )
        s = str(log)
        self.assertIn('OK', s)
        self.assertIn('1000', s)


class ServiceAlertDeterminationTests(TestCase):
    """Test IndicationMonitorService alert determination logic."""

    def setUp(self):
        # Import here to avoid circular imports at module level
        from .services import IndicationMonitorService
        # Create service without FHIR client (we won't call FHIR methods)
        self.service = IndicationMonitorService.__new__(IndicationMonitorService)

    def _create_candidate(self, **kwargs):
        defaults = {
            'patient_id': 'fhir-patient-svc',
            'patient_mrn': 'MRN-SVC-001',
            'medication_request_id': f'med-req-svc-{kwargs.get("_suffix", "001")}',
            'medication_name': 'Meropenem',
            'order_date': timezone.now(),
        }
        defaults.pop('_suffix', None)
        kwargs.pop('_suffix', None)
        defaults.update(kwargs)
        return IndicationCandidate.objects.create(**defaults)

    def test_no_alert_for_clean_candidate(self):
        candidate = self._create_candidate()
        result = self.service._determine_alert_type(candidate)
        self.assertIsNone(result)

    def test_never_appropriate_alert(self):
        candidate = self._create_candidate(
            _suffix='002',
            never_appropriate=True,
        )
        result = self.service._determine_alert_type(candidate)
        self.assertEqual(result, AlertType.ABX_NEVER_APPROPRIATE)

    def test_no_indication_alert(self):
        candidate = self._create_candidate(
            _suffix='003',
            indication_not_documented=True,
        )
        result = self.service._determine_alert_type(candidate)
        self.assertEqual(result, AlertType.ABX_NO_INDICATION)

    def test_likely_viral_alert(self):
        candidate = self._create_candidate(
            _suffix='004',
            likely_viral=True,
        )
        result = self.service._determine_alert_type(candidate)
        self.assertEqual(result, AlertType.ABX_NEVER_APPROPRIATE)

    def test_asb_alert(self):
        candidate = self._create_candidate(
            _suffix='005',
            asymptomatic_bacteriuria=True,
        )
        result = self.service._determine_alert_type(candidate)
        self.assertEqual(result, AlertType.ABX_NEVER_APPROPRIATE)

    def test_off_guideline_alert(self):
        candidate = self._create_candidate(
            _suffix='006',
            cchmc_agent_category=AgentCategoryChoice.OFF_GUIDELINE,
        )
        result = self.service._determine_alert_type(candidate)
        self.assertEqual(result, AlertType.ABX_OFF_GUIDELINE)

    def test_first_line_no_alert(self):
        candidate = self._create_candidate(
            _suffix='007',
            cchmc_agent_category=AgentCategoryChoice.FIRST_LINE,
        )
        result = self.service._determine_alert_type(candidate)
        self.assertIsNone(result)

    def test_alternative_no_alert(self):
        candidate = self._create_candidate(
            _suffix='008',
            cchmc_agent_category=AgentCategoryChoice.ALTERNATIVE,
        )
        result = self.service._determine_alert_type(candidate)
        self.assertIsNone(result)

    def test_never_appropriate_takes_priority(self):
        """never_appropriate overrides indication_not_documented."""
        candidate = self._create_candidate(
            _suffix='009',
            never_appropriate=True,
            indication_not_documented=True,
        )
        result = self.service._determine_alert_type(candidate)
        self.assertEqual(result, AlertType.ABX_NEVER_APPROPRIATE)


class ServiceStatsTests(TestCase):
    """Test IndicationMonitorService.get_stats()."""

    def setUp(self):
        # Create test candidates
        self.c_pending = IndicationCandidate.objects.create(
            patient_id='fhir-stats-1',
            patient_mrn='MRN-STATS-001',
            medication_request_id='med-req-stats-001',
            medication_name='Meropenem',
            order_date=timezone.now(),
            status=CandidateStatus.PENDING,
            syndrome_category='bloodstream',
            cchmc_agent_category=AgentCategoryChoice.FIRST_LINE,
        )
        self.c_alerted = IndicationCandidate.objects.create(
            patient_id='fhir-stats-2',
            patient_mrn='MRN-STATS-002',
            medication_request_id='med-req-stats-002',
            medication_name='Ceftriaxone',
            order_date=timezone.now(),
            status=CandidateStatus.ALERTED,
            syndrome_category='respiratory',
            indication_not_documented=True,
        )
        self.c_reviewed = IndicationCandidate.objects.create(
            patient_id='fhir-stats-3',
            patient_mrn='MRN-STATS-003',
            medication_request_id='med-req-stats-003',
            medication_name='Vancomycin',
            order_date=timezone.now(),
            status=CandidateStatus.REVIEWED,
        )
        self.c_auto = IndicationCandidate.objects.create(
            patient_id='fhir-stats-4',
            patient_mrn='MRN-STATS-004',
            medication_request_id='med-req-stats-004',
            medication_name='Cefepime',
            order_date=timezone.now(),
            status=CandidateStatus.AUTO_ACCEPTED,
        )

    def test_get_stats(self):
        from .services import IndicationMonitorService
        service = IndicationMonitorService.__new__(IndicationMonitorService)
        stats = service.get_stats()

        self.assertEqual(stats['total_candidates'], 4)
        self.assertEqual(stats['active_count'], 2)  # pending + alerted
        self.assertEqual(stats['pending_count'], 1)
        self.assertEqual(stats['alerted_count'], 1)
        self.assertEqual(stats['auto_accepted'], 1)

    def test_red_flag_counts(self):
        from .services import IndicationMonitorService
        service = IndicationMonitorService.__new__(IndicationMonitorService)
        stats = service.get_stats()

        self.assertEqual(stats['red_flags']['no_indication'], 1)
        self.assertEqual(stats['red_flags']['likely_viral'], 0)

    def test_by_category(self):
        from .services import IndicationMonitorService
        service = IndicationMonitorService.__new__(IndicationMonitorService)
        stats = service.get_stats()

        self.assertIn('bloodstream', stats['by_category'])
        self.assertIn('respiratory', stats['by_category'])

    def test_by_medication(self):
        from .services import IndicationMonitorService
        service = IndicationMonitorService.__new__(IndicationMonitorService)
        stats = service.get_stats()

        self.assertIn('Meropenem', stats['by_medication'])
        self.assertIn('Ceftriaxone', stats['by_medication'])


class ServiceAutoAcceptTests(TestCase):
    """Test IndicationMonitorService.auto_accept_old()."""

    def test_auto_accept_old_candidates(self):
        """Pending candidates past threshold without red flags get auto-accepted."""
        from .services import IndicationMonitorService

        # Old candidate - should be auto-accepted
        old = IndicationCandidate.objects.create(
            patient_id='fhir-auto-1',
            patient_mrn='MRN-AUTO-001',
            medication_request_id='med-req-auto-001',
            medication_name='Meropenem',
            order_date=timezone.now() - timedelta(hours=72),
            status=CandidateStatus.PENDING,
            cchmc_agent_category=AgentCategoryChoice.FIRST_LINE,
        )
        # Force created_at to be old
        IndicationCandidate.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(hours=72)
        )

        # Recent candidate - should NOT be auto-accepted
        recent = IndicationCandidate.objects.create(
            patient_id='fhir-auto-2',
            patient_mrn='MRN-AUTO-002',
            medication_request_id='med-req-auto-002',
            medication_name='Vancomycin',
            order_date=timezone.now(),
            status=CandidateStatus.PENDING,
        )

        service = IndicationMonitorService.__new__(IndicationMonitorService)
        count = service.auto_accept_old()

        self.assertEqual(count, 1)
        old.refresh_from_db()
        self.assertEqual(old.status, CandidateStatus.AUTO_ACCEPTED)
        recent.refresh_from_db()
        self.assertEqual(recent.status, CandidateStatus.PENDING)

    def test_auto_accept_skips_red_flags(self):
        """Candidates with red flags should NOT be auto-accepted."""
        from .services import IndicationMonitorService

        flagged = IndicationCandidate.objects.create(
            patient_id='fhir-auto-3',
            patient_mrn='MRN-AUTO-003',
            medication_request_id='med-req-auto-003',
            medication_name='Ceftriaxone',
            order_date=timezone.now() - timedelta(hours=72),
            status=CandidateStatus.PENDING,
            indication_not_documented=True,
        )
        IndicationCandidate.objects.filter(pk=flagged.pk).update(
            created_at=timezone.now() - timedelta(hours=72)
        )

        service = IndicationMonitorService.__new__(IndicationMonitorService)
        count = service.auto_accept_old()

        self.assertEqual(count, 0)
        flagged.refresh_from_db()
        self.assertEqual(flagged.status, CandidateStatus.PENDING)

    def test_auto_accept_skips_off_guideline(self):
        """Off-guideline candidates should NOT be auto-accepted."""
        from .services import IndicationMonitorService

        off = IndicationCandidate.objects.create(
            patient_id='fhir-auto-4',
            patient_mrn='MRN-AUTO-004',
            medication_request_id='med-req-auto-004',
            medication_name='Ciprofloxacin',
            order_date=timezone.now() - timedelta(hours=72),
            status=CandidateStatus.PENDING,
            cchmc_agent_category=AgentCategoryChoice.OFF_GUIDELINE,
        )
        IndicationCandidate.objects.filter(pk=off.pk).update(
            created_at=timezone.now() - timedelta(hours=72)
        )

        service = IndicationMonitorService.__new__(IndicationMonitorService)
        count = service.auto_accept_old()

        self.assertEqual(count, 0)
        off.refresh_from_db()
        self.assertEqual(off.status, CandidateStatus.PENDING)


class ServiceAlertCreationTests(TestCase):
    """Test IndicationMonitorService._create_alert()."""

    def test_create_never_appropriate_alert(self):
        from .services import IndicationMonitorService

        candidate = IndicationCandidate.objects.create(
            patient_id='fhir-alert-1',
            patient_mrn='MRN-ALERT-001',
            patient_name='Alert Patient',
            patient_location='A7N',
            medication_request_id='med-req-alert-001',
            medication_name='Amoxicillin',
            order_date=timezone.now(),
            clinical_syndrome='bronchiolitis',
            clinical_syndrome_display='Bronchiolitis',
            syndrome_confidence=SyndromeConfidence.DEFINITE,
            never_appropriate=True,
        )

        service = IndicationMonitorService.__new__(IndicationMonitorService)
        alert = service._create_alert(candidate, AlertType.ABX_NEVER_APPROPRIATE)

        self.assertEqual(alert.alert_type, AlertType.ABX_NEVER_APPROPRIATE)
        self.assertEqual(alert.severity, AlertSeverity.CRITICAL)
        self.assertEqual(alert.priority_score, 95)
        self.assertIn('Never Appropriate', alert.title)
        self.assertEqual(alert.source_module, 'abx_indications')

        # Check audit log was created
        audit = AlertAudit.objects.filter(alert=alert).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.new_status, AlertStatus.PENDING)

    def test_create_no_indication_alert(self):
        from .services import IndicationMonitorService

        candidate = IndicationCandidate.objects.create(
            patient_id='fhir-alert-2',
            patient_mrn='MRN-ALERT-002',
            patient_name='Alert Patient 2',
            patient_location='A6N',
            medication_request_id='med-req-alert-002',
            medication_name='Ceftriaxone',
            order_date=timezone.now(),
            indication_not_documented=True,
        )

        service = IndicationMonitorService.__new__(IndicationMonitorService)
        alert = service._create_alert(candidate, AlertType.ABX_NO_INDICATION)

        self.assertEqual(alert.severity, AlertSeverity.HIGH)
        self.assertEqual(alert.priority_score, 85)
        self.assertIn('No Indication', alert.title)

    def test_create_off_guideline_alert(self):
        from .services import IndicationMonitorService

        candidate = IndicationCandidate.objects.create(
            patient_id='fhir-alert-3',
            patient_mrn='MRN-ALERT-003',
            patient_name='Alert Patient 3',
            patient_location='A4N',
            medication_request_id='med-req-alert-003',
            medication_name='Ciprofloxacin',
            order_date=timezone.now(),
            clinical_syndrome='uti_simple',
            clinical_syndrome_display='Uncomplicated UTI',
            syndrome_confidence=SyndromeConfidence.DEFINITE,
            cchmc_agent_category=AgentCategoryChoice.OFF_GUIDELINE,
        )

        service = IndicationMonitorService.__new__(IndicationMonitorService)
        alert = service._create_alert(candidate, AlertType.ABX_OFF_GUIDELINE)

        self.assertEqual(alert.severity, AlertSeverity.MEDIUM)
        self.assertEqual(alert.priority_score, 70)
        self.assertIn('Off Guideline', alert.title)


class TaxonomyTests(TestCase):
    """Test taxonomy module."""

    def test_taxonomy_loads(self):
        from .logic.taxonomy import INDICATION_TAXONOMY
        self.assertGreater(len(INDICATION_TAXONOMY), 40)

    def test_get_indication_by_synonym(self):
        from .logic.taxonomy import get_indication_by_synonym
        # "CAP" should map to community_acquired_pneumonia
        result = get_indication_by_synonym('CAP')
        self.assertIsNotNone(result)
        self.assertEqual(result.category.value, 'respiratory')

    def test_never_appropriate_indications(self):
        from .logic.taxonomy import get_never_appropriate_indications
        never = get_never_appropriate_indications()
        self.assertGreater(len(never), 0)
        # bronchiolitis should be never_appropriate
        bronchiolitis_ids = [m.indication_id for m in never]
        self.assertIn('bronchiolitis', bronchiolitis_ids)

    def test_get_indications_by_category(self):
        from .logic.taxonomy import get_indications_by_category, IndicationCategory
        respiratory = get_indications_by_category(IndicationCategory.RESPIRATORY)
        self.assertGreater(len(respiratory), 0)


class GuidelinesTests(TestCase):
    """Test CCHMC guidelines engine."""

    def test_engine_loads(self):
        from .logic.guidelines import CCHMCGuidelinesEngine
        engine = CCHMCGuidelinesEngine()
        self.assertTrue(len(engine.disease_guidelines) > 0)

    def test_check_agent_by_disease_ids_no_match(self):
        from .logic.guidelines import CCHMCGuidelinesEngine, AgentCategory
        engine = CCHMCGuidelinesEngine()
        result = engine.check_agent_by_disease_ids(
            disease_ids=['nonexistent_disease'],
            prescribed_agent='meropenem',
        )
        self.assertEqual(result.current_agent_category, AgentCategory.NOT_ASSESSED)

    def test_check_agent_by_disease_ids_empty(self):
        from .logic.guidelines import CCHMCGuidelinesEngine
        engine = CCHMCGuidelinesEngine()
        result = engine.check_agent_by_disease_ids(
            disease_ids=[],
            prescribed_agent='meropenem',
        )
        self.assertIn('No guideline disease IDs', result.recommendation)

    def test_agent_normalization(self):
        from .logic.guidelines import CCHMCGuidelinesEngine
        engine = CCHMCGuidelinesEngine()
        # Should normalize common agent names
        normalized = engine._normalize_agent('Augmentin')
        self.assertIn('amoxicillin', normalized)

    def test_get_dosing_recommendation(self):
        from .logic.guidelines import CCHMCGuidelinesEngine
        engine = CCHMCGuidelinesEngine()
        # Try to find dosing for a common antibiotic
        result = engine.get_dosing_recommendation('vancomycin')
        # May or may not find depending on dosing data
        if result:
            self.assertEqual(result.drug_name.lower(), 'vancomycin')


class TemplateRenderTests(TestCase):
    """Test that templates render without errors.

    Uses render_to_string() instead of test client due to UserSession
    NOT NULL ip_address constraint on force_login().
    """

    def test_base_template(self):
        html = render_to_string('abx_indications/base.html')
        self.assertIn('ABX Indication', html)

    def test_help_template(self):
        from .logic.taxonomy import INDICATION_TAXONOMY, IndicationCategory

        by_category = {}
        for key, mapping in INDICATION_TAXONOMY.items():
            cat = mapping.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append({
                'id': mapping.indication_id,
                'name': mapping.display_name,
                'never_appropriate': mapping.never_appropriate,
                'has_guidelines': bool(mapping.guideline_disease_ids),
                'notes': mapping.notes,
            })

        html = render_to_string('abx_indications/help.html', {
            'taxonomy_by_category': by_category,
            'categories': [(c.value, c.name) for c in IndicationCategory],
        })
        self.assertIn('Clinical Syndrome Taxonomy', html)
        self.assertIn('Red Flag', html)
        self.assertIn('Workflow', html)

    def test_dashboard_template(self):
        html = render_to_string('abx_indications/dashboard.html', {
            'candidates': [],
            'stats': {
                'pending_count': 5,
                'red_flag_count': 2,
                'off_guideline_count': 1,
                'reviewed_today': 3,
            },
            'categories': [],
            'medications': [],
            'current_filters': {
                'category': None,
                'agent_category': None,
                'medication': None,
            },
        })
        self.assertIn('Pending Review', html)

    def test_detail_template(self):
        candidate = IndicationCandidate.objects.create(
            patient_id='fhir-tmpl-1',
            patient_mrn='MRN-TMPL-001',
            patient_name='Template Patient',
            patient_location='G3NE - PICU',
            medication_request_id='med-req-tmpl-001',
            medication_name='Meropenem',
            order_date=timezone.now(),
            clinical_syndrome='sepsis',
            clinical_syndrome_display='Sepsis',
            syndrome_category='bloodstream',
            syndrome_confidence=SyndromeConfidence.DEFINITE,
            therapy_intent=TherapyIntent.EMPIRIC,
            supporting_evidence=['Fever', 'WBC 22k'],
            evidence_quotes=['"Started meropenem for sepsis"'],
            cchmc_agent_category=AgentCategoryChoice.FIRST_LINE,
            cchmc_disease_matched='Sepsis',
            cchmc_first_line_agents=['meropenem', 'cefepime'],
        )

        from .logic.taxonomy import INDICATION_TAXONOMY
        syndrome_choices = [
            (key, mapping.display_name, mapping.category.value)
            for key, mapping in INDICATION_TAXONOMY.items()
        ]

        html = render_to_string('abx_indications/detail.html', {
            'candidate': candidate,
            'reviews': [],
            'llm_calls': [],
            'audit_log': [],
            'resolution_reasons': [],
            'syndrome_choices': syndrome_choices,
            'syndrome_decisions': SyndromeDecision.choices,
            'agent_decisions': AgentDecision.choices,
        })
        self.assertIn('Meropenem', html)
        self.assertIn('Sepsis', html)
        self.assertIn('MRN-TMPL-001', html)

    def test_history_template(self):
        html = render_to_string('abx_indications/history.html', {
            'candidates': [],
            'days': 30,
            'current_filters': {
                'category': None,
                'agent_decision': None,
                'days': 30,
            },
        })
        self.assertIn('Reviewed Indications', html)


class URLTests(TestCase):
    """Test URL resolution."""

    def test_dashboard_url(self):
        from django.urls import reverse
        url = reverse('abx_indications:dashboard')
        self.assertEqual(url, '/abx-indications/')

    def test_detail_url(self):
        import uuid
        from django.urls import reverse
        pk = uuid.uuid4()
        url = reverse('abx_indications:detail', kwargs={'pk': pk})
        self.assertIn(str(pk), url)

    def test_history_url(self):
        from django.urls import reverse
        url = reverse('abx_indications:history')
        self.assertEqual(url, '/abx-indications/history/')

    def test_help_url(self):
        from django.urls import reverse
        url = reverse('abx_indications:help')
        self.assertEqual(url, '/abx-indications/help/')

    def test_api_stats_url(self):
        from django.urls import reverse
        url = reverse('abx_indications:api_stats')
        self.assertEqual(url, '/abx-indications/api/stats/')

    def test_api_review_url(self):
        import uuid
        from django.urls import reverse
        pk = uuid.uuid4()
        url = reverse('abx_indications:api_review', kwargs={'pk': pk})
        self.assertIn('review', url)

    def test_api_export_url(self):
        from django.urls import reverse
        url = reverse('abx_indications:api_export')
        self.assertEqual(url, '/abx-indications/api/export/')
