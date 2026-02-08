"""
Management command to create demo ASP alert data.

Usage:
    python manage.py create_demo_alerts          # Create 8 demo alerts
    python manage.py create_demo_alerts --clear   # Clear existing demo alerts first
    python manage.py create_demo_alerts --count 20  # Create 20 randomized alerts
"""

import random
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.alerts.models import (
    Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity, ResolutionReason,
)


DEMO_PATIENTS = [
    {'name': 'Johnson, Michael', 'mrn': 'MRN-100234', 'location': 'MICU Bed 4', 'id': 'P-100234'},
    {'name': 'Williams, Sarah', 'mrn': 'MRN-100567', 'location': 'SICU Bed 12', 'id': 'P-100567'},
    {'name': 'Davis, Robert', 'mrn': 'MRN-100891', 'location': '7 North Bed 3', 'id': 'P-100891'},
    {'name': 'Martinez, Elena', 'mrn': 'MRN-101123', 'location': 'MICU Bed 7', 'id': 'P-101123'},
    {'name': 'Brown, James', 'mrn': 'MRN-101456', 'location': 'Oncology 5A Bed 2', 'id': 'P-101456'},
    {'name': 'Thompson, Linda', 'mrn': 'MRN-101789', 'location': 'SICU Bed 8', 'id': 'P-101789'},
    {'name': 'Garcia, Carlos', 'mrn': 'MRN-102012', 'location': '6 South Bed 11', 'id': 'P-102012'},
    {'name': 'Anderson, Patricia', 'mrn': 'MRN-102345', 'location': 'MICU Bed 1', 'id': 'P-102345'},
]

DEMO_SCENARIOS = [
    {
        'alert_type': AlertType.BACTEREMIA,
        'severity': AlertSeverity.CRITICAL,
        'title': 'MRSA Bacteremia - No Vancomycin',
        'summary': 'Blood culture positive for MRSA. Patient not on vancomycin or alternative anti-MRSA agent.',
        'patient_idx': 0,
        'details': {
            'organism': 'Staphylococcus aureus (MRSA)',
            'gram_stain': 'Gram positive cocci in clusters',
            'culture_date': None,  # filled dynamically
            'culture_source': 'Peripheral blood',
            'current_antibiotics': ['Cefazolin 2g IV q8h'],
            'coverage_status': 'inadequate',
            'mismatch_type': 'No MRSA coverage',
            'susceptibilities': [
                {'antibiotic': 'Vancomycin', 'result': 'S', 'mic': '1.0'},
                {'antibiotic': 'Daptomycin', 'result': 'S', 'mic': '0.5'},
                {'antibiotic': 'Linezolid', 'result': 'S', 'mic': '2.0'},
                {'antibiotic': 'Oxacillin', 'result': 'R', 'mic': '>2'},
                {'antibiotic': 'Cefazolin', 'result': 'R', 'mic': '>8'},
                {'antibiotic': 'TMP-SMX', 'result': 'S', 'mic': '<=0.5'},
            ],
            'recommendations': [
                'Add vancomycin (target trough 15-20 mcg/mL) or daptomycin 6-8 mg/kg IV daily',
                'Discontinue cefazolin - inadequate for MRSA',
                'Obtain ID consult for source control evaluation',
                'Repeat blood cultures in 48-72 hours',
            ],
        },
    },
    {
        'alert_type': AlertType.BACTEREMIA,
        'severity': AlertSeverity.CRITICAL,
        'title': 'Pseudomonas Bacteremia - Inadequate Coverage',
        'summary': 'Blood culture positive for Pseudomonas aeruginosa. Current antibiotic (cefazolin) lacks anti-pseudomonal activity.',
        'patient_idx': 1,
        'details': {
            'organism': 'Pseudomonas aeruginosa',
            'gram_stain': 'Gram negative rods',
            'culture_date': None,
            'culture_source': 'Central line blood',
            'current_antibiotics': ['Cefazolin 2g IV q8h'],
            'coverage_status': 'inadequate',
            'mismatch_type': 'No anti-pseudomonal coverage',
            'susceptibilities': [
                {'antibiotic': 'Cefepime', 'result': 'S', 'mic': '4.0'},
                {'antibiotic': 'Piperacillin-Tazobactam', 'result': 'S', 'mic': '16'},
                {'antibiotic': 'Meropenem', 'result': 'S', 'mic': '1.0'},
                {'antibiotic': 'Ciprofloxacin', 'result': 'R', 'mic': '>4'},
                {'antibiotic': 'Cefazolin', 'result': 'R', 'mic': '>32'},
                {'antibiotic': 'Tobramycin', 'result': 'S', 'mic': '2.0'},
            ],
            'recommendations': [
                'Switch to cefepime 2g IV q8h or piperacillin-tazobactam 4.5g IV q6h',
                'Consider combination therapy with tobramycin for synergy',
                'Evaluate for catheter-related source - consider line removal',
                'Repeat blood cultures daily until clearance',
            ],
        },
    },
    {
        'alert_type': AlertType.DRUG_BUG_MISMATCH,
        'severity': AlertSeverity.HIGH,
        'title': 'E. coli Drug-Bug Mismatch - Resistant to Ampicillin',
        'summary': 'Urine culture E. coli resistant to current ampicillin therapy. Susceptibility-guided change needed.',
        'patient_idx': 2,
        'details': {
            'organism': 'Escherichia coli',
            'gram_stain': 'Gram negative rods',
            'culture_date': None,
            'culture_source': 'Urine',
            'current_antibiotics': ['Ampicillin 2g IV q6h'],
            'coverage_status': 'inadequate',
            'mismatch_type': 'Organism resistant to current therapy',
            'susceptibilities': [
                {'antibiotic': 'Ampicillin', 'result': 'R', 'mic': '>32'},
                {'antibiotic': 'Ceftriaxone', 'result': 'S', 'mic': '<=1'},
                {'antibiotic': 'Ciprofloxacin', 'result': 'S', 'mic': '<=0.25'},
                {'antibiotic': 'TMP-SMX', 'result': 'R', 'mic': '>4'},
                {'antibiotic': 'Gentamicin', 'result': 'S', 'mic': '<=1'},
                {'antibiotic': 'Nitrofurantoin', 'result': 'S', 'mic': '32'},
            ],
            'recommendations': [
                'Switch to ceftriaxone 2g IV daily based on susceptibilities',
                'Consider oral step-down to ciprofloxacin if clinically improving',
            ],
        },
    },
    {
        'alert_type': AlertType.BACTEREMIA,
        'severity': AlertSeverity.CRITICAL,
        'title': 'VRE Bacteremia - On Vancomycin (Ineffective)',
        'summary': 'Blood culture positive for VRE. Current vancomycin therapy is ineffective against vancomycin-resistant Enterococcus.',
        'patient_idx': 3,
        'details': {
            'organism': 'Enterococcus faecium (VRE)',
            'gram_stain': 'Gram positive cocci in chains',
            'culture_date': None,
            'culture_source': 'Peripheral blood',
            'current_antibiotics': ['Vancomycin 1.5g IV q12h'],
            'coverage_status': 'inadequate',
            'mismatch_type': 'Organism resistant to current therapy',
            'susceptibilities': [
                {'antibiotic': 'Vancomycin', 'result': 'R', 'mic': '>256'},
                {'antibiotic': 'Daptomycin', 'result': 'S', 'mic': '2.0'},
                {'antibiotic': 'Linezolid', 'result': 'S', 'mic': '1.0'},
                {'antibiotic': 'Ampicillin', 'result': 'R', 'mic': '>32'},
            ],
            'recommendations': [
                'Switch to daptomycin 8-10 mg/kg IV daily or linezolid 600mg IV/PO q12h',
                'Discontinue vancomycin - organism is resistant',
                'ID consult for VRE bacteremia management',
            ],
        },
    },
    {
        'alert_type': AlertType.BACTEREMIA,
        'severity': AlertSeverity.CRITICAL,
        'title': 'Candida Fungemia - No Antifungal Therapy',
        'summary': 'Blood culture positive for Candida albicans. Patient not receiving any antifungal therapy.',
        'patient_idx': 4,
        'details': {
            'organism': 'Candida albicans',
            'gram_stain': 'Yeast',
            'culture_date': None,
            'culture_source': 'Central line blood',
            'current_antibiotics': ['Vancomycin 1.5g IV q12h', 'Piperacillin-Tazobactam 4.5g IV q6h'],
            'coverage_status': 'inadequate',
            'mismatch_type': 'No antifungal coverage',
            'susceptibilities': [
                {'antibiotic': 'Fluconazole', 'result': 'S', 'mic': '0.5'},
                {'antibiotic': 'Micafungin', 'result': 'S', 'mic': '<=0.06'},
                {'antibiotic': 'Caspofungin', 'result': 'S', 'mic': '<=0.25'},
                {'antibiotic': 'Amphotericin B', 'result': 'S', 'mic': '0.5'},
            ],
            'recommendations': [
                'Start micafungin 100mg IV daily (preferred initial therapy)',
                'Ophthalmology consult for endophthalmitis screening',
                'Remove all central venous catheters if possible',
                'Repeat blood cultures daily until clearance, then 14 days of therapy post-clearance',
            ],
        },
    },
    {
        'alert_type': AlertType.BROAD_SPECTRUM_USAGE,
        'severity': AlertSeverity.MEDIUM,
        'title': 'Broad Spectrum Alert - Meropenem >72 Hours',
        'summary': 'Meropenem has been administered for >72 hours. Review for de-escalation opportunity.',
        'patient_idx': 5,
        'details': {
            'medication': 'Meropenem 1g IV q8h',
            'duration_days': 5,
            'threshold_days': 3,
            'current_antibiotics': ['Meropenem 1g IV q8h', 'Vancomycin 1.5g IV q12h'],
            'recommendations': [
                'Review culture data for de-escalation opportunity',
                'If cultures negative at 48-72h, consider narrowing spectrum',
                'Assess clinical response and consider oral step-down',
            ],
        },
    },
    {
        'alert_type': AlertType.GUIDELINE_ADHERENCE,
        'severity': AlertSeverity.HIGH,
        'title': 'Sepsis Bundle Incomplete - Missing Elements',
        'summary': 'Sepsis 3-hour bundle not completed within time window. Missing lactate recheck and antibiotic administration within 1 hour.',
        'patient_idx': 6,
        'details': {
            'bundle_name': 'Sepsis 3-Hour Bundle (SEP-1)',
            'missed_elements': [
                'Lactate recheck within 6 hours (not ordered)',
                'Antibiotics within 1 hour of recognition (administered at 2h 15min)',
                'Blood cultures before antibiotics (obtained, but delayed)',
            ],
            'current_antibiotics': ['Vancomycin 1.5g IV', 'Cefepime 2g IV'],
            'recommendations': [
                'Order stat lactate level for 6-hour recheck',
                'Document time of sepsis recognition in chart',
                'Ensure 30 mL/kg crystalloid bolus completed if hypotensive',
            ],
        },
    },
    {
        # This one is pre-resolved for history page
        'alert_type': AlertType.BACTEREMIA,
        'severity': AlertSeverity.CRITICAL,
        'title': 'MRSA Bacteremia - Resolved (Vancomycin Added)',
        'summary': 'Previously identified MRSA bacteremia. Vancomycin was added and therapy is now adequate.',
        'patient_idx': 7,
        'resolved': True,
        'details': {
            'organism': 'Staphylococcus aureus (MRSA)',
            'gram_stain': 'Gram positive cocci in clusters',
            'culture_date': None,
            'culture_source': 'Peripheral blood',
            'current_antibiotics': ['Vancomycin 1.5g IV q12h'],
            'coverage_status': 'adequate',
            'susceptibilities': [
                {'antibiotic': 'Vancomycin', 'result': 'S', 'mic': '1.0'},
                {'antibiotic': 'Daptomycin', 'result': 'S', 'mic': '0.5'},
                {'antibiotic': 'Oxacillin', 'result': 'R', 'mic': '>2'},
            ],
            'recommendations': [
                'Continue vancomycin - adequate coverage confirmed',
                'Monitor trough levels',
            ],
        },
    },
]

# Additional organism/scenario data for randomized alerts
RANDOM_ORGANISMS = [
    ('Klebsiella pneumoniae', 'Gram negative rods', AlertType.DRUG_BUG_MISMATCH),
    ('Enterobacter cloacae', 'Gram negative rods', AlertType.DRUG_BUG_MISMATCH),
    ('Staphylococcus aureus (MRSA)', 'Gram positive cocci in clusters', AlertType.BACTEREMIA),
    ('Streptococcus pneumoniae', 'Gram positive cocci in chains', AlertType.BACTEREMIA),
    ('Candida glabrata', 'Yeast', AlertType.BACTEREMIA),
    ('Serratia marcescens', 'Gram negative rods', AlertType.CULTURE_NO_THERAPY),
]


class Command(BaseCommand):
    help = 'Create demo ASP alert data for testing and demonstration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing demo alerts before creating new ones',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=0,
            help='Create N additional randomized alerts (in addition to the 8 standard scenarios)',
        )

    def handle(self, *args, **options):
        if options['clear']:
            deleted_count, _ = Alert.objects.filter(source_module='demo').delete()
            self.stdout.write(self.style.WARNING(f'Deleted {deleted_count} existing demo alerts'))

        now = timezone.now()
        created_count = 0

        # Create the 8 standard demo scenarios
        for i, scenario in enumerate(DEMO_SCENARIOS):
            patient = DEMO_PATIENTS[scenario['patient_idx']]
            details = scenario['details'].copy()

            # Set dynamic culture date
            if 'culture_date' in details and details['culture_date'] is None:
                culture_time = now - timedelta(hours=random.randint(6, 48))
                details['culture_date'] = culture_time.strftime('%Y-%m-%d %H:%M')

            is_resolved = scenario.get('resolved', False)
            created_time = now - timedelta(hours=random.randint(2, 72))

            alert = Alert.objects.create(
                alert_type=scenario['alert_type'],
                source_module='demo',
                source_id=f'demo-{uuid.uuid4().hex[:8]}',
                title=scenario['title'],
                summary=scenario['summary'],
                details=details,
                patient_id=patient['id'],
                patient_mrn=patient['mrn'],
                patient_name=patient['name'],
                patient_location=patient['location'],
                severity=scenario['severity'],
                priority_score=self._severity_to_score(scenario['severity']),
                status=AlertStatus.RESOLVED if is_resolved else AlertStatus.PENDING,
                created_at=created_time,
                resolved_at=(now - timedelta(hours=random.randint(1, 24))) if is_resolved else None,
                resolution_reason=ResolutionReason.THERAPY_CHANGED if is_resolved else None,
                resolution_notes='Vancomycin added per ASP recommendation' if is_resolved else None,
            )

            # Create initial audit entry
            AlertAudit.objects.create(
                alert=alert,
                action='created',
                old_status=None,
                new_status=AlertStatus.PENDING,
                details={'source': 'demo_data_generator'},
            )

            if is_resolved:
                AlertAudit.objects.create(
                    alert=alert,
                    action='resolved',
                    old_status=AlertStatus.ACKNOWLEDGED,
                    new_status=AlertStatus.RESOLVED,
                    details={'reason': 'therapy_changed', 'notes': 'Vancomycin added per ASP recommendation'},
                )

            created_count += 1
            self.stdout.write(f'  Created: {scenario["title"]}')

        # Create additional randomized alerts if requested
        extra_count = options['count']
        if extra_count > 0:
            for i in range(extra_count):
                alert = self._create_random_alert(now)
                created_count += 1

            self.stdout.write(f'  Created {extra_count} additional randomized alerts')

        self.stdout.write(self.style.SUCCESS(
            f'\nSuccessfully created {created_count} demo alerts'
        ))

    def _severity_to_score(self, severity):
        return {
            AlertSeverity.CRITICAL: 95,
            AlertSeverity.HIGH: 75,
            AlertSeverity.MEDIUM: 50,
            AlertSeverity.LOW: 25,
            AlertSeverity.INFO: 10,
        }.get(severity, 50)

    def _create_random_alert(self, now):
        patient = random.choice(DEMO_PATIENTS)
        organism, gram_stain, alert_type = random.choice(RANDOM_ORGANISMS)
        severity = random.choice([AlertSeverity.CRITICAL, AlertSeverity.HIGH, AlertSeverity.MEDIUM])
        status = random.choice([AlertStatus.PENDING, AlertStatus.ACKNOWLEDGED, AlertStatus.SNOOZED])

        abx_options = [
            'Vancomycin 1.5g IV q12h', 'Cefazolin 2g IV q8h', 'Ceftriaxone 2g IV daily',
            'Piperacillin-Tazobactam 4.5g IV q6h', 'Meropenem 1g IV q8h',
            'Ampicillin 2g IV q6h', 'Cefepime 2g IV q8h',
        ]

        details = {
            'organism': organism,
            'gram_stain': gram_stain,
            'culture_date': (now - timedelta(hours=random.randint(6, 72))).strftime('%Y-%m-%d %H:%M'),
            'culture_source': random.choice(['Peripheral blood', 'Central line blood', 'Urine', 'Wound']),
            'current_antibiotics': random.sample(abx_options, random.randint(1, 3)),
            'coverage_status': random.choice(['adequate', 'inadequate']),
            'recommendations': [
                'Review current antimicrobial therapy',
                'Consider ID consultation',
            ],
        }

        created_time = now - timedelta(hours=random.randint(1, 96))

        alert = Alert.objects.create(
            alert_type=alert_type,
            source_module='demo',
            source_id=f'demo-rand-{uuid.uuid4().hex[:8]}',
            title=f'{organism} - {alert_type.label}',
            summary=f'Alert for {organism} identified in {details["culture_source"].lower()}.',
            details=details,
            patient_id=patient['id'],
            patient_mrn=patient['mrn'],
            patient_name=patient['name'],
            patient_location=patient['location'],
            severity=severity,
            priority_score=self._severity_to_score(severity),
            status=status,
            created_at=created_time,
        )

        AlertAudit.objects.create(
            alert=alert,
            action='created',
            old_status=None,
            new_status=AlertStatus.PENDING,
            details={'source': 'demo_data_generator_random'},
        )

        return alert
