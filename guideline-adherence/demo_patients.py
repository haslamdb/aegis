#!/usr/bin/env python3
"""Guideline Adherence Demo with Sample Patients.

This script demonstrates the guideline adherence monitoring system with
realistic patient scenarios for different bundles.

Usage:
    python demo_patients.py

The demo creates a temporary database and simulates:
1. Febrile Infant (14-day-old) - Full adherence scenario
2. Sepsis (3-year-old) - Partial adherence with missed elements
3. Neonatal HSV (10-day-old) - Critical alerts scenario
4. C. diff Testing - Diagnostic stewardship check
"""

import sys
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from guideline_adherence import (
    GUIDELINE_BUNDLES,
    BundleElementStatus,
    AdherenceLevel,
)
from guideline_src.episode_db import (
    EpisodeDB,
    BundleEpisode,
    ElementResult,
    BundleAlert,
)


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_subheader(text: str):
    """Print a formatted subheader."""
    print("\n" + "-" * 50)
    print(f"  {text}")
    print("-" * 50)


def print_element_status(element_name: str, status: str, value: str = None, notes: str = None):
    """Print element status with icon."""
    icons = {
        "met": "\u2713",      # checkmark
        "not_met": "\u2717",  # X
        "pending": "\u25cb",  # circle
        "na": "-",
        "unknown": "?",
    }
    icon = icons.get(status, "?")
    value_str = f" = {value}" if value else ""
    notes_str = f" ({notes})" if notes else ""
    print(f"    [{icon}] {element_name}: {status}{value_str}{notes_str}")


def create_febrile_infant_episode(db: EpisodeDB) -> int:
    """Create a febrile infant episode with full adherence.

    Patient: 14-day-old with fever 38.5°C
    Expected: All required elements for 8-21 day age group
    """
    print_subheader("Patient 1: Febrile Infant (14 days old)")

    now = datetime.now()
    trigger_time = now - timedelta(hours=2)

    print(f"""
    MRN: FI-2024-001
    Age: 14 days
    Chief Complaint: Fever (38.5°C) at home
    Presentation: Well-appearing, no source identified
    Trigger Time: {trigger_time.strftime('%Y-%m-%d %H:%M')}

    Bundle: Febrile Infant (8-60 days) - AAP 2021 Guideline
    Age Group: 8-21 days (requires LP, admission, IV antibiotics)
    """)

    # Create episode
    episode = BundleEpisode(
        patient_id="PT-FI-001",
        patient_mrn="FI-2024-001",
        encounter_id="ENC-FI-001",
        bundle_id="febrile_infant_2024",
        bundle_name="Febrile Infant Bundle (0-60 days)",
        trigger_type="diagnosis",
        trigger_code="R50.9",
        trigger_description="Fever, unspecified",
        trigger_time=trigger_time,
        patient_age_days=14,
        patient_age_months=0.47,
        patient_unit="Pediatric Emergency",
        status="active",
    )
    episode_id = db.save_episode(episode)

    # Simulate element results - FULL ADHERENCE
    bundle = GUIDELINE_BUNDLES["febrile_infant_2024"]

    elements_data = [
        # All elements completed within time window
        ("fi_ua", "Urinalysis obtained", "met", "Negative", "Cath specimen"),
        ("fi_blood_culture", "Blood culture obtained", "met", "Collected 10:15", "Before antibiotics"),
        ("fi_inflammatory_markers", "Inflammatory markers obtained", "met", "ANC 8500, CRP 0.8", "Normal"),
        ("fi_lp_8_21d", "LP performed (8-21 days)", "met", "WBC 2, protein 45", "Normal CSF"),
        ("fi_abx_8_21d", "Parenteral antibiotics (8-21 days)", "met", "Ampicillin + Gentamicin", "Given at 10:30"),
        ("fi_hsv_risk_assessment", "HSV risk assessment", "met", "No risk factors", "Documented in note"),
        ("fi_admit_8_21d", "Hospital admission (8-21 days)", "met", "Admitted", "To pediatrics"),
    ]

    print("    Element Status:")
    met_count = 0
    for elem_id, elem_name, status, value, notes in elements_data:
        result = ElementResult(
            episode_id=episode_id,
            element_id=elem_id,
            element_name=elem_name,
            status=status,
            required=True,
            time_window_hours=2.0,
            deadline=trigger_time + timedelta(hours=2),
            completed_at=trigger_time + timedelta(minutes=30) if status == "met" else None,
            value=value,
            notes=notes,
        )
        db.save_element_result(result)
        print_element_status(elem_name, status, value, notes)
        if status == "met":
            met_count += 1

    # Update episode with adherence stats
    episode.id = episode_id
    episode.elements_total = len(elements_data)
    episode.elements_applicable = len(elements_data)
    episode.elements_met = met_count
    episode.elements_not_met = 0
    episode.elements_pending = len(elements_data) - met_count
    episode.adherence_percentage = (met_count / len(elements_data)) * 100
    episode.adherence_level = "full" if episode.adherence_percentage == 100 else "partial"
    db.save_episode(episode)

    print(f"""
    Summary:
    - Elements Met: {met_count}/{len(elements_data)}
    - Adherence: {episode.adherence_percentage:.0f}%
    - Level: {episode.adherence_level.upper()}
    - Alerts: None (full compliance)
    """)

    return episode_id


def create_sepsis_episode(db: EpisodeDB) -> int:
    """Create a sepsis episode with partial adherence.

    Patient: 3-year-old with septic shock
    Scenario: Antibiotics delayed >1 hour, no repeat lactate
    """
    print_subheader("Patient 2: Pediatric Sepsis (3 years old)")

    now = datetime.now()
    trigger_time = now - timedelta(hours=4)

    print(f"""
    MRN: SEP-2024-002
    Age: 3 years
    Chief Complaint: Fever, lethargy, poor perfusion
    Presentation: Hypotensive, tachycardic, mottled extremities
    Trigger Time: {trigger_time.strftime('%Y-%m-%d %H:%M')} (sepsis alert fired)

    Bundle: Pediatric Sepsis Bundle
    Critical Elements: ABX within 1 hour, blood culture, lactate
    """)

    # Create episode
    episode = BundleEpisode(
        patient_id="PT-SEP-002",
        patient_mrn="SEP-2024-002",
        encounter_id="ENC-SEP-002",
        bundle_id="sepsis_peds_2024",
        bundle_name="Pediatric Sepsis Bundle",
        trigger_type="diagnosis",
        trigger_code="A41.9",
        trigger_description="Sepsis, unspecified organism",
        trigger_time=trigger_time,
        patient_age_days=1095,
        patient_age_months=36,
        patient_weight_kg=15.0,
        patient_unit="PICU",
        status="active",
    )
    episode_id = db.save_episode(episode)

    # Simulate element results - PARTIAL ADHERENCE with issues
    elements_data = [
        ("sepsis_blood_cx", "Blood culture obtained", "met", "Collected 14:05", "Before antibiotics"),
        ("sepsis_lactate", "Lactate measured", "met", "4.2 mmol/L", "Elevated - needs repeat"),
        ("sepsis_abx_1hr", "Antibiotics within 1 hour", "not_met", "Given at 15:20", "DELAYED 80 min - pharmacy delay"),
        ("sepsis_fluid_bolus", "Fluid resuscitation initiated", "met", "60 mL/kg given", "3 boluses"),
        ("sepsis_repeat_lactate", "Repeat lactate if elevated", "not_met", None, "NOT DONE - initial was 4.2"),
        ("sepsis_reassess_48h", "Antibiotic reassessment at 48h", "pending", None, "Due in 44 hours"),
    ]

    print("    Element Status:")
    met_count = 0
    not_met_count = 0
    pending_count = 0

    for elem_id, elem_name, status, value, notes in elements_data:
        # Determine time window based on element
        time_window = 1.0 if "1hr" in elem_id or "1h" in elem_name.lower() else 6.0
        if "48h" in elem_id:
            time_window = 72.0

        result = ElementResult(
            episode_id=episode_id,
            element_id=elem_id,
            element_name=elem_name,
            status=status,
            required=True,
            time_window_hours=time_window,
            deadline=trigger_time + timedelta(hours=time_window),
            completed_at=trigger_time + timedelta(minutes=20) if status == "met" else None,
            value=value,
            notes=notes,
        )
        db.save_element_result(result)
        print_element_status(elem_name, status, value, notes)

        if status == "met":
            met_count += 1
        elif status == "not_met":
            not_met_count += 1
        else:
            pending_count += 1

    # Create alerts for missed elements
    alert_count = 0

    # Alert for delayed antibiotics (CRITICAL)
    alert1 = BundleAlert(
        episode_id=episode_id,
        patient_id="PT-SEP-002",
        patient_mrn="SEP-2024-002",
        encounter_id="ENC-SEP-002",
        bundle_id="sepsis_peds_2024",
        bundle_name="Pediatric Sepsis Bundle",
        element_id="sepsis_abx_1hr",
        element_name="Antibiotics within 1 hour",
        alert_type="element_not_met",
        severity="critical",
        title="SEPSIS: Antibiotic delay >1 hour",
        message="Antibiotics administered 80 minutes after sepsis recognition. Target: <60 minutes. Delay attributed to pharmacy.",
    )
    db.save_alert(alert1)
    alert_count += 1

    # Alert for missing repeat lactate (WARNING)
    alert2 = BundleAlert(
        episode_id=episode_id,
        patient_id="PT-SEP-002",
        patient_mrn="SEP-2024-002",
        encounter_id="ENC-SEP-002",
        bundle_id="sepsis_peds_2024",
        bundle_name="Pediatric Sepsis Bundle",
        element_id="sepsis_repeat_lactate",
        element_name="Repeat lactate if elevated",
        alert_type="element_overdue",
        severity="warning",
        title="SEPSIS: Repeat lactate overdue",
        message="Initial lactate was 4.2 mmol/L. Repeat lactate required within 6 hours but not yet obtained.",
    )
    db.save_alert(alert2)
    alert_count += 1

    # Update episode stats
    applicable = len(elements_data) - pending_count
    adherence_pct = (met_count / applicable * 100) if applicable > 0 else 0

    episode.id = episode_id
    episode.elements_total = len(elements_data)
    episode.elements_applicable = applicable
    episode.elements_met = met_count
    episode.elements_not_met = not_met_count
    episode.elements_pending = pending_count
    episode.adherence_percentage = adherence_pct
    episode.adherence_level = "partial" if adherence_pct > 50 else "low"
    db.save_episode(episode)

    print(f"""
    Summary:
    - Elements Met: {met_count}/{applicable} (+ {pending_count} pending)
    - Adherence: {adherence_pct:.0f}%
    - Level: {episode.adherence_level.upper()}
    - Alerts Generated: {alert_count}
      * CRITICAL: Antibiotic delay (80 min vs 60 min target)
      * WARNING: Repeat lactate not obtained
    """)

    return episode_id


def create_neonatal_hsv_episode(db: EpisodeDB) -> int:
    """Create a neonatal HSV episode with critical alerts.

    Patient: 10-day-old with vesicular rash and seizure
    Scenario: HSV workup incomplete, acyclovir not started
    """
    print_subheader("Patient 3: Neonatal HSV Suspected (10 days old)")

    now = datetime.now()
    trigger_time = now - timedelta(hours=3)

    print(f"""
    MRN: HSV-2024-003
    Age: 10 days
    Chief Complaint: Vesicular rash, new seizure
    Presentation: Irritable, vesicles on scalp, witnessed seizure
    HSV Risk Factors: Vesicular rash, seizures, maternal HSV unknown
    Trigger Time: {trigger_time.strftime('%Y-%m-%d %H:%M')}

    Bundle: Neonatal HSV Bundle (CCHMC 2024)
    CRITICAL: Acyclovir must be started within 1 hour
    """)

    # Create episode
    episode = BundleEpisode(
        patient_id="PT-HSV-003",
        patient_mrn="HSV-2024-003",
        encounter_id="ENC-HSV-003",
        bundle_id="neonatal_hsv_2024",
        bundle_name="Neonatal HSV Bundle",
        trigger_type="diagnosis",
        trigger_code="B00.9",
        trigger_description="Herpesviral infection suspected",
        trigger_time=trigger_time,
        patient_age_days=10,
        patient_age_months=0.33,
        patient_weight_kg=3.5,
        patient_unit="NICU",
        status="active",
    )
    episode_id = db.save_episode(episode)

    # Simulate element results - CRITICAL ISSUES
    elements_data = [
        ("hsv_csf_pcr", "CSF HSV PCR", "met", "Sent", "LP done at 15:30"),
        ("hsv_surface_cultures", "Surface cultures (SEM)", "met", "Collected", "Conjunctiva, mouth, rectum"),
        ("hsv_blood_pcr", "Blood HSV PCR", "met", "Sent", "Collected with blood cx"),
        ("hsv_lfts", "LFTs obtained", "met", "ALT 45, AST 52", "Mildly elevated"),
        ("hsv_acyclovir_started", "Acyclovir started", "not_met", None, "NOT GIVEN - 3 HOURS ELAPSED"),
        ("hsv_acyclovir_dose", "Acyclovir 60 mg/kg/day Q8H", "pending", None, "Awaiting acyclovir start"),
        ("hsv_id_consult", "ID consult", "met", "Placed", "ID to see within 2h"),
        ("hsv_neuroimaging", "Neuroimaging (CNS suspected)", "pending", None, "MRI scheduled"),
    ]

    print("    Element Status:")
    met_count = 0
    not_met_count = 0
    pending_count = 0

    for elem_id, elem_name, status, value, notes in elements_data:
        time_window = 1.0 if "acyclovir_started" in elem_id else 4.0
        if "consult" in elem_id:
            time_window = 24.0
        if "neuroimaging" in elem_id:
            time_window = 48.0

        result = ElementResult(
            episode_id=episode_id,
            element_id=elem_id,
            element_name=elem_name,
            status=status,
            required=True,
            time_window_hours=time_window,
            deadline=trigger_time + timedelta(hours=time_window),
            completed_at=trigger_time + timedelta(minutes=45) if status == "met" else None,
            value=value,
            notes=notes,
        )
        db.save_element_result(result)
        print_element_status(elem_name, status, value, notes)

        if status == "met":
            met_count += 1
        elif status == "not_met":
            not_met_count += 1
        else:
            pending_count += 1

    # Create CRITICAL alert for missing acyclovir
    alert = BundleAlert(
        episode_id=episode_id,
        patient_id="PT-HSV-003",
        patient_mrn="HSV-2024-003",
        encounter_id="ENC-HSV-003",
        bundle_id="neonatal_hsv_2024",
        bundle_name="Neonatal HSV Bundle",
        element_id="hsv_acyclovir_started",
        element_name="Acyclovir started",
        alert_type="element_overdue",
        severity="critical",
        title="URGENT: Acyclovir NOT started - HSV suspected",
        message=f"Neonatal HSV suspected with vesicles and seizure. Acyclovir required within 1 hour but NOT YET GIVEN. "
                f"Time elapsed: 3 hours. Risk factors: vesicular rash, seizures. "
                f"ACTION REQUIRED: Start IV acyclovir 20 mg/kg Q8H immediately.",
    )
    db.save_alert(alert)

    # Update episode stats
    applicable = len(elements_data) - pending_count
    adherence_pct = (met_count / applicable * 100) if applicable > 0 else 0

    episode.id = episode_id
    episode.elements_total = len(elements_data)
    episode.elements_applicable = applicable
    episode.elements_met = met_count
    episode.elements_not_met = not_met_count
    episode.elements_pending = pending_count
    episode.adherence_percentage = adherence_pct
    episode.adherence_level = "low"
    db.save_episode(episode)

    print(f"""
    Summary:
    - Elements Met: {met_count}/{applicable} (+ {pending_count} pending)
    - Adherence: {adherence_pct:.0f}%
    - Level: {episode.adherence_level.upper()}

    *** CRITICAL ALERT ***
    Acyclovir NOT started in neonate with suspected HSV!
    - Vesicular rash present
    - Seizure documented
    - 3 hours elapsed (target: 1 hour)
    - Mortality risk increases with treatment delay

    ACTION: Start IV acyclovir 20 mg/kg Q8H IMMEDIATELY
    """)

    return episode_id


def create_cdiff_testing_episode(db: EpisodeDB) -> int:
    """Create a C. diff testing appropriateness episode.

    Patient: 8-year-old with diarrhea, recent antibiotics
    Scenario: Testing appropriateness check (diagnostic stewardship)
    """
    print_subheader("Patient 4: C. diff Testing Appropriateness (8 years old)")

    now = datetime.now()
    trigger_time = now - timedelta(hours=1)

    print(f"""
    MRN: CDIFF-2024-004
    Age: 8 years
    Chief Complaint: Watery diarrhea x 3 days
    History: Completed amoxicillin course 5 days ago (for strep throat)
    Stool Count: 5 liquid stools in 24 hours

    Bundle: C. diff Testing Appropriateness (Diagnostic Stewardship)
    Purpose: Verify testing criteria met before resulting
    """)

    # Create episode
    episode = BundleEpisode(
        patient_id="PT-CDIFF-004",
        patient_mrn="CDIFF-2024-004",
        encounter_id="ENC-CDIFF-004",
        bundle_id="cdiff_testing_2024",
        bundle_name="C. diff Testing Appropriateness Bundle",
        trigger_type="lab",
        trigger_code="C_DIFF_PCR",
        trigger_description="C. diff PCR test ordered",
        trigger_time=trigger_time,
        patient_age_days=2920,
        patient_age_months=96,
        patient_unit="Pediatric Unit",
        status="active",
    )
    episode_id = db.save_episode(episode)

    # Check appropriateness criteria - ALL MET (appropriate test)
    elements_data = [
        ("cdiff_age_appropriate", "Age ≥3 years", "met", "8 years", "Meets age criteria"),
        ("cdiff_liquid_stools", "≥3 liquid stools/24h", "met", "5 stools", "Documented in nursing notes"),
        ("cdiff_no_laxatives", "No laxatives 48h", "met", "None given", "MAR reviewed"),
        ("cdiff_no_contrast", "No enteral contrast 48h", "met", "None given", "No recent imaging"),
        ("cdiff_no_tube_feed_changes", "No tube feed changes", "na", None, "Not on tube feeds"),
        ("cdiff_no_gi_bleed", "No active GI bleed", "met", "No blood", "Stools non-bloody"),
        ("cdiff_risk_factor_present", "Risk factor present", "met", "Recent antibiotics", "Amoxicillin 5 days ago"),
        ("cdiff_symptom_duration", "Symptoms persist 48h", "met", "3 days", "Symptoms x 72 hours"),
    ]

    print("    Appropriateness Criteria:")
    met_count = 0
    na_count = 0

    for elem_id, elem_name, status, value, notes in elements_data:
        result = ElementResult(
            episode_id=episode_id,
            element_id=elem_id,
            element_name=elem_name,
            status=status,
            required=status != "na",
            value=value,
            notes=notes,
        )
        db.save_element_result(result)
        print_element_status(elem_name, status, value, notes)

        if status == "met":
            met_count += 1
        elif status == "na":
            na_count += 1

    applicable = len(elements_data) - na_count
    adherence_pct = (met_count / applicable * 100) if applicable > 0 else 0

    episode.id = episode_id
    episode.elements_total = len(elements_data)
    episode.elements_applicable = applicable
    episode.elements_met = met_count
    episode.elements_not_met = 0
    episode.elements_pending = 0
    episode.adherence_percentage = adherence_pct
    episode.adherence_level = "full"
    episode.status = "completed"
    db.save_episode(episode)

    print(f"""
    Appropriateness Assessment:
    - Criteria Met: {met_count}/{applicable}
    - Score: {adherence_pct:.0f}%
    - Classification: APPROPRIATE TEST

    Test may proceed - all diagnostic stewardship criteria satisfied:
    - Age appropriate (≥3 years)
    - Symptomatic (≥3 liquid stools)
    - No confounders (laxatives, contrast, GI bleed)
    - Risk factor present (recent antibiotics)
    - Symptoms persistent (>48 hours)
    """)

    return episode_id


def display_dashboard_summary(db: EpisodeDB):
    """Display a summary dashboard of all episodes."""
    print_header("GUIDELINE ADHERENCE DASHBOARD SUMMARY")

    # Get all episodes
    episodes = db.get_active_episodes(limit=10)
    if not episodes:
        # Try to get any episodes including completed
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bundle_episodes ORDER BY created_at DESC LIMIT 10")
            episodes = [db._row_to_episode(row) for row in cursor.fetchall()]

    print(f"\n  Active/Recent Episodes: {len(episodes)}")
    print("\n  " + "-" * 66)
    print(f"  {'MRN':<15} {'Bundle':<25} {'Adherence':<12} {'Status':<10}")
    print("  " + "-" * 66)

    for ep in episodes:
        mrn = ep.patient_mrn or ep.patient_id[:12]
        bundle_name = (ep.bundle_name or ep.bundle_id)[:23]
        adherence = f"{ep.adherence_percentage or 0:.0f}%"
        level = ep.adherence_level or "unknown"

        # Color coding simulation with text
        level_indicator = {
            "full": "(FULL)",
            "partial": "(PART)",
            "low": "(LOW!)",
        }.get(level, "")

        print(f"  {mrn:<15} {bundle_name:<25} {adherence:<12} {level_indicator:<10}")

    # Get active alerts
    alerts = db.get_active_alerts(limit=10)

    print(f"\n  Active Alerts: {len(alerts)}")
    if alerts:
        print("\n  " + "-" * 66)
        print(f"  {'Severity':<10} {'Bundle':<20} {'Element':<25}")
        print("  " + "-" * 66)

        for alert in alerts:
            severity = alert.severity.upper()
            bundle = (alert.bundle_name or "")[:18]
            element = (alert.element_name or "")[:23]
            print(f"  {severity:<10} {bundle:<20} {element:<25}")

    # Adherence stats
    stats = db.get_adherence_stats(days=30)
    if stats:
        print(f"\n  Adherence Statistics (Last 30 Days):")
        print("  " + "-" * 66)
        for bundle_id, s in stats.items():
            name = (s.get("bundle_name") or bundle_id)[:30]
            total = s["total_episodes"]
            avg = s["avg_adherence_pct"] or 0
            print(f"  {name}: {total} episodes, {avg:.1f}% avg adherence")


def main():
    """Run the demo."""
    print_header("AEGIS GUIDELINE ADHERENCE MONITORING - DEMO")

    print("""
    This demo creates sample patient scenarios to demonstrate the
    guideline adherence monitoring system.

    Patients:
    1. Febrile Infant (14 days) - Full adherence example
    2. Sepsis (3 years) - Partial adherence with alerts
    3. Neonatal HSV (10 days) - Critical alert scenario
    4. C. diff Testing (8 years) - Diagnostic stewardship
    """)

    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "demo_guideline_adherence.db")
        print(f"  Demo database: {db_path}")

        # Initialize database
        db = EpisodeDB(db_path)

        # Create patient scenarios
        create_febrile_infant_episode(db)
        create_sepsis_episode(db)
        create_neonatal_hsv_episode(db)
        create_cdiff_testing_episode(db)

        # Display summary dashboard
        display_dashboard_summary(db)

        print_header("DEMO COMPLETE")
        print("""
    Key Observations:

    1. FEBRILE INFANT: 100% adherence - all age-appropriate elements met
       - LP performed (required for 8-21 days)
       - Parenteral antibiotics given
       - HSV risk assessed (no risk factors)
       - Admitted per guideline

    2. SEPSIS: 60% adherence - critical delays identified
       - ALERT: Antibiotic delay (80 min vs 60 min target)
       - ALERT: Repeat lactate not obtained
       - Fluid resuscitation met
       - 48h reassessment pending

    3. NEONATAL HSV: 71% adherence - CRITICAL safety issue
       - CRITICAL: Acyclovir not started (3 hours elapsed!)
       - Workup appropriately sent (CSF, blood, surface cultures)
       - ID consulted
       - Treatment delay increases mortality risk

    4. C. DIFF TESTING: 100% criteria met - appropriate test
       - All diagnostic stewardship criteria satisfied
       - Recent antibiotics = valid risk factor
       - Symptomatic with liquid stools
       - No confounders present

    This system enables:
    - Real-time monitoring of guideline adherence
    - Automated alerts for missed elements
    - Compliance metrics for QI dashboards
    - Joint Commission MM.09.01.01 documentation
        """)


if __name__ == "__main__":
    main()
