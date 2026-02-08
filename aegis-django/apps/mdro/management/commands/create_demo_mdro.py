"""
Management command to create demo MDRO surveillance data.

Usage:
    python manage.py create_demo_mdro              # Create 10 demo cases
    python manage.py create_demo_mdro --clear       # Clear existing demo data first
    python manage.py create_demo_mdro --count 20    # Create 20 cases
"""

import random
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity
from apps.mdro.models import (
    MDROCase, MDROReview, MDROProcessingLog,
    MDROTypeChoices, TransmissionStatusChoices,
)


DEMO_PATIENTS = [
    {'name': 'Johnson, Aiden', 'mrn': 'MRN-100234', 'id': 'P-100234'},
    {'name': 'Williams, Sophia', 'mrn': 'MRN-100567', 'id': 'P-100567'},
    {'name': 'Davis, Liam', 'mrn': 'MRN-100891', 'id': 'P-100891'},
    {'name': 'Martinez, Isabella', 'mrn': 'MRN-101123', 'id': 'P-101123'},
    {'name': 'Brown, Ethan', 'mrn': 'MRN-101456', 'id': 'P-101456'},
    {'name': 'Thompson, Olivia', 'mrn': 'MRN-101789', 'id': 'P-101789'},
    {'name': 'Garcia, Noah', 'mrn': 'MRN-102012', 'id': 'P-102012'},
    {'name': 'Anderson, Emma', 'mrn': 'MRN-102345', 'id': 'P-102345'},
    {'name': 'Wilson, Mason', 'mrn': 'MRN-102678', 'id': 'P-102678'},
    {'name': 'Lee, Mia', 'mrn': 'MRN-102901', 'id': 'P-102901'},
]

DEMO_UNITS = [
    'G3NE', 'G3NW', 'G1NE', 'G1SW', 'G4NW',  # PICU, NICU
    'G6SE', 'G6NW',  # CICU
    'G5NE', 'G5SW',  # BMT
    'A6N', 'A6S',  # Hospital Medicine
    'A4N', 'A5N1',  # GI / Hematology
    'A3N', 'A7C',  # Ortho, Neuro
    'ED Inpatient',
]

DEMO_SCENARIOS = [
    {
        'mdro_type': MDROTypeChoices.MRSA,
        'organism': 'Staphylococcus aureus',
        'specimen_type': 'Blood',
        'resistant_antibiotics': ['oxacillin', 'cefoxitin'],
        'classification_reason': 'Staph aureus resistant to oxacillin',
        'susceptibilities': [
            {'antibiotic': 'oxacillin', 'result': 'R', 'mic': '>2'},
            {'antibiotic': 'cefoxitin', 'result': 'R', 'mic': '>8'},
            {'antibiotic': 'vancomycin', 'result': 'S', 'mic': '1.0'},
            {'antibiotic': 'daptomycin', 'result': 'S', 'mic': '0.5'},
            {'antibiotic': 'linezolid', 'result': 'S', 'mic': '2.0'},
            {'antibiotic': 'tmp-smx', 'result': 'S', 'mic': '<=0.5'},
        ],
    },
    {
        'mdro_type': MDROTypeChoices.VRE,
        'organism': 'Enterococcus faecium',
        'specimen_type': 'Rectal Swab',
        'resistant_antibiotics': ['vancomycin'],
        'classification_reason': 'Enterococcus resistant to vancomycin',
        'susceptibilities': [
            {'antibiotic': 'vancomycin', 'result': 'R', 'mic': '>256'},
            {'antibiotic': 'ampicillin', 'result': 'R', 'mic': '>32'},
            {'antibiotic': 'daptomycin', 'result': 'S', 'mic': '2.0'},
            {'antibiotic': 'linezolid', 'result': 'S', 'mic': '1.0'},
        ],
    },
    {
        'mdro_type': MDROTypeChoices.CRE,
        'organism': 'Klebsiella pneumoniae',
        'specimen_type': 'Urine',
        'resistant_antibiotics': ['meropenem', 'ertapenem'],
        'classification_reason': 'Enterobacteriaceae resistant to meropenem, ertapenem',
        'susceptibilities': [
            {'antibiotic': 'meropenem', 'result': 'R', 'mic': '>8'},
            {'antibiotic': 'ertapenem', 'result': 'R', 'mic': '>4'},
            {'antibiotic': 'ceftriaxone', 'result': 'R', 'mic': '>32'},
            {'antibiotic': 'ciprofloxacin', 'result': 'R', 'mic': '>4'},
            {'antibiotic': 'gentamicin', 'result': 'S', 'mic': '2'},
            {'antibiotic': 'colistin', 'result': 'S', 'mic': '<=0.5'},
        ],
    },
    {
        'mdro_type': MDROTypeChoices.ESBL,
        'organism': 'Escherichia coli',
        'specimen_type': 'Urine',
        'resistant_antibiotics': ['ceftriaxone', 'ceftazidime'],
        'classification_reason': 'ESBL pattern: resistant to ceftriaxone, ceftazidime',
        'susceptibilities': [
            {'antibiotic': 'ceftriaxone', 'result': 'R', 'mic': '>32'},
            {'antibiotic': 'ceftazidime', 'result': 'R', 'mic': '>16'},
            {'antibiotic': 'cefepime', 'result': 'S', 'mic': '4'},
            {'antibiotic': 'meropenem', 'result': 'S', 'mic': '<=0.25'},
            {'antibiotic': 'ciprofloxacin', 'result': 'R', 'mic': '>4'},
            {'antibiotic': 'gentamicin', 'result': 'S', 'mic': '<=1'},
            {'antibiotic': 'nitrofurantoin', 'result': 'S', 'mic': '32'},
        ],
    },
    {
        'mdro_type': MDROTypeChoices.CRPA,
        'organism': 'Pseudomonas aeruginosa',
        'specimen_type': 'Respiratory',
        'resistant_antibiotics': ['meropenem', 'imipenem'],
        'classification_reason': 'Pseudomonas resistant to meropenem, imipenem',
        'susceptibilities': [
            {'antibiotic': 'meropenem', 'result': 'R', 'mic': '>8'},
            {'antibiotic': 'imipenem', 'result': 'R', 'mic': '>8'},
            {'antibiotic': 'cefepime', 'result': 'I', 'mic': '16'},
            {'antibiotic': 'piperacillin-tazobactam', 'result': 'S', 'mic': '32'},
            {'antibiotic': 'tobramycin', 'result': 'S', 'mic': '2'},
            {'antibiotic': 'ciprofloxacin', 'result': 'R', 'mic': '>4'},
            {'antibiotic': 'ceftazidime-avibactam', 'result': 'S', 'mic': '4'},
        ],
    },
    {
        'mdro_type': MDROTypeChoices.CRAB,
        'organism': 'Acinetobacter baumannii',
        'specimen_type': 'Wound',
        'resistant_antibiotics': ['meropenem', 'imipenem'],
        'classification_reason': 'Acinetobacter resistant to meropenem, imipenem',
        'susceptibilities': [
            {'antibiotic': 'meropenem', 'result': 'R', 'mic': '>8'},
            {'antibiotic': 'imipenem', 'result': 'R', 'mic': '>8'},
            {'antibiotic': 'ampicillin-sulbactam', 'result': 'I', 'mic': '16'},
            {'antibiotic': 'minocycline', 'result': 'S', 'mic': '2'},
            {'antibiotic': 'colistin', 'result': 'S', 'mic': '<=0.5'},
            {'antibiotic': 'tigecycline', 'result': 'S', 'mic': '1'},
        ],
    },
]

# Severity mapping for MDRO types → Alert severity
MDRO_SEVERITY_MAP = {
    MDROTypeChoices.CRE: AlertSeverity.HIGH,
    MDROTypeChoices.CRAB: AlertSeverity.HIGH,
    MDROTypeChoices.CRPA: AlertSeverity.HIGH,
    MDROTypeChoices.VRE: AlertSeverity.MEDIUM,
    MDROTypeChoices.MRSA: AlertSeverity.MEDIUM,
    MDROTypeChoices.ESBL: AlertSeverity.MEDIUM,
}


class Command(BaseCommand):
    help = 'Create demo MDRO surveillance data for testing and demonstration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing demo MDRO data before creating new ones',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=10,
            help='Number of MDRO cases to create (default: 10)',
        )

    def handle(self, *args, **options):
        if options['clear']:
            # Delete demo MDRO cases
            mdro_deleted, _ = MDROCase.objects.filter(
                culture_id__startswith='demo-'
            ).delete()
            self.stdout.write(self.style.WARNING(
                f'Deleted {mdro_deleted} existing demo MDRO cases'
            ))

            # Delete demo MDRO alerts
            alert_deleted, _ = Alert.objects.filter(
                source_module='mdro_surveillance',
                source_id__startswith='demo-'
            ).delete()
            self.stdout.write(self.style.WARNING(
                f'Deleted {alert_deleted} existing demo MDRO alerts'
            ))

            # Delete demo processing logs
            log_deleted, _ = MDROProcessingLog.objects.filter(
                culture_id__startswith='demo-'
            ).delete()
            self.stdout.write(self.style.WARNING(
                f'Deleted {log_deleted} existing demo processing logs'
            ))

        now = timezone.now()
        count = options['count']
        created_count = 0

        for i in range(count):
            scenario = random.choice(DEMO_SCENARIOS)
            patient = random.choice(DEMO_PATIENTS)
            unit = random.choice(DEMO_UNITS)

            # Random timing
            culture_time = now - timedelta(
                days=random.randint(0, 25),
                hours=random.randint(0, 23),
            )
            days_since_admission = random.randint(0, 14)
            admission_date = culture_time - timedelta(days=days_since_admission)

            # Determine transmission status based on days
            if days_since_admission > 2:
                transmission = TransmissionStatusChoices.HEALTHCARE
            else:
                transmission = TransmissionStatusChoices.COMMUNITY

            culture_id = f"demo-{uuid.uuid4().hex[:12]}"

            case = MDROCase.objects.create(
                patient_id=patient['id'],
                patient_mrn=patient['mrn'],
                patient_name=patient['name'],
                culture_id=culture_id,
                culture_date=culture_time,
                specimen_type=scenario['specimen_type'],
                organism=scenario['organism'],
                mdro_type=scenario['mdro_type'],
                resistant_antibiotics=scenario['resistant_antibiotics'],
                susceptibilities=scenario['susceptibilities'],
                classification_reason=scenario['classification_reason'],
                location='Cincinnati Children\'s Hospital',
                unit=unit,
                admission_date=admission_date,
                days_since_admission=days_since_admission,
                transmission_status=transmission,
                is_new=random.choice([True, True, True, False]),
                prior_history=random.choice([False, False, False, True]),
            )

            # Create processing log
            MDROProcessingLog.objects.create(
                culture_id=culture_id,
                is_mdro=True,
                mdro_type=scenario['mdro_type'],
                case=case,
            )

            # Create corresponding Alert record
            severity = MDRO_SEVERITY_MAP.get(
                scenario['mdro_type'], AlertSeverity.MEDIUM
            )

            alert = Alert.objects.create(
                alert_type=AlertType.MDRO_DETECTION,
                source_module='mdro_surveillance',
                source_id=f'demo-{case.id}',
                title=f"{scenario['mdro_type'].upper()} Detection - {scenario['organism']}",
                summary=f"{scenario['organism']} identified as {scenario['mdro_type'].upper()} in {scenario['specimen_type'].lower()} culture from {unit}.",
                details={
                    'organism': scenario['organism'],
                    'mdro_type': scenario['mdro_type'],
                    'susceptibilities': scenario['susceptibilities'],
                    'classification_reason': scenario['classification_reason'],
                    'resistant_antibiotics': scenario['resistant_antibiotics'],
                    'specimen_type': scenario['specimen_type'],
                    'unit': unit,
                    'transmission_status': transmission,
                    'days_since_admission': days_since_admission,
                },
                patient_id=patient['id'],
                patient_mrn=patient['mrn'],
                patient_name=patient['name'],
                patient_location=unit,
                severity=severity,
                priority_score=75 if severity == AlertSeverity.HIGH else 50,
                status=AlertStatus.PENDING,
            )

            AlertAudit.objects.create(
                alert=alert,
                action='created',
                old_status=None,
                new_status=AlertStatus.PENDING,
                details={'source': 'demo_mdro_generator'},
            )

            created_count += 1
            self.stdout.write(
                f'  Created: {scenario["mdro_type"].upper()} - {scenario["organism"]} '
                f'({patient["mrn"]}, {unit}, {transmission})'
            )

        self.stdout.write(self.style.SUCCESS(
            f'\nSuccessfully created {created_count} demo MDRO cases with corresponding alerts'
        ))
