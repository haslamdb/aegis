#!/usr/bin/env python3
"""Test LLM-based indication extraction with realistic clinical notes.

Tests the indication extractor with sample notes representing:
1. Clear bacterial infection (should find indication)
2. Viral illness (should flag as inappropriate)
3. No documented indication
"""

import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


# Sample clinical notes for testing - realistic multi-note scenarios
# Each scenario has 8-12 notes like real HAI classification

# Irrelevant notes that would be mixed in (nursing, dietary, PT, social work, etc.)
IRRELEVANT_NOTES = [
    """
    NURSING NOTE - 0800

    Patient resting comfortably. Vital signs stable. IV site clean and dry, no signs
    of infiltration. Patient ate 75% of breakfast. Ambulated to bathroom with assistance.
    Fall risk precautions in place. Call light within reach. Will continue to monitor.

    Pain level: 3/10, managed with scheduled acetaminophen.
    Skin assessment: Intact, no pressure injuries noted.
    """,
    """
    PHYSICAL THERAPY NOTE

    Patient seen for mobility assessment and gait training. Patient able to transfer
    from bed to chair with minimal assistance. Ambulated 50 feet in hallway with
    rolling walker and supervision. Gait steady, no loss of balance. Patient reports
    mild fatigue after ambulation but no shortness of breath or chest pain.

    PLAN: Continue daily PT sessions, progress to independent ambulation as tolerated.
    Recommend home PT evaluation prior to discharge.
    """,
    """
    DIETARY CONSULT

    Reason for consult: Diabetic diet education

    Patient is a 68 y/o male with type 2 diabetes. Current diet order: Consistent
    carbohydrate diet (60g CHO per meal). Patient reports understanding of carb
    counting basics but would benefit from refresher education.

    Discussed meal planning, portion sizes, and importance of consistent timing.
    Patient engaged and asking appropriate questions.

    RECOMMENDATION: Continue current diet order. Provided written materials for
    reference. Follow up PRN.
    """,
    """
    SOCIAL WORK NOTE

    Met with patient and family to discuss discharge planning. Patient lives alone
    in a single-story home. Has daughter who lives nearby and can assist with
    transportation to follow-up appointments. Patient has Medicare Part A and B.

    No concerns with medication access - patient uses local pharmacy with delivery.
    Patient reports adequate support system and denies need for additional resources
    at this time.

    PLAN: Will coordinate with case management for home health referral if needed.
    """,
    """
    CASE MANAGEMENT NOTE

    Reviewed patient for discharge planning needs. Current anticipated LOS 2-3 more days
    per primary team. Insurance verified: Medicare with supplement.

    DME needs: None anticipated at this time.
    Home health: May need visiting nurse for wound check - will reassess closer to discharge.
    SNF: Not indicated - patient has good functional status and support at home.

    Will continue to follow and update plan as needed.
    """,
    """
    PHARMACY NOTE - Medication Reconciliation

    Completed admission medication reconciliation with patient and daughter.
    Home medications verified against pharmacy records:
    - Metformin 1000mg BID
    - Lisinopril 20mg daily
    - Atorvastatin 40mg daily
    - Aspirin 81mg daily
    - Metoprolol succinate 50mg daily

    No discrepancies noted. All home medications continued per primary team.
    No drug interactions identified with current inpatient medications.
    """,
    """
    RESPIRATORY THERAPY NOTE

    Patient on 2L NC with SpO2 94-96%. Breath sounds diminished at bases bilaterally.
    Encouraged incentive spirometry - patient performing 10 reps hourly while awake.
    No acute respiratory distress. Will continue to monitor and titrate O2 as needed
    for goal SpO2 >92%.
    """,
    """
    NURSING NOTE - 1600

    Received patient from radiology after CT scan. Patient tolerated procedure well.
    Vital signs stable post-procedure. IV contrast given - monitoring for reaction,
    none noted. Encouraging oral fluids. Patient voided 300mL clear yellow urine.
    No complaints at this time.
    """,
]

SAMPLE_NOTES = {
    "pneumonia": [
        # Admission H&P (relevant)
        """
        ADMISSION HISTORY AND PHYSICAL

        CHIEF COMPLAINT: Shortness of breath, cough

        HPI: 68 y/o male with history of COPD, HTN, DM2 presents with 5 days of
        progressively worsening shortness of breath and productive cough with
        yellowish sputum. Reports fever to 101.8F at home. Denies chest pain,
        hemoptysis, or leg swelling. Has been using albuterol inhaler more frequently
        without relief.

        PMH: COPD (on home O2 at night), HTN, DM2, former smoker (quit 10 years ago)
        PSH: Appendectomy (1985)
        MEDS: Metformin, lisinopril, tiotropium, albuterol PRN
        ALLERGIES: Penicillin (rash)

        EXAM:
        Vitals: T 100.4F, HR 98, BP 128/76, RR 22, SpO2 88% on RA -> 94% on 2L NC
        General: Ill-appearing, using accessory muscles
        Lungs: Crackles in RLL, decreased breath sounds at base, scattered wheezes
        CV: Tachycardic, regular, no murmurs
        Abd: Soft, NT, ND

        LABS: WBC 14.2, Hgb 13.1, Plt 245, BMP wnl, Procalcitonin 1.8

        IMAGING: CXR shows right lower lobe consolidation

        ASSESSMENT/PLAN:
        1. Community-acquired pneumonia - will start ceftriaxone + azithromycin
           (avoiding fluoroquinolones given age). Blood and sputum cultures ordered.
        2. COPD exacerbation - continue home inhalers, add prednisone burst
        3. Hypoxia - supplemental O2 for goal SpO2 >92%

        Admit to medicine, telemetry for cardiac monitoring given tachycardia.
        """,
        # Day 1 progress note (relevant)
        """
        PROGRESS NOTE - Hospital Day 1

        SUBJECTIVE:
        Patient reports feeling slightly better. Cough still productive but less
        frequent. Breathing easier on oxygen. Slept reasonably well overnight.
        No chest pain or hemoptysis.

        OBJECTIVE:
        Vitals: Tmax 100.2F, currently 99.1F, HR 88, BP 132/78, RR 18, SpO2 94% on 2L
        Lungs: Crackles in RLL, improved air movement compared to admission
        Labs: WBC 12.8 (trending down), procalcitonin pending repeat

        Micro: Blood cultures NGTD at 24h, sputum culture pending

        ASSESSMENT/PLAN:
        1. CAP - clinically improving on ceftriaxone/azithromycin. Continue current
           antibiotics. Will plan for 5-day course if continues to improve.
        2. COPD - tolerating prednisone, continue taper
        3. O2 requirement - wean as tolerated
        """,
        # ID consult (relevant)
        """
        INFECTIOUS DISEASE CONSULT

        Reason for consult: Pneumonia in patient with PCN allergy

        Thank you for this consultation.

        IMPRESSION:
        68 y/o male with community-acquired pneumonia, CURB-65 score of 2 (moderate
        severity). Currently on ceftriaxone + azithromycin which is appropriate
        coverage. Patient has documented penicillin allergy (rash) - ceftriaxone
        is acceptable given low cross-reactivity risk with rash-only history.

        Sputum culture growing normal respiratory flora. Blood cultures negative
        at 48 hours - will follow to final.

        RECOMMENDATIONS:
        1. Continue current antibiotic regimen
        2. Total duration 5 days from clinical improvement (anticipated completion
           in 3 more days)
        3. No need for PO transition - ceftriaxone once daily is convenient and
           bioavailability of oral alternatives is adequate
        4. If patient worsens or fails to improve, consider broadening coverage
           and repeat imaging
        5. Recommend pneumococcal and influenza vaccines prior to discharge if
           not up to date

        Thank you for involving us in this patient's care.
        """,
        # Day 2 progress note (relevant)
        """
        PROGRESS NOTE - Hospital Day 2

        S: Patient feeling much better. Cough improving, less sputum production.
        Appetite returning. Ambulated in hallway without significant dyspnea.

        O:
        Vitals: Afebrile x 24h, HR 78, BP 128/74, RR 16, SpO2 96% on 1L NC
        Lungs: Crackles resolving, good air movement
        Labs: WBC 9.8 (normalized)

        A/P:
        1. CAP - excellent clinical response. Day 3 of antibiotics (ceftriaxone/azithro).
           Per ID, plan for 5-day total course. May complete as outpatient if stable.
        2. COPD - stable, prednisone taper ongoing
        3. Hypoxia - resolving, will trial room air today

        Anticipate discharge tomorrow if continues to improve.
        """,
        # Nursing notes and other irrelevant notes mixed in
        IRRELEVANT_NOTES[0],
        IRRELEVANT_NOTES[1],
        IRRELEVANT_NOTES[2],
        IRRELEVANT_NOTES[3],
        IRRELEVANT_NOTES[4],
        IRRELEVANT_NOTES[5],
        IRRELEVANT_NOTES[6],
        IRRELEVANT_NOTES[7],
    ],
    "viral_uri": [
        # ED note (relevant - shows no indication)
        """
        EMERGENCY DEPARTMENT NOTE

        CHIEF COMPLAINT: Sore throat, runny nose x 3 days

        HPI: 32 y/o healthy female presents with 3 days of sore throat, rhinorrhea,
        and mild cough. Denies fever, though reports feeling "feverish." No shortness
        of breath, no trouble swallowing. Symptoms consistent with URI. Multiple
        sick contacts at work - several coworkers with similar symptoms.

        No recent travel. No known COVID exposure. Vaccinated and boosted.

        PMH: None
        MEDS: OCP
        ALLERGIES: NKDA

        EXAM:
        Vitals: T 98.6F, HR 72, BP 118/70, RR 14, SpO2 99% RA
        General: Well-appearing, NAD
        HEENT: TMs clear, pharynx with mild erythema, no exudates, no tonsillar
               enlargement or asymmetry
        Neck: Supple, no lymphadenopathy
        Lungs: Clear bilaterally, no wheezes/rhonchi/rales
        CV: RRR, no murmurs

        TESTING:
        Rapid strep: Negative
        COVID rapid: Negative
        Flu A/B rapid: Negative

        ASSESSMENT: Viral upper respiratory infection

        PLAN:
        - Supportive care: rest, fluids, honey for cough
        - OTC analgesics (ibuprofen, acetaminophen) for symptom relief
        - Saline nasal spray for congestion
        - Return precautions: high fever, worsening symptoms, difficulty breathing

        Patient requested antibiotics. I discussed that this appears to be a viral
        infection and antibiotics are not indicated. Explained that antibiotics
        will not help viral infections and can cause side effects and contribute
        to antibiotic resistance. Patient verbalized understanding and agreed with
        plan for supportive care.

        DISPOSITION: Discharged home in stable condition
        """,
        # Triage note
        """
        TRIAGE NOTE

        32 y/o female presents with cold symptoms x 3 days. Sore throat, runny nose,
        mild cough. Denies fever, SOB, chest pain. No known COVID exposure.

        Vitals: T 98.4, HR 74, BP 116/72, RR 14, SpO2 99%

        Acuity: ESI 5 (non-urgent)

        Patient placed in fast track area.
        """,
        # Nursing note
        """
        ED NURSING NOTE

        Patient arrived ambulatory, in no distress. Chief complaint of cold symptoms.
        Vital signs obtained and documented. Patient comfortable, no acute needs.
        Rapid strep and COVID tests collected per protocol. Patient informed of
        expected wait time. Call light in reach.
        """,
        IRRELEVANT_NOTES[0],
        IRRELEVANT_NOTES[2],
    ],
    "no_indication": [
        # Post-op day 1
        """
        SURGERY PROGRESS NOTE - POD 1

        Procedure: Laparoscopic cholecystectomy (yesterday)

        S: Patient reports mild incisional pain, 4/10, well-controlled with PO pain meds.
        Tolerating clear liquids. Passed flatus. No nausea or vomiting.

        O:
        Vitals: T 98.8F, HR 76, BP 124/78
        Abd: Soft, appropriately tender at port sites, no rebound/guarding
        Incisions: Clean, dry, intact, no erythema or drainage

        A/P:
        1. S/p lap chole - recovering well, advance diet as tolerated
        2. Pain - continue current regimen
        3. DVT prophylaxis - continue SCDs and ambulation

        Anticipate discharge today if tolerating regular diet.
        """,
        # Post-op day 2
        """
        SURGERY PROGRESS NOTE - POD 2

        S: Patient feeling well. Tolerating regular diet. Having bowel movements.
        Pain minimal, declining pain medication. Ambulating independently.

        O:
        Vitals: Afebrile, VSS
        Abd: Soft, NT, ND
        Incisions: Healing well, no signs of infection

        A/P:
        1. S/p lap chole POD 2 - excellent recovery
        2. Ready for discharge

        DISCHARGE INSTRUCTIONS:
        - Regular diet
        - Activity as tolerated, no heavy lifting >10 lbs for 2 weeks
        - Incision care: keep clean and dry, may shower
        - Follow up in clinic in 2 weeks
        - Return for fever >101.5, worsening pain, redness/drainage from incisions
        """,
        # Pre-op note
        """
        PRE-OPERATIVE NOTE

        Patient: 45 y/o female
        Procedure: Laparoscopic cholecystectomy
        Indication: Symptomatic cholelithiasis with recurrent biliary colic

        PMH: HTN, obesity
        PSH: C-section x2
        MEDS: Lisinopril 10mg daily
        ALLERGIES: NKDA

        Pre-op labs: CBC, BMP, LFTs all within normal limits
        EKG: Normal sinus rhythm

        Patient consented for procedure. Risks, benefits, and alternatives discussed.
        NPO after midnight. Surgical site marked.
        """,
        IRRELEVANT_NOTES[0],
        IRRELEVANT_NOTES[1],
        IRRELEVANT_NOTES[3],
        IRRELEVANT_NOTES[4],
        IRRELEVANT_NOTES[5],
        IRRELEVANT_NOTES[6],
    ],
    "sepsis": [
        # ED note
        """
        EMERGENCY DEPARTMENT NOTE

        CHIEF COMPLAINT: Fever, altered mental status

        HPI: 72 y/o female with history of DM2, HTN, recurrent UTIs brought in by
        family for fever and confusion. Per family, patient was in her usual state
        of health until 2 days ago when she developed urinary frequency and dysuria.
        Today found to be confused and febrile to 102F at home.

        PMH: DM2, HTN, recurrent UTIs, mild dementia at baseline
        MEDS: Metformin, lisinopril, donepezil
        ALLERGIES: Sulfa (hives)

        EXAM:
        Vitals: T 102.8F, HR 118, BP 82/50, RR 24, SpO2 94% RA
        General: Elderly female, drowsy but arousable, oriented to self only
        CV: Tachycardic, regular
        Lungs: Clear
        Abd: Soft, mild suprapubic tenderness
        Skin: Warm, dry, no rashes

        LABS:
        WBC 18.4 with left shift
        Lactate 4.2
        Cr 1.8 (baseline 1.0)
        UA: Large LE, positive nitrites, >100 WBC, bacteria

        ASSESSMENT: Sepsis secondary to UTI, likely pyelonephritis

        PLAN:
        - 30 mL/kg crystalloid bolus
        - Blood and urine cultures obtained
        - Empiric antibiotics: ceftriaxone 2g IV (avoiding fluoroquinolones given
          altered mental status and sulfa allergy)
        - Admit to ICU for monitoring given hypotension

        Sepsis bundle initiated. Time zero documented.
        """,
        # ICU admission note
        """
        ICU ADMISSION NOTE

        Admitted from ED with sepsis secondary to UTI.

        Patient required additional 2L fluid boluses in ED with minimal BP response.
        Started on norepinephrine for MAP goal >65.

        Current status:
        - MAP 62 on norepinephrine 0.08 mcg/kg/min
        - Lactate 3.8 (down from 4.2)
        - UOP 20 mL/hr

        A/P:
        1. Septic shock - UTI source
           - Continue ceftriaxone, consider adding vancomycin if no improvement
           - Aggressive fluid resuscitation
           - Titrate pressors for MAP >65
        2. AKI - likely prerenal/ATN, monitor closely
        3. Altered mental status - likely toxic-metabolic from sepsis
        """,
        # ICU day 1 progress
        """
        ICU PROGRESS NOTE - Day 1

        Events overnight: Required uptitration of norepinephrine to 0.15 mcg/kg/min.
        Lactate peaked at 4.2, now downtrending to 2.8.

        SUBJECTIVE: Intubated overnight for airway protection given worsening mental
        status. Currently sedated.

        OBJECTIVE:
        T 101.2F, HR 102, BP 92/58 on norepinephrine 0.12 mcg/kg/min
        MAP 68, CVP 12

        Vent: AC 16/450/5/40%, ABG 7.34/38/92

        LABS:
        WBC 22.4 with 15% bands
        Procalcitonin 18.6
        Lactate 2.8
        Cr 2.1

        MICRO:
        Blood cultures x2: Gram negative rods (prelim) - likely E. coli
        Urine culture: >100k E. coli

        ASSESSMENT/PLAN:
        1. Septic shock, urinary source with E. coli bacteremia
           - Continue ceftriaxone - appropriate coverage for E. coli
           - Final sensitivities pending, will narrow when available
           - Weaning vasopressors as tolerated, lactate improving
        2. Respiratory failure - intubated for airway protection
           - Wean FiO2 and sedation as sepsis improves
        3. AKI - creatinine stable, UOP improving with resuscitation
        """,
        # ID consult
        """
        INFECTIOUS DISEASE CONSULT

        Reason for consult: E. coli bacteremia and UTI

        IMPRESSION:
        72 y/o female with septic shock secondary to E. coli urosepsis. Blood and
        urine cultures both growing E. coli - sensitivities pending but community
        E. coli typically susceptible to ceftriaxone.

        Current antibiotic (ceftriaxone) is appropriate. Patient is improving
        clinically with downtrending lactate and vasopressor requirements.

        RECOMMENDATIONS:
        1. Continue ceftriaxone 2g IV daily
        2. Anticipate 14-day course for bacteremia (from first negative blood culture)
        3. Renal ultrasound to rule out obstruction/abscess given severity
        4. When sensitivities available, can consider transition to narrower agent
        5. Given recurrent UTIs, would recommend outpatient urology follow-up

        Will continue to follow. Thank you for this consultation.
        """,
        IRRELEVANT_NOTES[0],
        IRRELEVANT_NOTES[4],
        IRRELEVANT_NOTES[5],
        IRRELEVANT_NOTES[6],
        IRRELEVANT_NOTES[7],
    ],
}


def test_extraction(scenario: str, notes: list[str], medication: str) -> dict:
    """Run extraction test for a scenario.

    Args:
        scenario: Name of the test scenario
        notes: Clinical notes to analyze
        medication: Antibiotic being evaluated

    Returns:
        Dict with extraction results and timing
    """
    from au_alerts_src.llm_extractor import IndicationExtractor

    total_chars = sum(len(n) for n in notes)

    print(f"\n{'=' * 60}")
    print(f"Scenario: {scenario}")
    print(f"Medication: {medication}")
    print(f"Notes: {len(notes)} ({total_chars:,} chars)")
    print("=" * 60)

    extractor = IndicationExtractor()

    start = time.time()
    result = extractor.extract(notes=notes, medication=medication)
    elapsed = time.time() - start

    print(f"\nResults ({elapsed:.1f}s):")
    print(f"  Found indications: {result.found_indications}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Supporting quotes: {result.supporting_quotes[:2] if result.supporting_quotes else []}")

    return {
        "scenario": scenario,
        "medication": medication,
        "num_notes": len(notes),
        "total_chars": total_chars,
        "indications": result.found_indications,
        "confidence": result.confidence,
        "elapsed_seconds": elapsed,
    }


def main():
    """Run all extraction tests."""
    from au_alerts_src.llm_extractor import check_llm_availability

    print("#" * 60)
    print("# Antibiotic Indication Extraction Test")
    print("# Testing LLM extraction with realistic clinical notes")
    print("#" * 60)

    # Check LLM availability
    available, msg = check_llm_availability()
    print(f"\n{msg}")

    if not available:
        print("ERROR: LLM not available. Exiting.")
        return

    results = []

    # Test 1: Clear bacterial pneumonia - should find indication
    results.append(test_extraction(
        scenario="Community-acquired pneumonia",
        notes=SAMPLE_NOTES["pneumonia"],
        medication="Ceftriaxone",
    ))

    # Test 2: Viral URI - should flag as inappropriate
    results.append(test_extraction(
        scenario="Viral URI (antibiotics not indicated)",
        notes=SAMPLE_NOTES["viral_uri"],
        medication="Azithromycin",
    ))

    # Test 3: No indication documented
    results.append(test_extraction(
        scenario="Post-op (no infection)",
        notes=SAMPLE_NOTES["no_indication"],
        medication="Cefazolin",
    ))

    # Test 4: Sepsis - clear indication
    results.append(test_extraction(
        scenario="Septic shock",
        notes=SAMPLE_NOTES["sepsis"],
        medication="Vancomycin",
    ))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_time = sum(r["elapsed_seconds"] for r in results)
    avg_time = total_time / len(results)

    print(f"\nTotal extraction time: {total_time:.1f}s")
    print(f"Average per patient: {avg_time:.1f}s")
    print(f"Estimated throughput: {3600/avg_time:.0f} patients/hour")
    print(f"Estimated daily capacity: {3600/avg_time * 24:.0f} patients/day")

    print("\nResults by scenario:")
    for r in results:
        status = "FOUND" if r["indications"] else "NONE"
        print(f"  {r['scenario']}: {status} ({r['confidence']}) - {r['num_notes']} notes, {r['total_chars']:,} chars, {r['elapsed_seconds']:.1f}s")


if __name__ == "__main__":
    main()
