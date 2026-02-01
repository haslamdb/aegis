#!/usr/bin/env python3
"""Demo for Clinical Appearance Tiered Extraction.

This script tests the new tiered LLM extraction workflow:
1. Fast triage with qwen2.5:7b (~1 sec)
2. Escalation to llama3.3:70b when ambiguous
3. Training data collection for human review

Usage:
    python demo_clinical_appearance.py           # Run extraction tests
    python demo_clinical_appearance.py --persist # Also create episodes in dashboard
    python demo_clinical_appearance.py --skip-llm # Skip LLM calls, just create training data

After running, check:
- Training data: data/training/clinical_appearance_*.jsonl
- Review queue: http://localhost:8082/guideline-adherence/review
- Training stats: http://localhost:8082/guideline-adherence/training/stats
"""

import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from guideline_src.nlp.clinical_impression import (
    TieredClinicalImpressionExtractor,
    ClinicalAppearance,
    get_tiered_clinical_impression_extractor,
)
from guideline_src.nlp.training_collector import (
    get_training_collector,
    ClinicalAppearanceExtractionRecord,
)
from guideline_src.nlp.triage_extractor import (
    ClinicalAppearanceTriageExtractor,
    TriageDecision,
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


# Sample clinical notes for testing different scenarios
DEMO_CASES = [
    {
        "name": "Clear Well-Appearing (Fast Path)",
        "patient_id": "PT-WELL-001",
        "patient_mrn": "DEMO-WELL-001",
        "age_days": 14,
        "expected_appearance": "well",
        "expected_triage": "fast_path",
        "notes": [
            """
            Chief Complaint: Fever (38.3C at home)

            Physical Exam:
            General: Well-appearing, alert, active infant
            Vitals: T 38.1, HR 145, RR 36, SpO2 99% RA
            Skin: Pink, warm, well-perfused, cap refill <2 sec
            HEENT: Fontanelle soft and flat, TMs clear, oropharynx clear
            Lungs: Clear to auscultation bilaterally, no distress
            CV: Regular rate and rhythm, no murmur
            Abdomen: Soft, non-tender, non-distended
            Neuro: Alert, good tone, strong suck reflex

            Assessment: 14-day-old well-appearing febrile infant
            """,
            """
            Nursing Note (0830):
            Baby feeding well, took 60ml formula without difficulty.
            Active, alert, making good eye contact with parents.
            Consolable when fussy. Parents reassured by baby's activity level.
            Diaper changed - urine output adequate.
            """
        ],
    },
    {
        "name": "Clear Ill-Appearing (Fast Path)",
        "patient_id": "PT-ILL-002",
        "patient_mrn": "DEMO-ILL-002",
        "age_days": 18,
        "expected_appearance": "ill",
        "expected_triage": "fast_path",
        "notes": [
            """
            Chief Complaint: Fever, decreased activity

            Physical Exam:
            General: Ill-appearing, lethargic infant
            Vitals: T 39.2, HR 180, RR 52, SpO2 94% RA
            Skin: Mottled appearance on trunk and extremities, delayed cap refill 4 sec
            HEENT: Fontanelle flat, decreased tearing
            Lungs: Grunting respirations, mild retractions
            CV: Tachycardic, thready pulses
            Abdomen: Soft but distended
            Neuro: Hypotonic, poor suck, difficult to arouse

            Assessment: 18-day-old ill-appearing febrile infant, concern for sepsis
            Plan: Sepsis workup, empiric antibiotics
            """,
            """
            Nursing Note (1145):
            Baby very sleepy, difficult to wake for feeds. Only took 15ml before
            falling back asleep. Weak cry. Color pale with mottling on legs.
            Parents very concerned - say baby is "not himself."
            Notified physician of poor feeding and lethargy.
            """
        ],
    },
    {
        "name": "Toxic-Appearing (Fast Path)",
        "patient_id": "PT-TOXIC-003",
        "patient_mrn": "DEMO-TOXIC-003",
        "age_days": 21,
        "expected_appearance": "toxic",
        "expected_triage": "fast_path",
        "notes": [
            """
            Chief Complaint: Fever, unresponsive episodes

            Physical Exam:
            General: TOXIC-APPEARING, obtunded infant
            Vitals: T 40.1, HR 200, RR 68, BP 55/30, SpO2 88% RA
            Skin: Gray, mottled, cold extremities, cap refill >5 seconds
            HEENT: Sunken fontanelle, no tears
            Lungs: Severe retractions, grunting, nasal flaring
            CV: Tachycardic, weak pulses, gallop rhythm
            Abdomen: Distended, decreased bowel sounds
            Neuro: Obtunded, minimal response to stimulation, seizure activity noted

            Assessment: 21-day-old SEPTIC SHOCK, toxic-appearing
            Plan: Aggressive resuscitation, PICU admission
            """,
            """
            Rapid Response Note:
            Called for infant with acute decompensation. Infant obtunded,
            not responding to voice or touch. Mottled throughout.
            Fluid bolus initiated. Preparing for intubation.
            Parents informed of critical status.
            """
        ],
    },
    {
        "name": "Ambiguous - Conflicting Signals (Escalation)",
        "patient_id": "PT-AMBIG-004",
        "patient_mrn": "DEMO-AMBIG-004",
        "age_days": 16,
        "expected_appearance": "unclear",
        "expected_triage": "escalation",
        "notes": [
            """
            Chief Complaint: Fever

            Physical Exam:
            General: Infant appears alert but irritable
            Vitals: T 38.6, HR 160, RR 42
            Skin: Good color centrally, some mottling on feet (? cold room)
            HEENT: Fontanelle flat
            Lungs: Clear
            CV: Tachycardic but good pulses
            Neuro: Good tone, active

            Assessment: Febrile infant, clinical appearance somewhat reassuring
            but tachycardic and irritable
            """,
            """
            Nursing Note:
            Baby fed 45ml but then vomited. Now taking sips of pedialyte.
            Fusses when examined but quiets when held. Some mottling noted
            on legs but improves with warming. Parents report baby was
            playful this morning but now seems tired.
            """
        ],
    },
    {
        "name": "Poor Documentation (Escalation)",
        "patient_id": "PT-POOR-005",
        "patient_mrn": "DEMO-POOR-005",
        "age_days": 12,
        "expected_appearance": "unknown",
        "expected_triage": "escalation",
        "notes": [
            """
            Chief Complaint: Fever

            Labs ordered: CBC, BMP, UA, Blood culture, CSF studies
            Antibiotics: Ampicillin + Gentamicin

            Disposition: Admit to pediatrics
            """,
            """
            Order placed for IV fluids.
            """
        ],
    },
    {
        "name": "Well with Isolated Concerning Finding (Test Edge Case)",
        "patient_id": "PT-EDGE-006",
        "patient_mrn": "DEMO-EDGE-006",
        "age_days": 25,
        "expected_appearance": "well",
        "expected_triage": "escalation",  # Should escalate due to mottling mention
        "notes": [
            """
            Chief Complaint: Fever x 1 day

            Physical Exam:
            General: Well-appearing infant, alert and active
            Vitals: T 38.4, HR 150, RR 38, SpO2 99%
            Skin: Pink, warm, very mild mottling on feet only (improves with warming)
            HEENT: Normal
            Lungs: Clear
            CV: Normal
            Neuro: Good tone, strong suck

            Assessment: 25-day-old well-appearing febrile infant
            Mild peripheral mottling likely positional/temperature related
            """,
            """
            Nursing Note:
            Baby feeding well, took full bottle. Very alert and active.
            Good color. Parents reassured by baby's behavior.
            Will continue to monitor.
            """
        ],
    },
]


def run_extraction_demo(persist_episodes: bool = False, skip_llm: bool = False):
    """Run the clinical appearance extraction demo."""
    print_header("CLINICAL APPEARANCE TIERED EXTRACTION DEMO")

    # Check extractor availability
    print("\nChecking LLM availability...")

    triage_extractor = ClinicalAppearanceTriageExtractor()
    triage_available = triage_extractor.is_available()
    print(f"  Triage model (qwen2.5:7b): {'Available' if triage_available else 'NOT AVAILABLE'}")

    tiered_extractor = get_tiered_clinical_impression_extractor()
    full_available = tiered_extractor is not None and tiered_extractor.is_available()
    print(f"  Full model (llama3.3:70b): {'Available' if full_available else 'NOT AVAILABLE'}")

    collector = get_training_collector()
    print(f"  Training collector: Ready (storage: {collector.storage_dir})")

    if skip_llm or not full_available:
        print("\n  Running in mock mode (creating training data without LLM calls)")
        run_mock_demo(collector, persist_episodes)
    else:
        print("\n  Running full extraction demo...")
        run_full_demo(tiered_extractor, collector, persist_episodes)


def run_mock_demo(collector, persist_episodes: bool):
    """Create mock training data without calling LLMs."""
    print_header("MOCK TRAINING DATA GENERATION")

    for i, case in enumerate(DEMO_CASES, 1):
        print_subheader(f"Case {i}: {case['name']}")
        print(f"  Patient: {case['patient_mrn']}")
        print(f"  Age: {case['age_days']} days")
        print(f"  Expected: {case['expected_appearance']} ({case['expected_triage']})")

        # Create mock extraction record
        episode_id = 1000 + i  # Mock episode ID

        # Determine mock results based on expected values
        appearance = case['expected_appearance']
        escalated = case['expected_triage'] == 'escalation'

        # Mock triage result values
        if appearance == 'well':
            confidence = 'high'
            doc_quality = 'detailed'
            concerning = []
            reassuring = ['Alert', 'Feeding well', 'Good color']
        elif appearance == 'ill':
            confidence = 'high'
            doc_quality = 'detailed'
            concerning = ['Lethargic', 'Mottled', 'Poor feeding']
            reassuring = []
        elif appearance == 'toxic':
            confidence = 'high'
            doc_quality = 'detailed'
            concerning = ['Obtunded', 'Shock', 'Mottled', 'Unresponsive']
            reassuring = []
        else:
            confidence = 'low'
            doc_quality = 'limited' if 'Poor' in case['name'] else 'adequate'
            concerning = ['Unclear findings']
            reassuring = ['Some reassuring signs']

        # Log to training collector
        record_id = collector.log_extraction(
            episode_id=episode_id,
            patient_id=case['patient_id'],
            patient_mrn=case['patient_mrn'],
            input_notes=case['notes'],
            patient_age_days=case['age_days'],
            triage_result=None,  # Mock - no actual triage result
            full_result=None,    # Mock - no actual full result
            final_appearance=appearance,
            final_confidence=confidence,
            concerning_signs=concerning,
            reassuring_signs=reassuring,
        )

        # Manually update the record with mock triage data
        record = collector.get_record(record_id)
        if record:
            record.triage_model = 'qwen2.5:7b (mock)'
            record.triage_decision = 'needs_full' if escalated else f'clear_{appearance}'
            record.triage_escalated = escalated
            record.triage_escalation_reasons = ['Mock escalation'] if escalated else []
            record.triage_confidence = confidence
            record.triage_documentation_quality = doc_quality
            record.triage_response_time_ms = 500  # Mock fast time

            if escalated:
                record.full_model = 'llama3.3:70b (mock)'
                record.full_extraction_done = True
                record.full_response_time_ms = 30000  # Mock slower time

        print(f"  Logged extraction: {record_id}")
        print(f"    Appearance: {appearance}")
        print(f"    Confidence: {confidence}")
        print(f"    Escalated: {escalated}")
        print(f"    Concerning: {concerning}")
        print(f"    Reassuring: {reassuring}")

    # Create episode records if requested
    if persist_episodes:
        print_subheader("Creating Dashboard Episodes")
        create_dashboard_episodes()

    print_results_summary(collector)


def run_full_demo(extractor, collector, persist_episodes: bool):
    """Run full extraction demo with actual LLM calls."""
    print_header("FULL TIERED EXTRACTION")

    results = []

    for i, case in enumerate(DEMO_CASES, 1):
        print_subheader(f"Case {i}: {case['name']}")
        print(f"  Patient: {case['patient_mrn']}")
        print(f"  Age: {case['age_days']} days")
        print(f"  Expected: {case['expected_appearance']} ({case['expected_triage']})")

        episode_id = 1000 + i

        print("\n  Running tiered extraction...")
        result = extractor.extract(
            notes=case['notes'],
            episode_id=episode_id,
            patient_id=case['patient_id'],
            patient_mrn=case['patient_mrn'],
            patient_age_days=case['age_days'],
        )

        # Get the logged training record
        record = collector.get_record_by_episode(episode_id)

        print(f"\n  Results:")
        print(f"    Appearance: {result.appearance.value}")
        print(f"    Confidence: {result.confidence}")
        print(f"    Model: {result.model_used}")
        print(f"    Response time: {result.response_time_ms}ms")

        if record:
            print(f"    Triage escalated: {record.triage_escalated}")
            if record.triage_escalation_reasons:
                print(f"    Escalation reasons: {record.triage_escalation_reasons}")

        if result.concerning_signs:
            print(f"    Concerning: {result.concerning_signs[:3]}")
        if result.reassuring_signs:
            print(f"    Reassuring: {result.reassuring_signs[:3]}")

        # Check if result matches expectation
        actual_appearance = result.appearance.value.replace('_appearing', '')
        expected = case['expected_appearance']
        match = "MATCH" if actual_appearance == expected else f"MISMATCH (expected {expected})"
        print(f"    Expectation: {match}")

        results.append({
            'case': case['name'],
            'expected': expected,
            'actual': actual_appearance,
            'matched': actual_appearance == expected,
            'escalated': record.triage_escalated if record else None,
            'time_ms': result.response_time_ms,
        })

    # Create episodes if requested
    if persist_episodes:
        print_subheader("Creating Dashboard Episodes")
        create_dashboard_episodes()

    print_results_summary(collector)

    # Summary table
    print_header("EXTRACTION SUMMARY")
    print("\n  {:40} {:10} {:10} {:8} {:8}".format(
        "Case", "Expected", "Actual", "Match", "Time"
    ))
    print("  " + "-" * 80)
    for r in results:
        match_str = "Yes" if r['matched'] else "NO"
        esc_str = "Esc" if r['escalated'] else "Fast"
        print("  {:40} {:10} {:10} {:8} {:>6}ms ({})".format(
            r['case'][:38],
            r['expected'],
            r['actual'],
            match_str,
            r['time_ms'],
            esc_str,
        ))


def create_dashboard_episodes():
    """Create episodes in the dashboard database for testing review workflow."""
    try:
        from guideline_src.episode_db import EpisodeDB, BundleEpisode
        from guideline_src.config import Config

        db = EpisodeDB(str(Config.ADHERENCE_DB_PATH))

        for i, case in enumerate(DEMO_CASES, 1):
            episode = BundleEpisode(
                patient_id=case['patient_id'],
                patient_mrn=case['patient_mrn'],
                encounter_id=f"ENC-DEMO-{i:03d}",
                bundle_id="febrile_infant_2024",
                bundle_name="Febrile Infant Bundle (Demo)",
                trigger_type="diagnosis",
                trigger_code="R50.9",
                trigger_description="Fever - Demo Case",
                trigger_time=datetime.now() - timedelta(hours=i),
                patient_age_days=case['age_days'],
                patient_unit="Demo Unit",
                status="active",
                clinical_context=f'{{"demo_case": "{case["name"]}", "expected_appearance": "{case["expected_appearance"]}"}}',
            )
            episode_id = db.save_episode(episode)
            print(f"  Created episode {episode_id}: {case['name']}")

    except Exception as e:
        print(f"  Warning: Could not create dashboard episodes: {e}")


def print_results_summary(collector):
    """Print training data statistics."""
    print_header("TRAINING DATA SUMMARY")

    stats = collector.get_stats()

    print(f"""
    Total Extractions: {stats['total_extractions']}
    Human Reviewed: {stats['human_reviewed']} ({stats['review_rate']*100:.0f}%)
    Corrections: {stats['corrections']}

    Triage Performance:
    - Fast Path (triage only): {stats['triage_stats']['triage_only']} ({stats['triage_stats']['fast_path_rate']*100:.0f}%)
    - Escalated to full model: {stats['triage_stats']['triage_escalated']}

    Response Times:
    - Triage avg: {stats['response_times']['triage_avg_ms']:.0f}ms
    - Full avg: {stats['response_times']['full_avg_ms']:.0f}ms

    Appearance Distribution:""")

    for appearance, count in stats['appearance_distribution'].items():
        print(f"    - {appearance}: {count}")

    print(f"""
    Training Data Location:
    {collector.storage_dir}

    Next Steps:
    1. View review queue: http://localhost:8082/guideline-adherence/review
    2. Submit reviews for training data collection
    3. Check stats: http://localhost:8082/guideline-adherence/training/stats
    """)


def main():
    parser = argparse.ArgumentParser(description="Clinical Appearance Extraction Demo")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Also create episodes in dashboard database",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM calls, create mock training data only",
    )
    args = parser.parse_args()

    run_extraction_demo(
        persist_episodes=args.persist,
        skip_llm=args.skip_llm,
    )


if __name__ == "__main__":
    main()
