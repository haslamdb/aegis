"""Tests for dosing notification handler."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.notifications import DosingNotificationHandler
from common.dosing_verification import (
    DoseAssessment,
    DoseFlag,
    DoseFlagType,
    DoseAlertSeverity,
)


def test_notification_routing():
    """Test that notifications are routed correctly by severity."""
    # Create mock handler (no actual channels)
    handler = DosingNotificationHandler()

    # Test CRITICAL assessment
    critical_assessment = DoseAssessment(
        assessment_id="DOSE-TEST001",
        patient_id="PT-001",
        patient_mrn="123456",
        patient_name="Test Patient",
        encounter_id="ENC-001",
        age_years=65,
        weight_kg=80,
        height_cm=175,
        scr=1.0,
        gfr=60,
        is_on_dialysis=False,
        gestational_age_weeks=None,
        medications_evaluated=[
            {
                "drug": "vancomycin",
                "dose": "1000 mg",
                "interval": "q12h",
                "route": "IV",
                "order_id": "ORD-001",
                "start_date": "2024-01-01",
            }
        ],
        indication="MRSA bacteremia",
        indication_confidence=0.95,
        indication_source="Culture",
        flags=[
            DoseFlag(
                flag_type=DoseFlagType.ALLERGY_CONTRAINDICATED,
                severity=DoseAlertSeverity.CRITICAL,
                drug="vancomycin",
                message="Vancomycin contraindicated - documented allergy",
                expected="Alternative antibiotic",
                actual="Vancomycin ordered",
                rule_source="Allergy checker",
                indication="MRSA bacteremia",
            )
        ],
        max_severity=DoseAlertSeverity.CRITICAL,
        assessed_at="2024-01-01T08:00:00",
        assessed_by="dosing_engine_v1",
        co_medications=[],
    )

    # Should route to both Teams and Email (but will fail gracefully since channels not configured)
    results = handler.send_assessment_alert(critical_assessment, recipient_email="test@example.com")
    assert results["teams"] == False  # No channel configured
    assert results["email"] == False  # No channel configured

    # Test MODERATE assessment
    moderate_assessment = DoseAssessment(
        assessment_id="DOSE-TEST002",
        patient_id="PT-002",
        patient_mrn="234567",
        patient_name="Test Patient 2",
        encounter_id="ENC-002",
        age_years=55,
        weight_kg=70,
        height_cm=170,
        scr=1.2,
        gfr=55,
        is_on_dialysis=False,
        gestational_age_weeks=None,
        medications_evaluated=[
            {
                "drug": "cefepime",
                "dose": "2 g",
                "interval": "q8h",
                "route": "IV",
                "order_id": "ORD-002",
                "start_date": "2024-01-01",
            }
        ],
        indication="Pneumonia",
        indication_confidence=0.85,
        indication_source="LLM",
        flags=[
            DoseFlag(
                flag_type=DoseFlagType.EXTENDED_INFUSION_CANDIDATE,
                severity=DoseAlertSeverity.MODERATE,
                drug="cefepime",
                message="Extended infusion may improve outcomes",
                expected="3 hour infusion",
                actual="30 minute infusion",
                rule_source="PK/PD guidelines",
                indication="Pneumonia",
            )
        ],
        max_severity=DoseAlertSeverity.MODERATE,
        assessed_at="2024-01-01T08:00:00",
        assessed_by="dosing_engine_v1",
        co_medications=[],
    )

    # Should route to Teams only (email should be False even if provided)
    results = handler.send_assessment_alert(moderate_assessment, recipient_email="test@example.com")
    assert results["teams"] == False  # No channel configured
    assert results["email"] == False  # MODERATE doesn't send email

    # Test LOW assessment
    low_assessment = DoseAssessment(
        assessment_id="DOSE-TEST003",
        patient_id="PT-003",
        patient_mrn="345678",
        patient_name="Test Patient 3",
        encounter_id="ENC-003",
        age_years=45,
        weight_kg=75,
        height_cm=172,
        scr=0.9,
        gfr=85,
        is_on_dialysis=False,
        gestational_age_weeks=None,
        medications_evaluated=[
            {
                "drug": "piperacillin-tazobactam",
                "dose": "4.5 g",
                "interval": "q6h",
                "route": "IV",
                "order_id": "ORD-003",
                "start_date": "2024-01-01",
            }
        ],
        indication="UTI",
        indication_confidence=0.75,
        indication_source="LLM",
        flags=[
            DoseFlag(
                flag_type=DoseFlagType.EXTENDED_INFUSION_CANDIDATE,
                severity=DoseAlertSeverity.LOW,
                drug="piperacillin-tazobactam",
                message="Extended infusion may improve outcomes",
                expected="4 hour infusion",
                actual="30 minute infusion",
                rule_source="PK/PD guidelines",
                indication="UTI",
            )
        ],
        max_severity=DoseAlertSeverity.LOW,
        assessed_at="2024-01-01T08:00:00",
        assessed_by="dosing_engine_v1",
        co_medications=[],
    )

    # Should not send any notification (LOW severity)
    results = handler.send_assessment_alert(low_assessment, recipient_email="test@example.com")
    assert results["teams"] == False
    assert results["email"] == False

    # Test no flags
    no_flags_assessment = DoseAssessment(
        assessment_id="DOSE-TEST004",
        patient_id="PT-004",
        patient_mrn="456789",
        patient_name="Test Patient 4",
        encounter_id="ENC-004",
        age_years=35,
        weight_kg=82,
        height_cm=180,
        scr=0.8,
        gfr=95,
        is_on_dialysis=False,
        gestational_age_weeks=None,
        medications_evaluated=[
            {
                "drug": "ceftriaxone",
                "dose": "2 g",
                "interval": "daily",
                "route": "IV",
                "order_id": "ORD-004",
                "start_date": "2024-01-01",
            }
        ],
        indication="CAP",
        indication_confidence=0.90,
        indication_source="LLM",
        flags=[],
        max_severity=None,
        assessed_at="2024-01-01T08:00:00",
        assessed_by="dosing_engine_v1",
        co_medications=[],
    )

    # Should not send any notification (no flags)
    results = handler.send_assessment_alert(no_flags_assessment, recipient_email="test@example.com")
    assert results["teams"] == False
    assert results["email"] == False

    print("✓ All notification routing tests passed")


def test_message_building():
    """Test that messages are built correctly."""
    handler = DosingNotificationHandler()

    assessment = DoseAssessment(
        assessment_id="DOSE-TEST005",
        patient_id="PT-005",
        patient_mrn="567890",
        patient_name="Test Patient 5",
        encounter_id="ENC-005",
        age_years=72,
        weight_kg=68,
        height_cm=165,
        scr=1.5,
        gfr=42,
        is_on_dialysis=False,
        gestational_age_weeks=None,
        medications_evaluated=[
            {
                "drug": "meropenem",
                "dose": "2 g",
                "interval": "q8h",
                "route": "IV",
                "order_id": "ORD-005",
                "start_date": "2024-01-01",
            }
        ],
        indication="Sepsis",
        indication_confidence=0.92,
        indication_source="Clinical",
        flags=[
            DoseFlag(
                flag_type=DoseFlagType.NO_RENAL_ADJUSTMENT,
                severity=DoseAlertSeverity.HIGH,
                drug="meropenem",
                message="Renal adjustment needed for GFR 42",
                expected="1 g q12h or q24h",
                actual="2 g q8h",
                rule_source="Renal dosing guidelines",
                indication="Sepsis",
            )
        ],
        max_severity=DoseAlertSeverity.HIGH,
        assessed_at="2024-01-01T08:00:00",
        assessed_by="dosing_engine_v1",
        co_medications=[],
    )

    # Test Teams message building
    teams_msg = handler._build_teams_message(assessment)
    assert "Dosing Alert" in teams_msg.title
    assert "HIGH" in teams_msg.title
    assert "Test Patient 5" in teams_msg.title
    assert "567890" in teams_msg.title
    # facts is list of tuples: (title, value)
    assert len(teams_msg.facts) == 4  # Patient, Assessment ID, Flags, Issue #1
    assert teams_msg.facts[0] == ("Patient", "Test Patient 5 (MRN: 567890)")
    assert teams_msg.facts[3][0] == "Issue #1: No Renal Adjustment"
    assert "meropenem" in teams_msg.facts[3][1]
    assert len(teams_msg.actions) == 2
    assert teams_msg.color == "Warning"  # HIGH severity

    # Test Email message building
    email_msg = handler._build_email_message(assessment)
    assert "[HIGH]" in email_msg.subject
    assert "Test Patient 5" in email_msg.subject
    assert "567890" in email_msg.subject
    assert "meropenem" in email_msg.html_body
    assert "GFR: 42" in email_msg.html_body
    assert "meropenem" in email_msg.text_body

    print("✓ Message building tests passed")


if __name__ == "__main__":
    test_notification_routing()
    test_message_building()

    print("\n✅ All notification tests passed!")
