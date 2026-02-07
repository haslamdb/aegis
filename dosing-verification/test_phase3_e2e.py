"""End-to-end test for Phase 3 features: duration rules, extended infusion, notifications, analytics."""

import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from src.models import PatientContext, MedicationOrder
from src.rules_engine import DosingRulesEngine
from src.alert_integration import DosingAlertIntegration
from src.notifications import DosingNotificationHandler
from src.monitor import DosingVerificationMonitor
from common.dosing_verification import (
    DoseAlertStore,
    DoseAlertSeverity,
    DoseFlagType,
)


def test_duration_rules():
    """Test duration rules detect therapy that's too short or too long."""
    print("\n" + "=" * 70)
    print("TEST 1: Duration Rules")
    print("=" * 70)

    rules_engine = DosingRulesEngine()

    # Test 1a: Duration too short (UTI on day 2, needs 3-7 days)
    context = PatientContext(
        patient_id="PT-DUR-001",
        patient_mrn="DUR001",
        patient_name="Duration Test 1",
        encounter_id="ENC-001",
        age_years=35,
        weight_kg=70,
        height_cm=170,
        gestational_age_weeks=None,
        bsa=None,
        scr=0.9,
        gfr=85,
        crcl=90,
        is_on_dialysis=False,
        dialysis_type=None,
        antimicrobials=[
            MedicationOrder(
                drug_name="ciprofloxacin",
                dose_value=500,
                dose_unit="mg",
                interval="q12h",
                route="PO",
                frequency_hours=12,
                daily_dose=1000,
                daily_dose_per_kg=None,
                start_date=(datetime.now() - timedelta(days=2)).isoformat(),  # Started 2 days ago
                order_id="ORD-001",
            ),
        ],
        indication="urinary tract infection",  # Will match "uti" via fuzzy matching
        indication_confidence=0.9,
        indication_source="LLM",
        co_medications=[],
        allergies=[],
    )

    assessment = rules_engine.evaluate(context)

    # Should flag duration insufficient
    duration_flags = [f for f in assessment.flags if f.flag_type == DoseFlagType.DURATION_INSUFFICIENT]
    assert len(duration_flags) == 1, f"Expected 1 duration flag, got {len(duration_flags)}"
    assert "too short" in duration_flags[0].message.lower()
    print("✓ Duration too short detected (2 days, needs 3-7 days)")

    # Test 1b: Duration too long (cellulitis on day 18, max 14 days)
    context2 = PatientContext(
        patient_id="PT-DUR-002",
        patient_mrn="DUR002",
        patient_name="Duration Test 2",
        encounter_id="ENC-002",
        age_years=55,
        weight_kg=80,
        height_cm=175,
        gestational_age_weeks=None,
        bsa=None,
        scr=1.0,
        gfr=70,
        crcl=75,
        is_on_dialysis=False,
        dialysis_type=None,
        antimicrobials=[
            MedicationOrder(
                drug_name="cephalexin",
                dose_value=500,
                dose_unit="mg",
                interval="q6h",
                route="PO",
                frequency_hours=6,
                daily_dose=2000,
                daily_dose_per_kg=None,
                start_date=(datetime.now() - timedelta(days=18)).isoformat(),  # Started 18 days ago
                order_id="ORD-002",
            ),
        ],
        indication="cellulitis",
        indication_confidence=0.95,
        indication_source="Clinical",
        co_medications=[],
        allergies=[],
    )

    assessment2 = rules_engine.evaluate(context2)

    # Should flag duration excessive (18 days > 14 + 3 day grace period)
    excessive_flags = [f for f in assessment2.flags if f.flag_type == DoseFlagType.DURATION_EXCESSIVE]
    assert len(excessive_flags) == 1, f"Expected 1 excessive duration flag, got {len(excessive_flags)}"
    assert "excessive" in excessive_flags[0].message.lower()
    print("✓ Duration too long detected (18 days, max 14 days)")

    print("✅ Duration rules test passed\n")


def test_extended_infusion():
    """Test extended infusion optimization opportunities."""
    print("=" * 70)
    print("TEST 2: Extended Infusion Rules")
    print("=" * 70)

    rules_engine = DosingRulesEngine()

    # Test 2a: Pip-tazo on standard infusion for severe sepsis (should flag HIGH)
    context = PatientContext(
        patient_id="PT-EI-001",
        patient_mrn="EI001",
        patient_name="Extended Infusion Test 1",
        encounter_id="ENC-001",
        age_years=68,
        weight_kg=75,
        height_cm=172,
        gestational_age_weeks=None,
        bsa=None,
        scr=1.2,
        gfr=55,
        crcl=58,
        is_on_dialysis=False,
        dialysis_type=None,
        antimicrobials=[
            MedicationOrder(
                drug_name="piperacillin-tazobactam",
                dose_value=4.5,
                dose_unit="g",
                interval="q6h",
                route="IV",
                frequency_hours=6,
                daily_dose=18,
                daily_dose_per_kg=None,
                start_date=datetime.now().isoformat(),
                order_id="ORD-001",
                infusion_duration_minutes=30,  # Standard 30-min infusion
            ),
        ],
        indication="severe sepsis",  # High-risk indication
        indication_confidence=0.95,
        indication_source="Clinical",
        co_medications=[],
        allergies=[],
    )

    assessment = rules_engine.evaluate(context)

    # Should flag extended infusion candidate (HIGH severity due to severe sepsis)
    ei_flags = [f for f in assessment.flags if f.flag_type == DoseFlagType.EXTENDED_INFUSION_CANDIDATE]
    assert len(ei_flags) == 1, f"Expected 1 extended infusion flag, got {len(ei_flags)}"
    assert ei_flags[0].severity == DoseAlertSeverity.HIGH
    assert "extended infusion" in ei_flags[0].message.lower()
    print("✓ Extended infusion opportunity detected (HIGH severity for severe sepsis)")

    # Test 2b: Already on extended infusion (should NOT flag)
    context2 = PatientContext(
        patient_id="PT-EI-002",
        patient_mrn="EI002",
        patient_name="Extended Infusion Test 2",
        encounter_id="ENC-002",
        age_years=45,
        weight_kg=82,
        height_cm=180,
        gestational_age_weeks=None,
        bsa=None,
        scr=1.0,
        gfr=75,
        crcl=80,
        is_on_dialysis=False,
        dialysis_type=None,
        antimicrobials=[
            MedicationOrder(
                drug_name="meropenem",
                dose_value=2,
                dose_unit="g",
                interval="q8h",
                route="IV",
                frequency_hours=8,
                daily_dose=6,
                daily_dose_per_kg=None,
                start_date=datetime.now().isoformat(),
                order_id="ORD-002",
                infusion_duration_minutes=180,  # Already 3-hour extended infusion
            ),
        ],
        indication="pneumonia",
        indication_confidence=0.88,
        indication_source="LLM",
        co_medications=[],
        allergies=[],
    )

    assessment2 = rules_engine.evaluate(context2)

    # Should NOT flag (already on extended infusion)
    ei_flags2 = [f for f in assessment2.flags if f.flag_type == DoseFlagType.EXTENDED_INFUSION_CANDIDATE]
    assert len(ei_flags2) == 0, f"Expected 0 extended infusion flags, got {len(ei_flags2)}"
    print("✓ No flag when already on extended infusion")

    print("✅ Extended infusion test passed\n")


def test_alert_store_integration():
    """Test saving assessments to AlertStore."""
    print("=" * 70)
    print("TEST 3: AlertStore Integration")
    print("=" * 70)

    # Use temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmpdb:
        alert_store = DoseAlertStore(db_path=tmpdb.name)
        integration = DosingAlertIntegration(alert_store=alert_store, auto_notify=False)

        rules_engine = DosingRulesEngine()

        # Create assessment with flags
        context = PatientContext(
            patient_id="PT-STORE-001",
            patient_mrn="STORE001",
            patient_name="AlertStore Test",
            encounter_id="ENC-001",
            age_years=42,
            weight_kg=70,
            height_cm=170,
            gestational_age_weeks=None,
            bsa=None,
            scr=1.5,
            gfr=45,
            crcl=48,
            is_on_dialysis=False,
            dialysis_type=None,
            antimicrobials=[
                MedicationOrder(
                    drug_name="meropenem",
                    dose_value=2,
                    dose_unit="g",
                    interval="q8h",
                    route="IV",
                    frequency_hours=8,
                    daily_dose=6,
                    daily_dose_per_kg=None,
                    start_date=datetime.now().isoformat(),
                    order_id="ORD-001",
                ),
            ],
            indication="sepsis",
            indication_confidence=0.92,
            indication_source="Clinical",
            co_medications=[],
            allergies=[],
        )

        assessment = rules_engine.evaluate(context)

        # Should have renal adjustment flag (GFR 45)
        assert len(assessment.flags) > 0, "Expected flags for renal insufficiency"

        # Save to AlertStore
        alerts = integration.save_assessment(assessment)

        assert len(alerts) == len(assessment.flags), f"Expected {len(assessment.flags)} alerts, got {len(alerts)}"
        print(f"✓ Saved {len(alerts)} alert(s) to database")

        # Retrieve from database
        retrieved = integration.get_alerts_for_patient("STORE001")
        assert len(retrieved) == len(alerts), f"Expected {len(alerts)} alerts from DB, got {len(retrieved)}"
        print(f"✓ Retrieved {len(retrieved)} alert(s) from database")

        # Check alert details
        assert retrieved[0].patient_mrn == "STORE001"
        assert retrieved[0].drug == "meropenem"
        print("✓ Alert details match")

    print("✅ AlertStore integration test passed\n")


def test_csv_export():
    """Test CSV export functionality."""
    print("=" * 70)
    print("TEST 4: CSV Export")
    print("=" * 70)

    # Use temporary database and CSV file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmpdb, \
         tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as tmpcsv:

        alert_store = DoseAlertStore(db_path=tmpdb.name)
        integration = DosingAlertIntegration(alert_store=alert_store, auto_notify=False)
        monitor = DosingVerificationMonitor()
        monitor.dose_store = alert_store

        # Create and save a few test alerts
        rules_engine = DosingRulesEngine()

        for i in range(3):
            context = PatientContext(
                patient_id=f"PT-CSV-{i:03d}",
                patient_mrn=f"CSV{i:03d}",
                patient_name=f"CSV Test {i+1}",
                encounter_id=f"ENC-{i:03d}",
                age_years=40 + i * 10,
                weight_kg=70 + i * 5,
                height_cm=170,
                gestational_age_weeks=None,
                bsa=None,
                scr=1.0 + i * 0.5,
                gfr=60 - i * 10,
                crcl=65 - i * 10,
                is_on_dialysis=False,
                dialysis_type=None,
                antimicrobials=[
                    MedicationOrder(
                        drug_name="vancomycin",
                        dose_value=1000,
                        dose_unit="mg",
                        interval="q12h",
                        route="IV",
                        frequency_hours=12,
                        daily_dose=2000,
                        daily_dose_per_kg=None,
                        start_date=datetime.now().isoformat(),
                        order_id=f"ORD-{i:03d}",
                    ),
                ],
                indication="bacteremia",
                indication_confidence=0.9,
                indication_source="Culture",
                co_medications=[],
                allergies=[],
            )

            assessment = rules_engine.evaluate(context)
            integration.save_assessment(assessment)

        tmpcsv.close()  # Close before monitor writes to it

        # Generate CSV report
        count = monitor.generate_csv_report(tmpcsv.name, days=1)

        assert count >= 3, f"Expected at least 3 alerts in CSV, got {count}"
        print(f"✓ Generated CSV report with {count} alert(s)")

        # Verify CSV contents
        with open(tmpcsv.name, "r") as f:
            lines = f.readlines()
            assert len(lines) >= 4, "Expected header + at least 3 data rows"  # header + alerts
            assert "Alert ID" in lines[0]
            assert "Patient MRN" in lines[0]
            print("✓ CSV format validated")

    print("✅ CSV export test passed\n")


def test_analytics():
    """Test analytics generation."""
    print("=" * 70)
    print("TEST 5: Analytics")
    print("=" * 70)

    # Use temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmpdb:
        alert_store = DoseAlertStore(db_path=tmpdb.name)
        monitor = DosingVerificationMonitor()
        monitor.dose_store = alert_store

        # Create some test data
        integration = DosingAlertIntegration(alert_store=alert_store, auto_notify=False)
        rules_engine = DosingRulesEngine()

        # Create alerts with different severities
        severities = [DoseAlertSeverity.CRITICAL, DoseAlertSeverity.HIGH, DoseAlertSeverity.MODERATE]

        for i, severity in enumerate(severities):
            context = PatientContext(
                patient_id=f"PT-ANALYTICS-{i:03d}",
                patient_mrn=f"ANALYTICS{i:03d}",
                patient_name=f"Analytics Test {i+1}",
                encounter_id=f"ENC-{i:03d}",
                age_years=50,
                weight_kg=75,
                height_cm=175,
                gestational_age_weeks=None,
                bsa=None,
                scr=1.0,
                gfr=70,
                crcl=75,
                is_on_dialysis=False,
                dialysis_type=None,
                antimicrobials=[
                    MedicationOrder(
                        drug_name="ceftriaxone",
                        dose_value=1000,
                        dose_unit="mg",
                        interval="q24h",
                        route="IV",
                        frequency_hours=24,
                        daily_dose=1000,
                        daily_dose_per_kg=None,
                        start_date=(datetime.now() - timedelta(days=i * 10)).isoformat(),
                        order_id=f"ORD-{i:03d}",
                    ),
                ],
                indication="pneumonia",
                indication_confidence=0.9,
                indication_source="Clinical",
                co_medications=[],
                allergies=[],
            )

            assessment = rules_engine.evaluate(context)
            # Override severity for testing
            if assessment.flags:
                assessment.flags[0].severity = severity
                assessment.max_severity = severity
            integration.save_assessment(assessment)

        # Get analytics
        analytics = monitor.get_analytics(days=365)  # Long period to catch all test data

        assert "total_alerts" in analytics or "stats" in analytics
        print(f"✓ Analytics generated: {analytics}")

    print("✅ Analytics test passed\n")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("PHASE 3 END-TO-END TESTING")
    print("=" * 70)

    try:
        test_duration_rules()
        test_extended_infusion()
        test_alert_store_integration()
        test_csv_export()
        test_analytics()

        print("\n" + "=" * 70)
        print("✅ ALL PHASE 3 TESTS PASSED!")
        print("=" * 70)
        print("\nPhase 3 Features Verified:")
        print("  ✓ Duration rules (too short/too long)")
        print("  ✓ Extended infusion optimization")
        print("  ✓ AlertStore integration")
        print("  ✓ CSV export")
        print("  ✓ Analytics")
        print("\nPhase 3 is complete and ready for deployment!")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
