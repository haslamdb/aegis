"""
Management command to create demo dosing verification alerts.

Usage:
    python manage.py create_demo_dosing              # Create 10 demo alerts
    python manage.py create_demo_dosing --clear       # Clear existing demo data first
    python manage.py create_demo_dosing --count 20    # Create 20 alerts
"""

import random
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity


DEMO_PATIENTS = [
    {'name': 'Chen, Wei', 'mrn': 'MRN-200100', 'id': 'P-200100'},
    {'name': 'Okafor, Adaeze', 'mrn': 'MRN-200201', 'id': 'P-200201'},
    {'name': 'Petrov, Yuri', 'mrn': 'MRN-200302', 'id': 'P-200302'},
    {'name': 'Rodriguez, Maria', 'mrn': 'MRN-200403', 'id': 'P-200403'},
    {'name': 'Nguyen, Thanh', 'mrn': 'MRN-200504', 'id': 'P-200504'},
    {'name': 'Smith, Jamal', 'mrn': 'MRN-200605', 'id': 'P-200605'},
    {'name': 'Johansson, Erik', 'mrn': 'MRN-200706', 'id': 'P-200706'},
    {'name': 'Patel, Priya', 'mrn': 'MRN-200807', 'id': 'P-200807'},
    {'name': 'Kim, Soo-Jin', 'mrn': 'MRN-200908', 'id': 'P-200908'},
    {'name': 'Weber, Hans', 'mrn': 'MRN-201009', 'id': 'P-201009'},
]

DEMO_UNITS = [
    'MICU', 'SICU', 'NICU', '7 North', '6 South',
    'Oncology 5A', 'Step-Down', 'Med-Surg 4B', 'CCU', 'PICU',
]

DEMO_SCENARIOS = [
    # 1. Renal adjustment needed (CRITICAL)
    {
        'alert_type': AlertType.DOSING_RENAL,
        'severity': AlertSeverity.CRITICAL,
        'drug': 'Vancomycin',
        'flag_type': 'no_renal_adjustment',
        'title': 'Dosing: Renal adjustment needed for Vancomycin',
        'summary': 'Vancomycin dose not adjusted for GFR 25 mL/min. Standard dose 1g q12h exceeds recommended renal dose.',
        'expected_dose': '750 mg q24h (GFR 15-29: reduce dose 50%, extend interval)',
        'actual_dose': '1000 mg q12h (standard dose)',
        'rule_source': 'IDSA/ASHP Vancomycin Guidelines 2020',
        'indication': 'MRSA bacteremia',
        'patient_factors': {
            'age_years': 72, 'weight_kg': 68, 'height_cm': 170,
            'scr': 2.8, 'gfr': 25, 'is_on_dialysis': False,
        },
    },
    # 2. Age contraindication (CRITICAL)
    {
        'alert_type': AlertType.DOSING_AGE,
        'severity': AlertSeverity.CRITICAL,
        'drug': 'Ceftriaxone',
        'flag_type': 'age_dose_mismatch',
        'title': 'Dosing: Ceftriaxone contraindicated in neonate',
        'summary': 'Ceftriaxone contraindicated in neonates <28 days due to bilirubin displacement risk (kernicterus).',
        'expected_dose': 'Use cefotaxime 50 mg/kg q8h for neonatal meningitis',
        'actual_dose': 'Ceftriaxone 100 mg/kg/day',
        'rule_source': 'IDSA Neonatal Guidelines',
        'indication': 'Neonatal meningitis',
        'patient_factors': {
            'age_years': 0.02, 'weight_kg': 3.2,
            'gestational_age_weeks': 38,
        },
    },
    # 3. Allergy contraindication (CRITICAL)
    {
        'alert_type': AlertType.DOSING_ALLERGY,
        'severity': AlertSeverity.CRITICAL,
        'drug': 'Amoxicillin',
        'flag_type': 'allergy_contraindicated',
        'title': 'Dosing: Allergy - Penicillin allergy on Amoxicillin',
        'summary': 'Patient has documented penicillin allergy (anaphylaxis). Amoxicillin is a penicillin-class antibiotic.',
        'expected_dose': 'Discontinue amoxicillin. Consider azithromycin or fluoroquinolone.',
        'actual_dose': 'Amoxicillin 500 mg PO q8h',
        'rule_source': 'Drug allergy cross-reactivity database',
        'indication': 'Community-acquired pneumonia',
        'patient_factors': {
            'age_years': 45, 'weight_kg': 82,
        },
        'allergies': [
            {'drug': 'Penicillin', 'severity': 'severe', 'reaction': 'anaphylaxis'},
        ],
    },
    # 4. Drug interaction (HIGH)
    {
        'alert_type': AlertType.DOSING_INTERACTION,
        'severity': AlertSeverity.HIGH,
        'drug': 'Linezolid',
        'flag_type': 'drug_interaction',
        'title': 'Dosing: Drug Interaction - Linezolid + Sertraline',
        'summary': 'Linezolid (MAO inhibitor) + SSRI: Risk of serotonin syndrome (hyperthermia, rigidity, confusion).',
        'expected_dose': 'Avoid combination. If unavoidable, hold SSRI and monitor for serotonin syndrome.',
        'actual_dose': 'Linezolid 600 mg IV q12h + Sertraline 100 mg PO daily',
        'rule_source': 'FDA Safety Alert 2011, IDSA MRSA Guidelines',
        'indication': 'MRSA pneumonia',
        'patient_factors': {
            'age_years': 58, 'weight_kg': 75,
        },
        'co_medications': [
            {'drug_name': 'Sertraline 100 mg PO daily'},
        ],
    },
    # 5. Weight-based overdose (HIGH)
    {
        'alert_type': AlertType.DOSING_WEIGHT,
        'severity': AlertSeverity.HIGH,
        'drug': 'Gentamicin',
        'flag_type': 'weight_dose_mismatch',
        'title': 'Dosing: Weight-based dose exceeds maximum for Gentamicin',
        'summary': 'Gentamicin dose exceeds recommended mg/kg range. Patient weight 120 kg (obese), should use adjusted body weight.',
        'expected_dose': '7 mg/kg ABW q24h = 560 mg (ABW 80 kg, IBW 70 kg)',
        'actual_dose': '840 mg q24h (7 mg/kg actual weight)',
        'rule_source': 'Aminoglycoside dosing guidelines',
        'indication': 'Gram-negative bacteremia',
        'patient_factors': {
            'age_years': 52, 'weight_kg': 120, 'height_cm': 175,
        },
    },
    # 6. Wrong route (HIGH)
    {
        'alert_type': AlertType.DOSING_ROUTE,
        'severity': AlertSeverity.HIGH,
        'drug': 'Vancomycin',
        'flag_type': 'wrong_route',
        'title': 'Dosing: IV Vancomycin for C. difficile infection',
        'summary': 'IV vancomycin does NOT reach the colon. C. difficile requires PO or rectal vancomycin.',
        'expected_dose': 'Vancomycin 125 mg PO q6h (or 500 mg PO q6h for severe CDI)',
        'actual_dose': 'Vancomycin 1000 mg IV q12h',
        'rule_source': 'IDSA/SHEA CDI Guidelines 2021',
        'indication': 'C. difficile infection',
        'patient_factors': {
            'age_years': 68, 'weight_kg': 72,
        },
    },
    # 7. Subtherapeutic dose (HIGH)
    {
        'alert_type': AlertType.DOSING_INDICATION,
        'severity': AlertSeverity.HIGH,
        'drug': 'Meropenem',
        'flag_type': 'subtherapeutic_dose',
        'title': 'Dosing: Subtherapeutic meropenem dose for meningitis',
        'summary': 'Meningitis requires 2g q8h (not standard 1g q8h). BBB penetration requires higher dosing.',
        'expected_dose': 'Meropenem 2000 mg IV q8h (meningitis dose)',
        'actual_dose': 'Meropenem 1000 mg IV q8h (standard dose)',
        'rule_source': 'IDSA Meningitis Guidelines',
        'indication': 'Bacterial meningitis',
        'patient_factors': {
            'age_years': 35, 'weight_kg': 78,
        },
    },
    # 8. Duration excessive (MEDIUM)
    {
        'alert_type': AlertType.DOSING_DURATION,
        'severity': AlertSeverity.MEDIUM,
        'drug': 'Levofloxacin',
        'flag_type': 'duration_excessive',
        'title': 'Dosing: Excessive fluoroquinolone duration',
        'summary': 'Levofloxacin for uncomplicated UTI: 18 days exceeds recommended 5-7 day course.',
        'expected_dose': 'Maximum 7 days for uncomplicated UTI',
        'actual_dose': '18 days on therapy',
        'rule_source': 'IDSA UTI Guidelines 2011',
        'indication': 'Urinary tract infection',
        'patient_factors': {
            'age_years': 42, 'weight_kg': 65,
        },
    },
    # 9. Extended infusion candidate (LOW)
    {
        'alert_type': AlertType.DOSING_EXTENDED_INFUSION,
        'severity': AlertSeverity.LOW,
        'drug': 'Piperacillin-Tazobactam',
        'flag_type': 'extended_infusion',
        'title': 'Dosing: Extended infusion recommended for Piperacillin-Tazobactam',
        'summary': 'Standard 30-min infusion. Extended infusion (4h) improves time > MIC for beta-lactams.',
        'expected_dose': 'Consider extended infusion (4h) or continuous infusion',
        'actual_dose': 'Standard infusion (30 minutes)',
        'rule_source': 'Lancet Infect Dis 2023; Roberts et al.',
        'indication': 'Pseudomonas aeruginosa pneumonia',
        'patient_factors': {
            'age_years': 61, 'weight_kg': 85,
        },
    },
    # 10. Cross-reactivity (MEDIUM)
    {
        'alert_type': AlertType.DOSING_ALLERGY,
        'severity': AlertSeverity.MEDIUM,
        'drug': 'Cefazolin',
        'flag_type': 'allergy_cross_reactivity',
        'title': 'Dosing: Cephalosporin cross-reactivity with penicillin allergy',
        'summary': 'Patient has penicillin allergy (rash). Low cross-reactivity risk (1-2%) with cefazolin, but monitor closely.',
        'expected_dose': 'May continue with monitoring. Cross-reactivity risk is low for cefazolin.',
        'actual_dose': 'Cefazolin 2g IV q8h',
        'rule_source': 'Drug allergy cross-reactivity database',
        'indication': 'Surgical prophylaxis',
        'patient_factors': {
            'age_years': 55, 'weight_kg': 90,
        },
        'allergies': [
            {'drug': 'Penicillin', 'severity': 'moderate', 'reaction': 'rash'},
        ],
    },
]


class Command(BaseCommand):
    help = 'Create demo dosing verification alerts for testing and demonstration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing demo dosing data before creating new ones',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=10,
            help='Number of dosing alerts to create (default: 10)',
        )

    def handle(self, *args, **options):
        if options['clear']:
            deleted, _ = Alert.objects.filter(
                source_module='dosing_verification',
                source_id__startswith='demo-',
            ).delete()
            self.stdout.write(self.style.WARNING(
                f'Deleted {deleted} existing demo dosing alerts'
            ))

        now = timezone.now()
        count = options['count']
        created_count = 0

        for i in range(count):
            scenario = DEMO_SCENARIOS[i % len(DEMO_SCENARIOS)]
            patient = DEMO_PATIENTS[i % len(DEMO_PATIENTS)]
            unit = random.choice(DEMO_UNITS)

            # Random timing
            created_time = now - timedelta(
                hours=random.randint(0, 96),
                minutes=random.randint(0, 59),
            )

            demo_id = f"demo-dosing-{uuid.uuid4().hex[:12]}"

            # Determine if this should be resolved (for history variety)
            is_resolved = i >= count - 2 and count > 4

            # Build details JSONField
            details = {
                'drug': scenario['drug'],
                'flag_type': scenario['flag_type'],
                'flag_type_display': scenario['flag_type'].replace('_', ' ').title(),
                'indication': scenario.get('indication', ''),
                'expected_dose': scenario['expected_dose'],
                'actual_dose': scenario['actual_dose'],
                'rule_source': scenario['rule_source'],
                'patient_factors': scenario.get('patient_factors', {}),
            }

            # Add optional fields
            if 'allergies' in scenario:
                details['allergies'] = scenario['allergies']
            if 'co_medications' in scenario:
                details['co_medications'] = scenario['co_medications']

            # Build medication list for display
            details['medications'] = [{
                'drug_name': scenario['drug'],
                'dose_value': scenario['actual_dose'].split()[0] if scenario['actual_dose'] else '',
                'dose_unit': 'mg',
                'route': 'IV',
                'interval': 'q12h',
            }]

            # All flags (single flag for demo)
            details['flags'] = [{
                'flag_type': scenario['flag_type'],
                'severity': scenario['severity'],
                'drug': scenario['drug'],
                'message': scenario['summary'],
                'expected': scenario['expected_dose'],
                'actual': scenario['actual_dose'],
                'rule_source': scenario['rule_source'],
                'indication': scenario.get('indication', ''),
            }]

            alert = Alert.objects.create(
                alert_type=scenario['alert_type'],
                source_module='dosing_verification',
                source_id=demo_id,
                title=scenario['title'],
                summary=scenario['summary'],
                details=details,
                patient_id=patient['id'],
                patient_mrn=patient['mrn'],
                patient_name=patient['name'],
                patient_location=unit,
                severity=scenario['severity'],
                priority_score=90 if scenario['severity'] == AlertSeverity.CRITICAL else (
                    75 if scenario['severity'] == AlertSeverity.HIGH else (
                        50 if scenario['severity'] == AlertSeverity.MEDIUM else 25
                    )
                ),
                status=AlertStatus.RESOLVED if is_resolved else AlertStatus.PENDING,
            )

            # Backdate created_at
            Alert.objects.filter(id=alert.id).update(created_at=created_time)

            if is_resolved:
                resolved_time = created_time + timedelta(hours=random.randint(1, 8))
                resolution_reasons = ['dose_adjusted', 'interval_adjusted', 'clinical_justification',
                                       'therapy_changed', 'no_action_needed']
                Alert.objects.filter(id=alert.id).update(
                    resolved_at=resolved_time,
                    resolution_reason=random.choice(resolution_reasons),
                )

            AlertAudit.objects.create(
                alert=alert,
                action='created',
                old_status=None,
                new_status=AlertStatus.PENDING,
                details={'source': 'demo_dosing_generator'},
            )

            created_count += 1
            status_str = 'RESOLVED' if is_resolved else 'ACTIVE'
            self.stdout.write(
                f'  Created [{status_str}]: {scenario["flag_type"].upper()} - '
                f'{scenario["drug"]} ({patient["mrn"]}, {unit})'
            )

        self.stdout.write(self.style.SUCCESS(
            f'\nSuccessfully created {created_count} demo dosing verification alerts'
        ))
