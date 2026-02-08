"""
Create demo HAI detection data for development and testing.

Generates realistic HAI candidates across all 5 HAI types with
classifications, reviews (some with overrides), and matching Alert records.

Usage:
    python manage.py create_demo_hai                    # Create 20 candidates
    python manage.py create_demo_hai --count 50         # Create 50 candidates
    python manage.py create_demo_hai --clear             # Clear existing, create new
    python manage.py create_demo_hai --clear --count 30  # Clear and create 30
"""

import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.alerts.models import Alert, AlertType, AlertSeverity, AlertStatus
from apps.hai_detection.models import (
    HAICandidate, HAIClassification, HAIReview, LLMAuditLog,
    HAIType, CandidateStatus, ClassificationDecision,
    ReviewQueueType, ReviewerDecision, OverrideReasonCategory,
)


# Demo data scenarios
CLABSI_SCENARIOS = [
    {
        'organism': 'MRSA', 'device_days': 8, 'device_type': 'PICC',
        'location': 'G3NE', 'decision': 'hai_confirmed', 'confidence': 0.92,
    },
    {
        'organism': 'Coagulase-negative Staphylococcus', 'device_days': 3,
        'device_type': 'Triple-lumen CVC', 'location': 'G6SE',
        'decision': 'not_hai', 'confidence': 0.78,
    },
    {
        'organism': 'Escherichia coli', 'device_days': 12,
        'device_type': 'Triple-lumen CVC', 'location': 'G3NW',
        'decision': 'hai_confirmed', 'confidence': 0.88,
    },
    {
        'organism': 'Enterococcus faecalis', 'device_days': 5,
        'device_type': 'Tunneled catheter', 'location': 'G5NE',
        'decision': 'pending_review', 'confidence': 0.65,
    },
]

SSI_SCENARIOS = [
    {
        'organism': 'Escherichia coli', 'procedure': 'COLO',
        'procedure_name': 'Colostomy Revision', 'days_post_op': 7,
        'ssi_type': 'deep', 'location': 'A6N',
        'decision': 'hai_confirmed', 'confidence': 0.91,
    },
    {
        'organism': 'MSSA', 'procedure': 'SB',
        'procedure_name': 'Spinal Fusion', 'days_post_op': 14,
        'ssi_type': 'superficial', 'location': 'A3N',
        'decision': 'hai_confirmed', 'confidence': 0.85,
    },
    {
        'organism': 'Staphylococcus epidermidis', 'procedure': 'CARD',
        'procedure_name': 'Cardiac Surgery', 'days_post_op': 5,
        'ssi_type': None, 'location': 'G6NW',
        'decision': 'not_hai', 'confidence': 0.72,
    },
]

VAE_SCENARIOS = [
    {
        'organism': '', 'device_days': 6, 'location': 'G3SE',
        'fio2_increase': 25.0, 'peep_increase': 4.0,
        'decision': 'hai_confirmed', 'confidence': 0.87,
    },
    {
        'organism': 'Pseudomonas aeruginosa', 'device_days': 10,
        'location': 'G6NE', 'fio2_increase': 22.0, 'peep_increase': 3.5,
        'decision': 'pending_review', 'confidence': 0.68,
    },
]

CAUTI_SCENARIOS = [
    {
        'organism': 'Escherichia coli', 'catheter_days': 5,
        'catheter_type': 'Indwelling Foley', 'location': 'A6S',
        'decision': 'hai_confirmed', 'confidence': 0.90,
    },
    {
        'organism': 'Candida albicans', 'catheter_days': 7,
        'catheter_type': 'Suprapubic', 'location': 'G3NE',
        'decision': 'not_hai', 'confidence': 0.75,
    },
    {
        'organism': 'Klebsiella pneumoniae', 'catheter_days': 4,
        'catheter_type': 'Indwelling Foley', 'location': 'A7C',
        'decision': 'pending_review', 'confidence': 0.62,
    },
]

CDI_SCENARIOS = [
    {
        'organism': 'Clostridioides difficile', 'onset_type': 'ho',
        'specimen_day': 5, 'test_type': 'NAAT/PCR', 'location': 'A4N',
        'decision': 'hai_confirmed', 'confidence': 0.95,
    },
    {
        'organism': 'Clostridioides difficile', 'onset_type': 'co_hcfa',
        'specimen_day': 2, 'test_type': 'Toxin A/B', 'location': 'A6N',
        'decision': 'hai_confirmed', 'confidence': 0.82,
    },
    {
        'organism': 'Clostridioides difficile', 'onset_type': 'ho',
        'specimen_day': 8, 'test_type': 'NAAT/PCR', 'location': 'G5SW',
        'decision': 'not_hai', 'confidence': 0.71,
        'is_duplicate': True,
    },
]

PATIENT_NAMES = [
    'Johnson, Aiden', 'Williams, Sophia', 'Brown, Ethan',
    'Davis, Olivia', 'Miller, Liam', 'Wilson, Mia',
    'Moore, Noah', 'Taylor, Ava', 'Anderson, Mason',
    'Thomas, Charlotte', 'Jackson, Lucas', 'White, Amelia',
    'Harris, Logan', 'Martin, Harper', 'Thompson, James',
    'Garcia, Ella', 'Martinez, Benjamin', 'Robinson, Luna',
    'Clark, Henry', 'Rodriguez, Camila', 'Lewis, Owen',
    'Lee, Lily', 'Walker, Jack', 'Hall, Zoe',
]

REVIEWERS = [
    'Dr. Smith (IP)', 'Nurse Johnson (IP)', 'Dr. Chen (IP)',
    'Nurse Williams (IP)', 'Dr. Patel (IP)',
]

OVERRIDE_REASONS = [
    'Clinical context not captured in notes',
    'Contamination based on clinical picture',
    'NHSN criteria interpretation difference',
    'Missing documentation in EHR',
    'Extraction missed key finding',
]


class Command(BaseCommand):
    help = 'Create demo HAI detection data for development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear existing HAI data before creating',
        )
        parser.add_argument(
            '--count', type=int, default=20,
            help='Number of candidates to create (default: 20)',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write("Clearing existing HAI data...")
            LLMAuditLog.objects.all().delete()
            HAIReview.objects.all().delete()
            HAIClassification.objects.all().delete()
            HAICandidate.objects.all().delete()
            Alert.objects.filter(source_module='hai_detection').delete()
            self.stdout.write(self.style.SUCCESS("  Cleared."))

        count = options['count']
        self.stdout.write(f"Creating {count} demo HAI candidates...")

        # Build scenario pool
        all_scenarios = []
        for s in CLABSI_SCENARIOS:
            all_scenarios.append(('clabsi', s))
        for s in SSI_SCENARIOS:
            all_scenarios.append(('ssi', s))
        for s in VAE_SCENARIOS:
            all_scenarios.append(('vae', s))
        for s in CAUTI_SCENARIOS:
            all_scenarios.append(('cauti', s))
        for s in CDI_SCENARIOS:
            all_scenarios.append(('cdi', s))

        created = 0
        now = timezone.now()

        for i in range(count):
            hai_type, scenario = random.choice(all_scenarios)
            patient_name = random.choice(PATIENT_NAMES)
            mrn = f"MRN{random.randint(100000, 999999)}"
            days_ago = random.randint(1, 45)
            culture_date = now - timedelta(days=days_ago)

            # Build type-specific data
            type_specific = {}
            device_info = None
            device_days = scenario.get('device_days')

            if hai_type == 'clabsi':
                device_info = {
                    'device_type': scenario.get('device_type', 'CVC'),
                    'insertion_date': (culture_date - timedelta(days=device_days)).isoformat(),
                }
            elif hai_type == 'ssi':
                type_specific['ssi'] = {
                    'procedure_name': scenario.get('procedure_name', 'Surgery'),
                    'procedure_code': scenario.get('procedure', 'UNKN'),
                    'nhsn_category': scenario.get('procedure', 'UNKN'),
                    'procedure_date': (culture_date - timedelta(days=scenario.get('days_post_op', 7))).isoformat(),
                    'wound_class': random.choice(['Clean', 'Clean-Contaminated', 'Contaminated']),
                    'implant_used': scenario.get('procedure') in ('HPRO', 'KPRO'),
                    'days_post_op': scenario.get('days_post_op', 7),
                    'surveillance_days': 90 if scenario.get('procedure') in ('HPRO', 'KPRO') else 30,
                }
            elif hai_type == 'vae':
                device_days = scenario.get('device_days', 5)
                type_specific['vae'] = {
                    'vac_onset_date': (culture_date - timedelta(days=1)).isoformat(),
                    'ventilator_day_at_onset': device_days,
                    'baseline_min_fio2': 40.0,
                    'baseline_min_peep': 5.0,
                    'fio2_increase': scenario.get('fio2_increase', 20.0),
                    'peep_increase': scenario.get('peep_increase', 3.0),
                    'intubation_date': (culture_date - timedelta(days=device_days)).isoformat(),
                }
            elif hai_type == 'cauti':
                device_days = scenario.get('catheter_days', 5)
                type_specific['cauti'] = {
                    'catheter_days': device_days,
                    'catheter_type': scenario.get('catheter_type', 'Foley'),
                    'insertion_date': (culture_date - timedelta(days=device_days)).isoformat(),
                    'culture_cfu_ml': 100000,
                    'patient_age': random.randint(40, 85),
                }
            elif hai_type == 'cdi':
                type_specific['cdi'] = {
                    'onset_type': scenario.get('onset_type', 'ho'),
                    'specimen_day': scenario.get('specimen_day', 5),
                    'test_type': scenario.get('test_type', 'NAAT/PCR'),
                    'is_recurrent': False,
                    'is_duplicate': scenario.get('is_duplicate', False),
                    'admission_date': (culture_date - timedelta(days=scenario.get('specimen_day', 5) - 1)).isoformat(),
                }

            # Determine status
            decision = scenario['decision']
            roll = random.random()
            if roll < 0.3:
                status = CandidateStatus.PENDING
            elif roll < 0.5:
                status = CandidateStatus.PENDING_REVIEW
            elif decision == 'hai_confirmed' and roll < 0.8:
                status = CandidateStatus.CONFIRMED
            elif decision == 'not_hai' and roll < 0.8:
                status = CandidateStatus.REJECTED
            else:
                status = CandidateStatus.PENDING_REVIEW

            # Create candidate
            candidate = HAICandidate.objects.create(
                hai_type=hai_type,
                patient_id=f"Patient/{uuid.uuid4()}",
                patient_mrn=mrn,
                patient_name=patient_name,
                patient_location=scenario.get('location', 'General'),
                culture_id=f"Culture/{uuid.uuid4()}",
                culture_date=culture_date,
                organism=scenario.get('organism', ''),
                device_info=device_info,
                device_days_at_culture=device_days,
                status=status,
                type_specific_data=type_specific,
            )

            # Create classification for non-pending candidates
            classification = None
            if status != CandidateStatus.PENDING:
                classification = HAIClassification.objects.create(
                    candidate=candidate,
                    decision=decision,
                    confidence=scenario['confidence'],
                    is_mbi_lcbi=(hai_type == 'clabsi' and decision == 'not_hai' and random.random() < 0.3),
                    supporting_evidence=[
                        {'text': f'Positive culture: {scenario.get("organism", "organism")}', 'source': 'Lab'},
                        {'text': f'Device in place {device_days or "N/A"} days', 'source': 'Nursing'},
                    ],
                    contradicting_evidence=(
                        [{'text': 'Possible contaminant', 'source': 'ID Consult'}]
                        if decision == 'not_hai' else []
                    ),
                    reasoning=f'LLM analysis of clinical notes for {hai_type.upper()} criteria',
                    model_used='llama3.3:70b',
                    prompt_version='v1.0',
                    tokens_used=random.randint(2000, 8000),
                    processing_time_ms=random.randint(5000, 45000),
                    extraction_data={
                        'documentation_quality': random.choice(['adequate', 'detailed']),
                        'notes_reviewed_count': random.randint(3, 12),
                    },
                    rules_result={
                        'meets_criteria': decision == 'hai_confirmed',
                        'strictness': 'nhsn_strict',
                    },
                    strictness_level='nhsn_strict',
                )

                # Create LLM audit log
                LLMAuditLog.objects.create(
                    candidate=candidate,
                    model='llama3.3:70b',
                    success=True,
                    input_tokens=random.randint(3000, 12000),
                    output_tokens=random.randint(500, 2000),
                    response_time_ms=random.randint(5000, 45000),
                )

            # Create review for resolved candidates
            if status in (CandidateStatus.CONFIRMED, CandidateStatus.REJECTED):
                is_override = random.random() < 0.2
                reviewer_decision = (
                    ReviewerDecision.CONFIRMED
                    if status == CandidateStatus.CONFIRMED
                    else ReviewerDecision.REJECTED
                )

                HAIReview.objects.create(
                    candidate=candidate,
                    classification=classification,
                    queue_type=ReviewQueueType.IP_REVIEW,
                    reviewed=True,
                    reviewer=random.choice(REVIEWERS),
                    reviewer_decision=reviewer_decision,
                    reviewer_notes=f'Reviewed per NHSN criteria. {"Override: " + random.choice(OVERRIDE_REASONS) if is_override else "Agrees with LLM classification."}',
                    llm_decision=decision,
                    is_override=is_override,
                    override_reason=random.choice(OVERRIDE_REASONS) if is_override else '',
                    override_reason_category=(
                        random.choice([c[0] for c in OverrideReasonCategory.choices])
                        if is_override else ''
                    ),
                    reviewed_at=now - timedelta(days=random.randint(0, days_ago)),
                )
            elif status == CandidateStatus.PENDING_REVIEW and classification:
                # Pending review entry
                HAIReview.objects.create(
                    candidate=candidate,
                    classification=classification,
                    queue_type=ReviewQueueType.IP_REVIEW,
                    reviewed=False,
                )

            # Create matching Alert
            alert_type_map = {
                'clabsi': AlertType.CLABSI,
                'ssi': AlertType.SSI,
                'cauti': AlertType.CAUTI,
                'vae': AlertType.VAE,
                'cdi': AlertType.CDI,
            }
            alert_status = AlertStatus.RESOLVED if status in (CandidateStatus.CONFIRMED, CandidateStatus.REJECTED) else AlertStatus.PENDING
            Alert.objects.create(
                alert_type=alert_type_map[hai_type],
                source_module='hai_detection',
                source_id=str(candidate.id),
                title=f"{hai_type.upper()} Candidate: {mrn}",
                summary=f"{scenario.get('organism', 'HAI signal')} detected in {scenario.get('location', 'unit')}",
                details={
                    'organism': scenario.get('organism', ''),
                    'culture_date': culture_date.isoformat(),
                    'device_days': device_days,
                },
                patient_id=candidate.patient_id,
                patient_mrn=mrn,
                patient_name=patient_name,
                patient_location=scenario.get('location', ''),
                severity=AlertSeverity.HIGH,
                status=alert_status,
            )

            created += 1

        self.stdout.write(self.style.SUCCESS(f"\nCreated {created} HAI candidates with classifications and reviews."))

        # Summary
        for hai_type in HAIType:
            count_type = HAICandidate.objects.filter(hai_type=hai_type).count()
            if count_type > 0:
                self.stdout.write(f"  {hai_type.label}: {count_type}")
