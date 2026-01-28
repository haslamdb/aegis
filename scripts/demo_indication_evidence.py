#!/usr/bin/env python3
"""Create demo indication candidates with evidence source attribution.

This script creates test cases to demonstrate the new v2 evidence source
format with provider name, note type, and date attribution.

Usage:
    python scripts/demo_indication_evidence.py
"""

import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent / "antimicrobial-usage-alerts"))

from au_alerts_src.indication_db import IndicationDatabase
from au_alerts_src.models import (
    EvidenceSource,
    IndicationCandidate,
    IndicationExtraction,
    MedicationOrder,
    Patient,
)


def create_demo_cases():
    """Create 4 demo cases with evidence source attribution."""
    db = IndicationDatabase()

    cases = [
        # Case 1: Pneumonia with ID consult - Appropriate (A)
        {
            "mrn": "EVD10001",
            "name": "Emma Wilson",
            "medication": "Ceftriaxone",
            "rxnorm": "309090",
            "location": "4 West",
            "service": "Hospitalist",
            "icd10_codes": ["J18.9"],
            "icd10_classification": "A",
            "llm_classification": "A",
            "final_classification": "A",
            "classification_source": "llm",
            "llm_extracted_indication": "Community-acquired pneumonia",
            "extraction": {
                "indications": ["Community-acquired pneumonia"],
                "supporting_quotes": [
                    "Started on Ceftriaxone for community-acquired pneumonia",
                    "CXR shows right lower lobe infiltrate",
                ],
                "confidence": 0.9,
                "evidence_sources": [
                    {
                        "note_type": "PROGRESS_NOTE",
                        "note_date": (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d"),
                        "author": "Dr. Sarah Chen",
                        "quotes": [
                            "Started on Ceftriaxone 50mg/kg IV q24h for community-acquired pneumonia",
                            "CXR shows right lower lobe infiltrate consistent with bacterial pneumonia",
                        ],
                        "relevance": "Documents initiation of antibiotic with clear indication",
                    },
                    {
                        "note_type": "ID_CONSULT",
                        "note_date": (datetime.now() - timedelta(hours=4)).strftime("%Y-%m-%d"),
                        "author": "Dr. Michael Torres, ID",
                        "quotes": [
                            "Agree with ceftriaxone coverage for CAP",
                            "Continue current antibiotic regimen, can narrow based on cultures",
                        ],
                        "relevance": "ID specialist confirms appropriateness of antibiotic choice",
                    },
                ],
                "notes_filtered_count": 3,
                "notes_total_count": 8,
            },
        },
        # Case 2: Viral URI with inappropriate antibiotics - Never (N)
        {
            "mrn": "EVD10002",
            "name": "James Miller",
            "medication": "Azithromycin",
            "rxnorm": "18631",
            "location": "ED",
            "service": "Emergency",
            "icd10_codes": ["J06.9"],
            "icd10_classification": "N",
            "llm_classification": "N",
            "final_classification": "N",
            "classification_source": "llm",
            "llm_extracted_indication": "Viral upper respiratory infection - antibiotics not indicated",
            "extraction": {
                "indications": [],
                "supporting_quotes": [
                    "Viral URI, antibiotics not indicated",
                    "Family requested antibiotics despite viral presentation",
                ],
                "confidence": 0.85,
                "evidence_sources": [
                    {
                        "note_type": "PROGRESS_NOTE",
                        "note_date": (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d"),
                        "author": "Dr. Lisa Park",
                        "quotes": [
                            "Assessment: Viral upper respiratory infection",
                            "CXR clear, no infiltrates. Rapid flu negative.",
                            "Antibiotics NOT indicated for viral illness",
                        ],
                        "relevance": "Explicitly states viral etiology and antibiotics not indicated",
                    },
                    {
                        "note_type": "NURSING_NOTE",
                        "note_date": (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d"),
                        "author": "RN Johnson",
                        "quotes": [
                            "Family very anxious, asking for antibiotics",
                            "Azithromycin given per parent request",
                        ],
                        "relevance": "Documents antibiotics given despite clinical guidance",
                    },
                ],
                "notes_filtered_count": 2,
                "notes_total_count": 5,
            },
        },
        # Case 3: Sepsis with broad spectrum - Appropriate (A)
        {
            "mrn": "EVD10003",
            "name": "Sophia Rodriguez",
            "medication": "Meropenem",
            "rxnorm": "29561",
            "location": "PICU",
            "service": "Critical Care",
            "icd10_codes": ["A41.9", "R65.20"],
            "icd10_classification": "A",
            "llm_classification": "A",
            "final_classification": "A",
            "classification_source": "llm",
            "llm_extracted_indication": "Sepsis with suspected intra-abdominal source",
            "extraction": {
                "indications": ["Sepsis", "Suspected intra-abdominal infection"],
                "supporting_quotes": [
                    "Septic shock requiring vasopressors",
                    "Broad spectrum coverage with Meropenem initiated",
                ],
                "confidence": 0.95,
                "evidence_sources": [
                    {
                        "note_type": "ADMISSION_NOTE",
                        "note_date": (datetime.now() - timedelta(hours=12)).strftime("%Y-%m-%d"),
                        "author": "Dr. David Kim, PICU",
                        "quotes": [
                            "8 year old transferred from OSH with septic shock",
                            "Lactate 4.8, requiring norepinephrine",
                            "Initiated Meropenem for broad spectrum coverage pending source identification",
                        ],
                        "relevance": "Documents severe sepsis requiring immediate broad spectrum coverage",
                    },
                    {
                        "note_type": "ID_CONSULT",
                        "note_date": (datetime.now() - timedelta(hours=8)).strftime("%Y-%m-%d"),
                        "author": "Dr. Amanda Foster, ID",
                        "quotes": [
                            "Agree with meropenem given clinical severity",
                            "CT abdomen shows possible appendicitis with perforation",
                            "Appropriate empiric coverage for presumed intra-abdominal sepsis",
                        ],
                        "relevance": "ID confirms appropriateness and identifies likely source",
                    },
                    {
                        "note_type": "SURGERY_CONSULT",
                        "note_date": (datetime.now() - timedelta(hours=6)).strftime("%Y-%m-%d"),
                        "author": "Dr. Robert Chang, Surgery",
                        "quotes": [
                            "Perforated appendicitis confirmed on CT",
                            "Will proceed to OR after stabilization",
                        ],
                        "relevance": "Confirms surgical source of infection",
                    },
                ],
                "notes_filtered_count": 4,
                "notes_total_count": 12,
            },
        },
        # Case 4: UTI with appropriate antibiotics - Sometimes (S)
        {
            "mrn": "EVD10004",
            "name": "Oliver Thompson",
            "medication": "Ceftriaxone",
            "rxnorm": "309090",
            "location": "3 East",
            "service": "Hospitalist",
            "icd10_codes": ["N39.0"],
            "icd10_classification": "A",
            "llm_classification": "S",
            "final_classification": "S",
            "classification_source": "llm",
            "llm_extracted_indication": "Urinary tract infection, pending culture",
            "extraction": {
                "indications": ["Urinary tract infection"],
                "supporting_quotes": [
                    "UA positive for nitrites and leukocyte esterase",
                    "Started empiric ceftriaxone for presumed pyelonephritis",
                ],
                "confidence": 0.75,
                "evidence_sources": [
                    {
                        "note_type": "PROGRESS_NOTE",
                        "note_date": (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d"),
                        "author": "Dr. Jennifer Walsh",
                        "quotes": [
                            "2 year old with fever x3 days, foul-smelling urine",
                            "UA: positive nitrites, >50 WBC/hpf, bacteria present",
                            "Started Ceftriaxone 50mg/kg for presumed pyelonephritis",
                            "Urine culture pending - will narrow based on sensitivities",
                        ],
                        "relevance": "Documents UTI diagnosis and empiric antibiotic choice",
                    },
                ],
                "notes_filtered_count": 2,
                "notes_total_count": 6,
            },
        },
    ]

    print("Creating demo indication candidates with evidence sources...\n")

    for case in cases:
        # Create patient
        patient = Patient(
            fhir_id=str(uuid.uuid4()),
            mrn=case["mrn"],
            name=case["name"],
        )

        # Create medication order
        medication = MedicationOrder(
            fhir_id=str(uuid.uuid4()),
            patient_id=patient.fhir_id,
            medication_name=case["medication"],
            rxnorm_code=case["rxnorm"],
            start_date=datetime.now() - timedelta(hours=8),
            status="active",
        )

        # Create candidate
        candidate = IndicationCandidate(
            id=str(uuid.uuid4()),
            patient=patient,
            medication=medication,
            icd10_codes=case["icd10_codes"],
            icd10_classification=case["icd10_classification"],
            icd10_primary_indication=None,
            llm_extracted_indication=case["llm_extracted_indication"],
            llm_classification=case["llm_classification"],
            final_classification=case["final_classification"],
            classification_source=case["classification_source"],
            status="pending",
            location=case["location"],
            service=case["service"],
        )

        # Save candidate
        candidate_id = db.save_candidate(candidate)
        print(f"Created candidate: {case['name']} (MRN: {case['mrn']})")
        print(f"  Medication: {case['medication']}")
        print(f"  Classification: {case['final_classification']} ({case['llm_extracted_indication']})")
        print(f"  Location: {case['location']} / Service: {case['service']}")

        # Create extraction with evidence sources
        evidence_sources = [
            EvidenceSource.from_dict(src)
            for src in case["extraction"]["evidence_sources"]
        ]

        extraction = IndicationExtraction(
            found_indications=case["extraction"]["indications"],
            supporting_quotes=case["extraction"]["supporting_quotes"],
            confidence="HIGH" if case["extraction"]["confidence"] >= 0.8 else "MEDIUM",
            model_used="llama3.2",
            prompt_version="indication_extraction_v2",
            evidence_sources=evidence_sources,
            notes_filtered_count=case["extraction"]["notes_filtered_count"],
            notes_total_count=case["extraction"]["notes_total_count"],
        )

        # Save extraction
        db.save_extraction(candidate_id, extraction)

        num_sources = len(case["extraction"]["evidence_sources"])
        print(f"  Evidence sources: {num_sources} notes")
        for src in case["extraction"]["evidence_sources"]:
            print(f"    - {src['note_type']} by {src['author']} ({src['note_date']})")
        print()

    print("=" * 60)
    print("Demo cases created successfully!")
    print()
    print("View in dashboard:")
    print("  http://localhost:8082/abx-indications/")
    print()
    print("Click on any candidate to see the evidence source attribution.")
    print("=" * 60)


if __name__ == "__main__":
    create_demo_cases()
