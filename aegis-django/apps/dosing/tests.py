"""Tests for the dosing verification module."""

from datetime import datetime, timedelta

from django.test import TestCase

from .alert_models import (
    DoseAlertSeverity,
    DoseAlertStatus,
    DoseFlagType,
    DoseFlag,
    DoseAssessment,
    DoseResolution,
)
from .data_models import MedicationOrder, PatientContext
from .rules_engine import DosingRulesEngine, BaseRuleModule
from .rules.allergy import AllergyRules, DRUG_CLASSES, CROSS_REACTIVITY_RULES
from .rules.age import AgeBasedRules, classify_age_group, AGE_BASED_RULES
from .rules.renal import RenalAdjustmentRules, RENAL_ADJUSTMENTS
from .rules.weight import (
    WeightBasedRules,
    calculate_ibw_kg,
    calculate_adjusted_weight_kg,
    calculate_bmi,
)
from .rules.route import RouteRules
from .rules.indication import IndicationRules
from .rules.interaction import DrugInteractionRules, DRUG_CLASS_MAPPINGS
from .rules.duration import DurationRules, days_on_therapy, DURATION_RULES
from .rules.extended_infusion import ExtendedInfusionRules, EXTENDED_INFUSION_DRUGS


# ---------------------------------------------------------------------------
# Helper factory functions
# ---------------------------------------------------------------------------

def _make_med(drug_name="vancomycin", dose_value=500, dose_unit="mg",
              interval="q6h", route="IV", frequency_hours=6,
              daily_dose=2000, daily_dose_per_kg=None,
              start_date="2026-01-01T08:00:00", order_id="ORD-1",
              infusion_duration_minutes=None, rxnorm_code=None):
    return MedicationOrder(
        drug_name=drug_name,
        dose_value=dose_value,
        dose_unit=dose_unit,
        interval=interval,
        route=route,
        frequency_hours=frequency_hours,
        daily_dose=daily_dose,
        daily_dose_per_kg=daily_dose_per_kg,
        start_date=start_date,
        order_id=order_id,
        infusion_duration_minutes=infusion_duration_minutes,
        rxnorm_code=rxnorm_code,
    )


def _make_context(meds=None, co_meds=None, allergies=None, **kwargs):
    defaults = dict(
        patient_id="P-100",
        patient_mrn="MRN-100",
        patient_name="Test Patient",
        encounter_id="E-100",
        age_years=8.0,
        weight_kg=25.0,
        height_cm=125.0,
        gestational_age_weeks=None,
        bsa=0.95,
        scr=None,
        gfr=None,
        crcl=None,
        is_on_dialysis=False,
        dialysis_type=None,
        indication=None,
    )
    defaults.update(kwargs)
    ctx = PatientContext(**defaults)
    if meds:
        ctx.antimicrobials = meds
    if co_meds:
        ctx.co_medications = co_meds
    if allergies:
        ctx.allergies = allergies
    return ctx


# ===========================================================================
# Data model tests
# ===========================================================================

class DoseFlagTypeTests(TestCase):
    """Test DoseFlagType enum."""

    def test_all_options(self):
        options = DoseFlagType.all_options()
        self.assertGreater(len(options), 10)
        values = [v for v, _ in options]
        self.assertIn("subtherapeutic_dose", values)
        self.assertIn("drug_interaction", values)

    def test_display_name_with_enum(self):
        name = DoseFlagType.display_name(DoseFlagType.WRONG_ROUTE)
        self.assertEqual(name, "Wrong Route")

    def test_display_name_with_string(self):
        name = DoseFlagType.display_name("no_renal_adjustment")
        self.assertEqual(name, "No Renal Adjustment")

    def test_display_name_unknown_string(self):
        name = DoseFlagType.display_name("totally_unknown_flag")
        self.assertEqual(name, "Totally Unknown Flag")


class DoseAlertSeverityTests(TestCase):
    """Test DoseAlertSeverity enum."""

    def test_all_options(self):
        options = DoseAlertSeverity.all_options()
        self.assertEqual(len(options), 4)
        self.assertEqual(options[0], ("critical", "Critical"))


class DoseResolutionTests(TestCase):
    """Test DoseResolution enum."""

    def test_display_name(self):
        name = DoseResolution.display_name(DoseResolution.DOSE_ADJUSTED)
        self.assertEqual(name, "Dose Adjusted")

    def test_all_options_excludes_auto_accepted(self):
        options = DoseResolution.all_options()
        values = [v for v, _ in options]
        self.assertNotIn("auto_accepted", values)
        self.assertIn("dose_adjusted", values)


class MedicationOrderTests(TestCase):
    """Test MedicationOrder dataclass."""

    def test_basic_fields(self):
        med = _make_med()
        self.assertEqual(med.drug_name, "vancomycin")
        self.assertEqual(med.daily_dose, 2000)

    def test_optional_fields(self):
        med = _make_med(infusion_duration_minutes=240, rxnorm_code="11124")
        self.assertEqual(med.infusion_duration_minutes, 240)
        self.assertEqual(med.rxnorm_code, "11124")


class PatientContextTests(TestCase):
    """Test PatientContext dataclass."""

    def test_to_dict_keys(self):
        ctx = _make_context()
        d = ctx.to_dict()
        self.assertIn("patient_id", d)
        self.assertIn("antimicrobials", d)
        self.assertIn("allergies", d)
        self.assertEqual(d["age_years"], 8.0)

    def test_to_dict_with_meds(self):
        ctx = _make_context(meds=[_make_med()])
        d = ctx.to_dict()
        self.assertEqual(len(d["antimicrobials"]), 1)
        self.assertEqual(d["antimicrobials"][0]["drug_name"], "vancomycin")


class DoseFlagTests(TestCase):
    """Test DoseFlag dataclass."""

    def test_to_dict(self):
        flag = DoseFlag(
            flag_type=DoseFlagType.WRONG_ROUTE,
            severity=DoseAlertSeverity.CRITICAL,
            drug="vancomycin",
            message="IV vancomycin for C. diff",
            expected="PO vancomycin",
            actual="vancomycin 500 mg IV q6h",
            rule_source="IDSA",
            indication="c_difficile",
        )
        d = flag.to_dict()
        self.assertEqual(d["flag_type"], "wrong_route")
        self.assertEqual(d["severity"], "critical")
        self.assertEqual(d["drug"], "vancomycin")


class DoseAssessmentTests(TestCase):
    """Test DoseAssessment dataclass."""

    def test_to_dict(self):
        assessment = DoseAssessment(
            assessment_id="DOSE-ABCDEF",
            patient_id="P-1",
            patient_mrn="MRN-1",
            patient_name="Test",
            encounter_id="E-1",
            age_years=10.0,
            weight_kg=30.0,
            height_cm=130.0,
            scr=0.5,
            gfr=120.0,
            is_on_dialysis=False,
            gestational_age_weeks=None,
            medications_evaluated=[],
            indication=None,
            indication_confidence=None,
            indication_source=None,
            flags=[],
            max_severity=None,
            assessed_at="2026-01-01T08:00:00",
            assessed_by="dosing_engine_v1",
            co_medications=[],
        )
        d = assessment.to_dict()
        self.assertEqual(d["assessment_id"], "DOSE-ABCDEF")
        self.assertIsNone(d["max_severity"])

    def test_to_alert_content(self):
        flag = DoseFlag(
            flag_type=DoseFlagType.WRONG_ROUTE,
            severity=DoseAlertSeverity.CRITICAL,
            drug="vancomycin",
            message="test",
            expected="PO",
            actual="IV",
            rule_source="IDSA",
            indication="c_diff",
        )
        assessment = DoseAssessment(
            assessment_id="DOSE-X",
            patient_id="P-1",
            patient_mrn="MRN-1",
            patient_name="Test",
            encounter_id=None,
            age_years=10.0,
            weight_kg=30.0,
            height_cm=130.0,
            scr=None,
            gfr=None,
            is_on_dialysis=False,
            gestational_age_weeks=None,
            medications_evaluated=[],
            indication=None,
            indication_confidence=None,
            indication_source=None,
            flags=[flag],
            max_severity=DoseAlertSeverity.CRITICAL,
            assessed_at="2026-01-01",
            assessed_by="engine",
            co_medications=[],
        )
        content = assessment.to_alert_content()
        self.assertIn("assessment", content)
        self.assertIn("flags", content)
        self.assertEqual(len(content["flags"]), 1)


# ===========================================================================
# Rules engine tests
# ===========================================================================

class DosingRulesEngineTests(TestCase):
    """Test the DosingRulesEngine orchestrator."""

    def test_registers_nine_rule_modules(self):
        engine = DosingRulesEngine()
        self.assertEqual(len(engine.rules), 9)

    def test_evaluate_returns_assessment(self):
        engine = DosingRulesEngine()
        ctx = _make_context()
        assessment = engine.evaluate(ctx)
        self.assertIsInstance(assessment, DoseAssessment)
        self.assertTrue(assessment.assessment_id.startswith("DOSE-"))

    def test_evaluate_no_meds_no_flags(self):
        engine = DosingRulesEngine()
        ctx = _make_context()
        assessment = engine.evaluate(ctx)
        self.assertEqual(len(assessment.flags), 0)
        self.assertIsNone(assessment.max_severity)

    def test_deduplication_keeps_highest_severity(self):
        engine = DosingRulesEngine()
        flags = [
            DoseFlag(
                flag_type=DoseFlagType.WRONG_ROUTE,
                severity=DoseAlertSeverity.MODERATE,
                drug="vancomycin", message="test1", expected="", actual="",
                rule_source="", indication="",
            ),
            DoseFlag(
                flag_type=DoseFlagType.WRONG_ROUTE,
                severity=DoseAlertSeverity.CRITICAL,
                drug="vancomycin", message="test2", expected="", actual="",
                rule_source="", indication="",
            ),
        ]
        deduped = engine._deduplicate_flags(flags)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].severity, DoseAlertSeverity.CRITICAL)

    def test_max_severity(self):
        engine = DosingRulesEngine()
        flags = [
            DoseFlag(
                flag_type=DoseFlagType.WRONG_ROUTE,
                severity=DoseAlertSeverity.MODERATE,
                drug="x", message="", expected="", actual="",
                rule_source="", indication="",
            ),
            DoseFlag(
                flag_type=DoseFlagType.DRUG_INTERACTION,
                severity=DoseAlertSeverity.HIGH,
                drug="y", message="", expected="", actual="",
                rule_source="", indication="",
            ),
        ]
        max_sev = engine._get_max_severity(flags)
        self.assertEqual(max_sev, DoseAlertSeverity.HIGH)

    def test_severity_rank(self):
        engine = DosingRulesEngine()
        self.assertEqual(engine._severity_rank(DoseAlertSeverity.CRITICAL), 4)
        self.assertEqual(engine._severity_rank(DoseAlertSeverity.LOW), 1)

    def test_rule_module_error_does_not_crash(self):
        """If a rule module raises, the engine logs and continues."""
        engine = DosingRulesEngine()

        class BrokenRule(BaseRuleModule):
            def evaluate(self, context):
                raise ValueError("boom")

        engine.rules = [BrokenRule()]
        ctx = _make_context()
        assessment = engine.evaluate(ctx)
        self.assertEqual(len(assessment.flags), 0)


# ===========================================================================
# Allergy rules
# ===========================================================================

class AllergyRulesTests(TestCase):
    """Test allergy checking and cross-reactivity."""

    def test_direct_allergy_match(self):
        rules = AllergyRules()
        med = _make_med(drug_name="amoxicillin")
        ctx = _make_context(
            meds=[med],
            allergies=[{"substance": "amoxicillin", "severity": "mild", "reaction": "rash"}],
        )
        flags = rules.evaluate(ctx)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].flag_type, DoseFlagType.ALLERGY_CONTRAINDICATED)

    def test_severe_allergy_gets_critical_severity(self):
        rules = AllergyRules()
        med = _make_med(drug_name="penicillin")
        ctx = _make_context(
            meds=[med],
            allergies=[{"substance": "penicillin", "severity": "severe/anaphylaxis", "reaction": "anaphylaxis"}],
        )
        flags = rules.evaluate(ctx)
        self.assertEqual(flags[0].severity, DoseAlertSeverity.CRITICAL)

    def test_cross_reactivity_penicillin_cephalosporin(self):
        rules = AllergyRules()
        med = _make_med(drug_name="ceftriaxone")
        ctx = _make_context(
            meds=[med],
            allergies=[{"substance": "amoxicillin", "severity": "mild", "reaction": "rash"}],
        )
        flags = rules.evaluate(ctx)
        # Should flag cross-reactivity penicillin -> cephalosporin
        self.assertGreater(len(flags), 0)
        self.assertEqual(flags[0].flag_type, DoseFlagType.ALLERGY_CROSS_REACTIVITY)

    def test_no_allergy_no_flags(self):
        rules = AllergyRules()
        med = _make_med(drug_name="vancomycin")
        ctx = _make_context(meds=[med], allergies=[])
        flags = rules.evaluate(ctx)
        self.assertEqual(len(flags), 0)

    def test_drug_classes_contain_expected_members(self):
        self.assertIn("amoxicillin", DRUG_CLASSES["penicillins"])
        self.assertIn("ceftriaxone", DRUG_CLASSES["cephalosporins"])
        self.assertIn("meropenem", DRUG_CLASSES["carbapenems"])


# ===========================================================================
# Age-based rules
# ===========================================================================

class AgeClassificationTests(TestCase):
    """Test classify_age_group function."""

    def test_neonate(self):
        self.assertEqual(classify_age_group(0.01), "neonate")

    def test_infant(self):
        self.assertEqual(classify_age_group(0.5), "infant")

    def test_child(self):
        self.assertEqual(classify_age_group(5), "child")

    def test_adolescent(self):
        self.assertEqual(classify_age_group(15), "adolescent")

    def test_adult(self):
        self.assertEqual(classify_age_group(25), "adult")

    def test_none_returns_unknown(self):
        self.assertEqual(classify_age_group(None), "unknown")


class AgeBasedRulesTests(TestCase):
    """Test age-based dosing rules."""

    def test_fluoroquinolone_child_contraindicated(self):
        rules = AgeBasedRules()
        med = _make_med(drug_name="ciprofloxacin", dose_value=200, interval="q12h",
                        frequency_hours=12, daily_dose=400)
        ctx = _make_context(meds=[med], age_years=10.0)
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)
        self.assertEqual(flags[0].flag_type, DoseFlagType.CONTRAINDICATED)

    def test_tetracycline_child_under_8_contraindicated(self):
        rules = AgeBasedRules()
        med = _make_med(drug_name="tetracycline", dose_value=250, interval="q6h",
                        frequency_hours=6, daily_dose=1000)
        ctx = _make_context(meds=[med], age_years=5.0)
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)

    def test_no_age_returns_no_flags(self):
        rules = AgeBasedRules()
        med = _make_med(drug_name="ciprofloxacin")
        ctx = _make_context(meds=[med], age_years=None)
        flags = rules.evaluate(ctx)
        self.assertEqual(len(flags), 0)

    def test_neonatal_gentamicin_verify_interval(self):
        rules = AgeBasedRules()
        # 3-day-old neonate at 28 weeks gestation
        med = _make_med(drug_name="gentamicin", dose_value=10, dose_unit="mg",
                        interval="q48h", frequency_hours=48, daily_dose=5)
        ctx = _make_context(
            meds=[med], age_years=3.0 / 365.25,
            gestational_age_weeks=28,
        )
        flags = rules.evaluate(ctx)
        # Should flag for age-dose verification
        self.assertGreater(len(flags), 0)


# ===========================================================================
# Renal adjustment rules
# ===========================================================================

class RenalAdjustmentRulesTests(TestCase):
    """Test renal dose adjustment rules."""

    def test_no_renal_data_no_flags(self):
        rules = RenalAdjustmentRules()
        med = _make_med(drug_name="meropenem", dose_value=1000, interval="q8h",
                        frequency_hours=8, daily_dose=3000)
        ctx = _make_context(meds=[med], gfr=None, crcl=None, scr=None)
        flags = rules.evaluate(ctx)
        self.assertEqual(len(flags), 0)

    def test_meropenem_low_gfr_flags_interval(self):
        rules = RenalAdjustmentRules()
        # GFR 20, meropenem still at q8h — should flag
        med = _make_med(drug_name="meropenem", dose_value=1000, interval="q8h",
                        frequency_hours=8, daily_dose=3000)
        ctx = _make_context(meds=[med], gfr=20.0, scr=3.0)
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)
        self.assertEqual(flags[0].flag_type, DoseFlagType.NO_RENAL_ADJUSTMENT)

    def test_ceftriaxone_no_adjustment_needed(self):
        """Ceftriaxone is biliary-excreted, no renal adjustment."""
        rules = RenalAdjustmentRules()
        med = _make_med(drug_name="ceftriaxone", dose_value=2000, interval="q24h",
                        frequency_hours=24, daily_dose=2000)
        ctx = _make_context(meds=[med], gfr=15.0, scr=4.0)
        flags = rules.evaluate(ctx)
        self.assertEqual(len(flags), 0)

    def test_dialysis_patient_flag(self):
        rules = RenalAdjustmentRules()
        med = _make_med(drug_name="meropenem", dose_value=1000, interval="q8h",
                        frequency_hours=8, daily_dose=3000)
        ctx = _make_context(
            meds=[med], gfr=5.0, scr=6.0,
            is_on_dialysis=True, dialysis_type="HD",
        )
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)


# ===========================================================================
# Weight-based rules
# ===========================================================================

class WeightHelperTests(TestCase):
    """Test weight calculation helpers."""

    def test_calculate_bmi(self):
        bmi = calculate_bmi(70, 175)
        self.assertAlmostEqual(bmi, 22.86, places=1)

    def test_calculate_ibw_male(self):
        ibw = calculate_ibw_kg(175, sex="male")
        # 175cm = 68.9 inches, 8.9 inches over 5ft -> 50 + 2.3*8.9 = 70.5
        self.assertAlmostEqual(ibw, 70.5, places=0)

    def test_calculate_ibw_female_short(self):
        ibw = calculate_ibw_kg(150, sex="female")
        self.assertEqual(ibw, 45.5)

    def test_calculate_adjusted_weight(self):
        abw = calculate_adjusted_weight_kg(actual_kg=120, ideal_kg=70)
        expected = 70 + 0.4 * (120 - 70)
        self.assertAlmostEqual(abw, expected, places=1)

    def test_adjusted_weight_normal(self):
        """If actual <= ideal, returns actual."""
        abw = calculate_adjusted_weight_kg(actual_kg=60, ideal_kg=70)
        self.assertEqual(abw, 60)


class WeightBasedRulesTests(TestCase):
    """Test weight-based dosing rules."""

    def test_no_weight_no_flags(self):
        rules = WeightBasedRules()
        med = _make_med(drug_name="vancomycin")
        ctx = _make_context(meds=[med], weight_kg=None)
        flags = rules.evaluate(ctx)
        self.assertEqual(len(flags), 0)

    def test_pediatric_vancomycin_max_dose_exceeded(self):
        rules = WeightBasedRules()
        # 60 kg pediatric patient getting 5000 mg/day vancomycin (max is 4000)
        med = _make_med(drug_name="vancomycin", dose_value=1250, interval="q6h",
                        frequency_hours=6, daily_dose=5000)
        ctx = _make_context(meds=[med], age_years=15.0, weight_kg=60.0)
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)
        flag_types = [f.flag_type for f in flags]
        self.assertIn(DoseFlagType.MAX_DOSE_EXCEEDED, flag_types)

    def test_pediatric_low_dose_flags(self):
        rules = WeightBasedRules()
        # 25 kg child getting only 200 mg/day vanc (expected ~1000-1500 mg/day)
        med = _make_med(drug_name="vancomycin", dose_value=50, interval="q6h",
                        frequency_hours=6, daily_dose=200)
        ctx = _make_context(meds=[med], age_years=8.0, weight_kg=25.0)
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)
        self.assertEqual(flags[0].flag_type, DoseFlagType.WEIGHT_DOSE_MISMATCH)


# ===========================================================================
# Route rules
# ===========================================================================

class RouteRulesTests(TestCase):
    """Test route verification rules."""

    def test_iv_vancomycin_for_cdiff_flags_critical(self):
        rules = RouteRules()
        med = _make_med(drug_name="vancomycin", route="IV", interval="q6h",
                        frequency_hours=6, daily_dose=2000)
        ctx = _make_context(meds=[med], indication="c_difficile")
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)
        self.assertEqual(flags[0].flag_type, DoseFlagType.WRONG_ROUTE)
        self.assertEqual(flags[0].severity, DoseAlertSeverity.CRITICAL)

    def test_daptomycin_for_pneumonia_flags(self):
        rules = RouteRules()
        med = _make_med(drug_name="daptomycin", dose_value=350, route="IV",
                        interval="q24h", frequency_hours=24, daily_dose=350)
        ctx = _make_context(meds=[med], indication="pneumonia")
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)
        self.assertIn("surfactant", flags[0].message.lower())

    def test_no_indication_no_flags(self):
        rules = RouteRules()
        med = _make_med(drug_name="vancomycin", route="IV")
        ctx = _make_context(meds=[med], indication=None)
        flags = rules.evaluate(ctx)
        self.assertEqual(len(flags), 0)


# ===========================================================================
# Drug interaction rules
# ===========================================================================

class DrugInteractionRulesTests(TestCase):
    """Test drug-drug interaction detection."""

    def test_meropenem_valproic_acid_critical(self):
        rules = DrugInteractionRules()
        med = _make_med(drug_name="meropenem")
        co_med = _make_med(drug_name="valproic acid", order_id="CO-1")
        ctx = _make_context(meds=[med], co_meds=[co_med])
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)
        self.assertEqual(flags[0].severity, DoseAlertSeverity.CRITICAL)
        self.assertEqual(flags[0].flag_type, DoseFlagType.DRUG_INTERACTION)

    def test_linezolid_ssri_serotonin_syndrome(self):
        rules = DrugInteractionRules()
        med = _make_med(drug_name="linezolid")
        co_med = _make_med(drug_name="sertraline", order_id="CO-1")
        ctx = _make_context(meds=[med], co_meds=[co_med])
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)
        self.assertIn("serotonin", flags[0].message.lower())

    def test_no_co_meds_no_flags(self):
        rules = DrugInteractionRules()
        med = _make_med(drug_name="meropenem")
        ctx = _make_context(meds=[med], co_meds=[])
        flags = rules.evaluate(ctx)
        self.assertEqual(len(flags), 0)

    def test_drug_class_mappings_ssri(self):
        ssris = DRUG_CLASS_MAPPINGS["ssri"]
        self.assertIn("fluoxetine", ssris)
        self.assertIn("sertraline", ssris)


# ===========================================================================
# Indication rules
# ===========================================================================

class IndicationRulesTests(TestCase):
    """Test indication-specific dosing rules."""

    def test_meningitis_subtherapeutic_ceftriaxone(self):
        rules = IndicationRules()
        # 25 kg child with meningitis on low-dose ceftriaxone
        # Expected: 100 mg/kg/day = 2500 mg/day
        med = _make_med(drug_name="ceftriaxone", dose_value=500, interval="q12h",
                        frequency_hours=12, daily_dose=1000)
        ctx = _make_context(meds=[med], indication="meningitis", weight_kg=25.0, age_years=8.0)
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)
        self.assertEqual(flags[0].flag_type, DoseFlagType.SUBTHERAPEUTIC_DOSE)

    def test_no_indication_no_flags(self):
        rules = IndicationRules()
        med = _make_med(drug_name="ceftriaxone")
        ctx = _make_context(meds=[med], indication=None)
        flags = rules.evaluate(ctx)
        self.assertEqual(len(flags), 0)


# ===========================================================================
# Duration rules
# ===========================================================================

class DaysOnTherapyTests(TestCase):
    """Test the days_on_therapy helper."""

    def test_calculates_days(self):
        start = (datetime.now() - timedelta(days=5)).isoformat()
        med = _make_med(start_date=start)
        days = days_on_therapy(med)
        self.assertEqual(days, 5)

    def test_no_start_date(self):
        med = _make_med(start_date="")
        days = days_on_therapy(med)
        self.assertIsNone(days)


class DurationRulesTests(TestCase):
    """Test duration appropriateness rules."""

    def test_surgical_prophylaxis_excessive(self):
        rules = DurationRules()
        # Surgical prophylaxis > 1 day + 3 day grace -> should flag at > 4 days
        start = (datetime.now() - timedelta(days=6)).isoformat()
        med = _make_med(drug_name="cefazolin", start_date=start)
        ctx = _make_context(meds=[med], indication="surgical_prophylaxis")
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)
        self.assertEqual(flags[0].flag_type, DoseFlagType.DURATION_EXCESSIVE)

    def test_duration_rules_have_key_indications(self):
        self.assertIn("osteomyelitis", DURATION_RULES)
        self.assertIn("surgical_prophylaxis", DURATION_RULES)
        self.assertIn("meningitis", DURATION_RULES)


# ===========================================================================
# Extended infusion rules
# ===========================================================================

class ExtendedInfusionRulesTests(TestCase):
    """Test extended infusion optimization rules."""

    def test_piperacillin_tazobactam_standard_infusion_flags(self):
        rules = ExtendedInfusionRules()
        med = _make_med(
            drug_name="piperacillin-tazobactam",
            dose_value=4500, interval="q6h",
            frequency_hours=6, daily_dose=18000,
            infusion_duration_minutes=30,
        )
        ctx = _make_context(meds=[med], indication="Pseudomonas aeruginosa")
        flags = rules.evaluate(ctx)
        self.assertGreater(len(flags), 0)
        self.assertEqual(flags[0].flag_type, DoseFlagType.EXTENDED_INFUSION_CANDIDATE)

    def test_already_extended_no_flags(self):
        rules = ExtendedInfusionRules()
        med = _make_med(
            drug_name="piperacillin-tazobactam",
            dose_value=4500, interval="q6h",
            frequency_hours=6, daily_dose=18000,
            infusion_duration_minutes=240,
        )
        ctx = _make_context(meds=[med])
        flags = rules.evaluate(ctx)
        self.assertEqual(len(flags), 0)

    def test_extended_infusion_drugs_defined(self):
        self.assertIn("piperacillin-tazobactam", EXTENDED_INFUSION_DRUGS)
        self.assertIn("meropenem", EXTENDED_INFUSION_DRUGS)
        self.assertIn("cefepime", EXTENDED_INFUSION_DRUGS)
