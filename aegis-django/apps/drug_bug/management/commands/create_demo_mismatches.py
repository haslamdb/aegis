"""
Management command to create demo drug-bug mismatch data.

Usage:
    python manage.py create_demo_mismatches              # Create 8 demo alerts
    python manage.py create_demo_mismatches --clear       # Clear existing demo data first
    python manage.py create_demo_mismatches --count 20    # Create 20 alerts
"""

import random
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity


DEMO_PATIENTS = [
    {'name': 'Johnson, Michael', 'mrn': 'MRN-100234', 'id': 'P-100234'},
    {'name': 'Williams, Sarah', 'mrn': 'MRN-100567', 'id': 'P-100567'},
    {'name': 'Davis, Robert', 'mrn': 'MRN-100891', 'id': 'P-100891'},
    {'name': 'Martinez, Elena', 'mrn': 'MRN-101123', 'id': 'P-101123'},
    {'name': 'Brown, James', 'mrn': 'MRN-101456', 'id': 'P-101456'},
    {'name': 'Thompson, Linda', 'mrn': 'MRN-101789', 'id': 'P-101789'},
    {'name': 'Garcia, Carlos', 'mrn': 'MRN-102012', 'id': 'P-102012'},
    {'name': 'Anderson, Patricia', 'mrn': 'MRN-102345', 'id': 'P-102345'},
]

DEMO_UNITS = [
    'MICU', 'SICU', 'NICU', '7 North', '6 South',
    'Oncology 5A', 'Step-Down', 'Med-Surg 4B',
]

DEMO_SCENARIOS = [
    {
        'organism': 'Staphylococcus aureus (MRSA)',
        'specimen_type': 'Blood',
        'mismatch_type': 'resistant',
        'severity': AlertSeverity.HIGH,
        'current_antibiotics': [
            {'name': 'Ceftriaxone', 'rxnorm': '2193', 'mismatch_type': 'resistant', 'susceptibility': 'R'},
        ],
        'susceptible_options': ['vancomycin', 'daptomycin', 'linezolid', 'tmp-smx'],
        'susceptibility_panel': [
            {'antibiotic': 'ceftriaxone', 'result': 'R'},
            {'antibiotic': 'oxacillin', 'result': 'R', 'mic': '>2'},
            {'antibiotic': 'vancomycin', 'result': 'S', 'mic': '1.0'},
            {'antibiotic': 'daptomycin', 'result': 'S', 'mic': '0.5'},
            {'antibiotic': 'linezolid', 'result': 'S', 'mic': '2.0'},
            {'antibiotic': 'tmp-smx', 'result': 'S', 'mic': '<=0.5'},
        ],
        'recommendation': 'Organism resistant to Ceftriaxone. Consider: vancomycin, daptomycin, linezolid, tmp-smx.',
    },
    {
        'organism': 'Escherichia coli',
        'specimen_type': 'Urine',
        'mismatch_type': 'resistant',
        'severity': AlertSeverity.HIGH,
        'current_antibiotics': [
            {'name': 'Ciprofloxacin', 'rxnorm': '2551', 'mismatch_type': 'resistant', 'susceptibility': 'R'},
        ],
        'susceptible_options': ['meropenem', 'gentamicin', 'nitrofurantoin', 'cefepime'],
        'susceptibility_panel': [
            {'antibiotic': 'ciprofloxacin', 'result': 'R', 'mic': '>4'},
            {'antibiotic': 'ceftriaxone', 'result': 'R', 'mic': '>32'},
            {'antibiotic': 'meropenem', 'result': 'S', 'mic': '<=0.25'},
            {'antibiotic': 'gentamicin', 'result': 'S', 'mic': '<=1'},
            {'antibiotic': 'nitrofurantoin', 'result': 'S', 'mic': '32'},
            {'antibiotic': 'cefepime', 'result': 'S', 'mic': '4'},
        ],
        'recommendation': 'Organism resistant to Ciprofloxacin. Consider: meropenem, gentamicin, nitrofurantoin, cefepime.',
    },
    {
        'organism': 'Pseudomonas aeruginosa',
        'specimen_type': 'Respiratory',
        'mismatch_type': 'intermediate',
        'severity': AlertSeverity.MEDIUM,
        'current_antibiotics': [
            {'name': 'Meropenem', 'rxnorm': '29561', 'mismatch_type': 'intermediate', 'susceptibility': 'I'},
        ],
        'susceptible_options': ['piperacillin-tazobactam', 'tobramycin', 'ceftazidime'],
        'susceptibility_panel': [
            {'antibiotic': 'meropenem', 'result': 'I', 'mic': '4'},
            {'antibiotic': 'imipenem', 'result': 'R', 'mic': '>8'},
            {'antibiotic': 'cefepime', 'result': 'I', 'mic': '16'},
            {'antibiotic': 'piperacillin-tazobactam', 'result': 'S', 'mic': '32'},
            {'antibiotic': 'tobramycin', 'result': 'S', 'mic': '2'},
            {'antibiotic': 'ciprofloxacin', 'result': 'R', 'mic': '>4'},
            {'antibiotic': 'ceftazidime', 'result': 'S', 'mic': '8'},
        ],
        'recommendation': 'Intermediate susceptibility to Meropenem. Consider dose optimization or switch to: piperacillin-tazobactam, tobramycin, ceftazidime.',
    },
    {
        'organism': 'Klebsiella pneumoniae',
        'specimen_type': 'Wound',
        'mismatch_type': 'no_coverage',
        'severity': AlertSeverity.MEDIUM,
        'current_antibiotics': [
            {'name': 'No active antibiotics', 'rxnorm': None, 'mismatch_type': 'no_coverage'},
        ],
        'susceptible_options': ['meropenem', 'cefepime', 'gentamicin', 'ciprofloxacin'],
        'susceptibility_panel': [
            {'antibiotic': 'ampicillin', 'result': 'R'},
            {'antibiotic': 'ceftriaxone', 'result': 'S', 'mic': '<=1'},
            {'antibiotic': 'meropenem', 'result': 'S', 'mic': '<=0.25'},
            {'antibiotic': 'cefepime', 'result': 'S', 'mic': '<=1'},
            {'antibiotic': 'gentamicin', 'result': 'S', 'mic': '<=1'},
            {'antibiotic': 'ciprofloxacin', 'result': 'S', 'mic': '<=0.25'},
        ],
        'recommendation': 'Patient not on active antibiotics. Susceptible options: meropenem, cefepime, gentamicin, ciprofloxacin.',
    },
    {
        'organism': 'Enterococcus faecium (VRE)',
        'specimen_type': 'Blood',
        'mismatch_type': 'resistant',
        'severity': AlertSeverity.HIGH,
        'current_antibiotics': [
            {'name': 'Vancomycin', 'rxnorm': '11124', 'mismatch_type': 'resistant', 'susceptibility': 'R'},
        ],
        'susceptible_options': ['daptomycin', 'linezolid'],
        'susceptibility_panel': [
            {'antibiotic': 'vancomycin', 'result': 'R', 'mic': '>256'},
            {'antibiotic': 'ampicillin', 'result': 'R', 'mic': '>32'},
            {'antibiotic': 'daptomycin', 'result': 'S', 'mic': '2.0'},
            {'antibiotic': 'linezolid', 'result': 'S', 'mic': '1.0'},
        ],
        'recommendation': 'Organism resistant to Vancomycin. Consider: daptomycin, linezolid.',
    },
    {
        'organism': 'Staphylococcus aureus (MSSA)',
        'specimen_type': 'Wound',
        'mismatch_type': 'resistant',
        'severity': AlertSeverity.HIGH,
        'current_antibiotics': [
            {'name': 'Clindamycin', 'rxnorm': '2582', 'mismatch_type': 'resistant', 'susceptibility': 'R'},
        ],
        'susceptible_options': ['cefazolin', 'nafcillin', 'oxacillin', 'vancomycin'],
        'susceptibility_panel': [
            {'antibiotic': 'clindamycin', 'result': 'R'},
            {'antibiotic': 'erythromycin', 'result': 'R'},
            {'antibiotic': 'oxacillin', 'result': 'S', 'mic': '<=0.25'},
            {'antibiotic': 'cefazolin', 'result': 'S', 'mic': '<=2'},
            {'antibiotic': 'vancomycin', 'result': 'S', 'mic': '1'},
            {'antibiotic': 'tmp-smx', 'result': 'S', 'mic': '<=0.5'},
        ],
        'recommendation': 'Organism resistant to Clindamycin. Consider: cefazolin, nafcillin, oxacillin, vancomycin.',
    },
    {
        'organism': 'Escherichia coli (ESBL)',
        'specimen_type': 'Blood',
        'mismatch_type': 'resistant',
        'severity': AlertSeverity.HIGH,
        'current_antibiotics': [
            {'name': 'Ceftriaxone', 'rxnorm': '2193', 'mismatch_type': 'resistant', 'susceptibility': 'R'},
        ],
        'susceptible_options': ['meropenem', 'ertapenem'],
        'susceptibility_panel': [
            {'antibiotic': 'ceftriaxone', 'result': 'R', 'mic': '>32'},
            {'antibiotic': 'ceftazidime', 'result': 'R', 'mic': '>16'},
            {'antibiotic': 'ciprofloxacin', 'result': 'R', 'mic': '>4'},
            {'antibiotic': 'meropenem', 'result': 'S', 'mic': '<=0.25'},
            {'antibiotic': 'ertapenem', 'result': 'S', 'mic': '<=0.5'},
            {'antibiotic': 'gentamicin', 'result': 'I', 'mic': '8'},
        ],
        'recommendation': 'Organism resistant to Ceftriaxone. Consider: meropenem, ertapenem.',
    },
    {
        'organism': 'Candida albicans',
        'specimen_type': 'Blood',
        'mismatch_type': 'no_coverage',
        'severity': AlertSeverity.MEDIUM,
        'current_antibiotics': [
            {'name': 'Vancomycin', 'rxnorm': '11124', 'mismatch_type': None, 'susceptibility': None},
            {'name': 'Meropenem', 'rxnorm': '29561', 'mismatch_type': None, 'susceptibility': None},
        ],
        'susceptible_options': ['fluconazole', 'micafungin', 'caspofungin'],
        'susceptibility_panel': [
            {'antibiotic': 'fluconazole', 'result': 'S', 'mic': '<=1'},
            {'antibiotic': 'micafungin', 'result': 'S', 'mic': '<=0.06'},
            {'antibiotic': 'caspofungin', 'result': 'S', 'mic': '<=0.25'},
            {'antibiotic': 'amphotericin B', 'result': 'S', 'mic': '0.5'},
        ],
        'recommendation': 'Patient not on active antifungals. Susceptible options: fluconazole, micafungin, caspofungin.',
    },
]


class Command(BaseCommand):
    help = 'Create demo drug-bug mismatch alerts for testing and demonstration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing demo drug-bug mismatch data before creating new ones',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=8,
            help='Number of mismatch alerts to create (default: 8)',
        )

    def handle(self, *args, **options):
        if options['clear']:
            deleted, _ = Alert.objects.filter(
                source_module='drug_bug_mismatch',
                source_id__startswith='demo-'
            ).delete()
            self.stdout.write(self.style.WARNING(
                f'Deleted {deleted} existing demo drug-bug mismatch alerts'
            ))

        now = timezone.now()
        count = options['count']
        created_count = 0

        for i in range(count):
            scenario = DEMO_SCENARIOS[i % len(DEMO_SCENARIOS)]
            patient = random.choice(DEMO_PATIENTS)
            unit = random.choice(DEMO_UNITS)

            # Random timing
            created_time = now - timedelta(
                hours=random.randint(0, 72),
                minutes=random.randint(0, 59),
            )

            culture_id = f"demo-{uuid.uuid4().hex[:12]}"
            collection_date = created_time - timedelta(hours=random.randint(12, 48))

            # Build mismatch type display
            mismatch_display = scenario['mismatch_type'].replace('_', ' ').title()
            title = f"Drug-Bug Mismatch: {scenario['organism']} ({mismatch_display})"

            # Build summary
            resistant_abx = [
                abx['name'] for abx in scenario['current_antibiotics']
                if abx.get('mismatch_type') == 'resistant'
            ]
            if resistant_abx:
                summary = f"Resistant to {', '.join(resistant_abx)}"
            else:
                summary = scenario['recommendation'][:100]

            # Determine if this should be resolved (for history variety)
            is_resolved = i >= count - 2 and count > 4  # Last 2 get resolved if enough total

            alert = Alert.objects.create(
                alert_type=AlertType.DRUG_BUG_MISMATCH,
                source_module='drug_bug_mismatch',
                source_id=f'demo-{culture_id}',
                title=title,
                summary=summary,
                details={
                    'culture_id': culture_id,
                    'organism': scenario['organism'],
                    'specimen_type': scenario['specimen_type'],
                    'collection_date': collection_date.isoformat(),
                    'mismatch_type': scenario['mismatch_type'],
                    'current_antibiotics': scenario['current_antibiotics'],
                    'susceptible_options': scenario['susceptible_options'],
                    'recommendation': scenario['recommendation'],
                    'susceptibility_panel': scenario['susceptibility_panel'],
                },
                patient_id=patient['id'],
                patient_mrn=patient['mrn'],
                patient_name=patient['name'],
                patient_location=unit,
                severity=scenario['severity'],
                priority_score=75 if scenario['severity'] == AlertSeverity.HIGH else 50,
                status=AlertStatus.RESOLVED if is_resolved else AlertStatus.PENDING,
            )

            # Backdate created_at
            Alert.objects.filter(id=alert.id).update(created_at=created_time)

            if is_resolved:
                resolved_time = created_time + timedelta(hours=random.randint(1, 8))
                Alert.objects.filter(id=alert.id).update(
                    resolved_at=resolved_time,
                    resolution_reason='therapy_changed',
                )

            AlertAudit.objects.create(
                alert=alert,
                action='created',
                old_status=None,
                new_status=AlertStatus.PENDING,
                details={'source': 'demo_drug_bug_generator'},
            )

            created_count += 1
            status_str = 'RESOLVED' if is_resolved else 'ACTIVE'
            self.stdout.write(
                f'  Created [{status_str}]: {scenario["mismatch_type"].upper()} - '
                f'{scenario["organism"]} ({patient["mrn"]}, {unit})'
            )

        self.stdout.write(self.style.SUCCESS(
            f'\nSuccessfully created {created_count} demo drug-bug mismatch alerts'
        ))
