"""
Management command to create demo antimicrobial usage alerts.

Usage:
    python manage.py create_demo_usage              # Create 8 demo alerts
    python manage.py create_demo_usage --clear       # Clear existing demo data first
    python manage.py create_demo_usage --count 20    # Create 20 alerts
"""

import random
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity


DEMO_PATIENTS = [
    {'name': 'Chen, Marcus', 'mrn': 'MRN-200101', 'id': 'P-200101'},
    {'name': 'Patel, Priya', 'mrn': 'MRN-200234', 'id': 'P-200234'},
    {'name': 'Rodriguez, Sofia', 'mrn': 'MRN-200367', 'id': 'P-200367'},
    {'name': 'Kim, Jayden', 'mrn': 'MRN-200489', 'id': 'P-200489'},
    {'name': 'Okonkwo, Amara', 'mrn': 'MRN-200512', 'id': 'P-200512'},
    {'name': 'Thompson, Elijah', 'mrn': 'MRN-200645', 'id': 'P-200645'},
    {'name': 'Nguyen, Lily', 'mrn': 'MRN-200778', 'id': 'P-200778'},
    {'name': 'Jackson, Carter', 'mrn': 'MRN-200891', 'id': 'P-200891'},
]

# CCHMC hospital units
DEMO_UNITS = {
    'G3NE': 'PICU',
    'G3NW': 'PICU',
    'G1NE': 'NICU',
    'G4NW': 'NICU',
    'G6SE': 'CICU',
    'G6NW': 'CICU',
    'G5NE': 'BMT',
    'G5SW': 'BMT',
    'A6N': 'Hospital Medicine',
    'A6S': 'Hospital Medicine',
    'A4N': 'GI/Nephrology',
    'A5N1': 'GI/Hematology',
    'A3N': 'Orthopedics',
    'A7C': 'Neurology',
}

DEMO_SCENARIOS = [
    {
        'medication_name': 'Meropenem',
        'rxnorm_code': '29561',
        'dose': '1g',
        'route': 'IV',
        'duration_hours': 96.5,
        'severity': AlertSeverity.HIGH,
        'unit': 'G3NE',
        'department': 'PICU',
        'status': AlertStatus.PENDING,
        'recommendation': (
            'Meropenem has exceeded 72 hours (currently 4.0 days). '
            'Consider reviewing antibiotic necessity and potential de-escalation based on '
            'culture and sensitivity results.'
        ),
    },
    {
        'medication_name': 'Vancomycin',
        'rxnorm_code': '11124',
        'dose': '15mg/kg',
        'route': 'IV',
        'duration_hours': 168.0,
        'severity': AlertSeverity.CRITICAL,
        'unit': 'G1NE',
        'department': 'NICU',
        'status': AlertStatus.PENDING,
        'recommendation': (
            'Vancomycin has been active for 7.0 days (168 hours). '
            'Urgent: Please review for de-escalation or discontinuation. '
            'Consider culture results and clinical response.'
        ),
    },
    {
        'medication_name': 'Meropenem',
        'rxnorm_code': '29561',
        'dose': '500mg',
        'route': 'IV',
        'duration_hours': 80.0,
        'severity': AlertSeverity.HIGH,
        'unit': 'A6N',
        'department': 'Hospital Medicine',
        'status': AlertStatus.ACKNOWLEDGED,
        'recommendation': (
            'Meropenem has exceeded 72 hours (currently 3.3 days). '
            'Consider reviewing antibiotic necessity and potential de-escalation based on '
            'culture and sensitivity results.'
        ),
    },
    {
        'medication_name': 'Vancomycin',
        'rxnorm_code': '11124',
        'dose': '20mg/kg',
        'route': 'IV',
        'duration_hours': 120.0,
        'severity': AlertSeverity.HIGH,
        'unit': 'G6SE',
        'department': 'CICU',
        'status': AlertStatus.PENDING,
        'recommendation': (
            'Vancomycin has exceeded 72 hours (currently 5.0 days). '
            'Consider reviewing antibiotic necessity and potential de-escalation based on '
            'culture and sensitivity results.'
        ),
    },
    {
        'medication_name': 'Meropenem',
        'rxnorm_code': '29561',
        'dose': '1g',
        'route': 'IV',
        'duration_hours': 74.0,
        'severity': AlertSeverity.HIGH,
        'unit': 'A4N',
        'department': 'GI/Nephrology',
        'status': AlertStatus.PENDING,
        'recommendation': (
            'Meropenem has exceeded 72 hours (currently 3.1 days). '
            'Consider reviewing antibiotic necessity and potential de-escalation based on '
            'culture and sensitivity results.'
        ),
    },
    {
        'medication_name': 'Vancomycin',
        'rxnorm_code': '11124',
        'dose': '15mg/kg',
        'route': 'IV',
        'duration_hours': 72.0,
        'severity': AlertSeverity.HIGH,
        'unit': 'G5NE',
        'department': 'BMT',
        'status': AlertStatus.RESOLVED,
        'resolution_reason': 'therapy_changed',
        'resolution_notes': 'De-escalated to daptomycin based on culture results showing MRSE susceptible to daptomycin.',
        'recommendation': (
            'Vancomycin has exceeded 72 hours (currently 3.0 days). '
            'Consider reviewing antibiotic necessity and potential de-escalation based on '
            'culture and sensitivity results.'
        ),
    },
    {
        'medication_name': 'Meropenem',
        'rxnorm_code': '29561',
        'dose': '2g',
        'route': 'IV',
        'duration_hours': 200.0,
        'severity': AlertSeverity.CRITICAL,
        'unit': 'A5N1',
        'department': 'GI/Hematology',
        'status': AlertStatus.PENDING,
        'recommendation': (
            'Meropenem has been active for 8.3 days (200 hours). '
            'Urgent: Please review for de-escalation or discontinuation. '
            'Consider culture results and clinical response.'
        ),
    },
    {
        'medication_name': 'Vancomycin',
        'rxnorm_code': '11124',
        'dose': '15mg/kg',
        'route': 'IV',
        'duration_hours': 96.0,
        'severity': AlertSeverity.HIGH,
        'unit': 'A3N',
        'department': 'Orthopedics',
        'status': AlertStatus.RESOLVED,
        'resolution_reason': 'therapy_changed',
        'resolution_notes': 'Culture showed MSSA, switched to nafcillin for targeted therapy.',
        'recommendation': (
            'Vancomycin has exceeded 72 hours (currently 4.0 days). '
            'Consider reviewing antibiotic necessity and potential de-escalation based on '
            'culture and sensitivity results.'
        ),
    },
]


class Command(BaseCommand):
    help = 'Create demo antimicrobial usage alerts for testing and demonstration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing demo antimicrobial usage data before creating new ones',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=8,
            help='Number of usage alerts to create (default: 8)',
        )

    def handle(self, *args, **options):
        if options['clear']:
            deleted, _ = Alert.objects.filter(
                source_module='antimicrobial_usage',
                source_id__startswith='demo-',
            ).delete()
            self.stdout.write(self.style.WARNING(
                f'Deleted {deleted} existing demo antimicrobial usage alerts'
            ))

        now = timezone.now()
        count = options['count']
        created_count = 0

        for i in range(count):
            scenario = DEMO_SCENARIOS[i % len(DEMO_SCENARIOS)]
            patient = DEMO_PATIENTS[i % len(DEMO_PATIENTS)]

            duration_hours = scenario['duration_hours']
            start_time = now - timedelta(hours=duration_hours)
            # Small random offset so alerts don't share exact times
            created_time = start_time + timedelta(
                hours=random.randint(0, max(1, int(duration_hours) - 72)),
            )

            order_id = f"demo-{uuid.uuid4().hex[:12]}"
            is_resolved = scenario['status'] == AlertStatus.RESOLVED

            alert = Alert.objects.create(
                alert_type=AlertType.BROAD_SPECTRUM_USAGE,
                source_module='antimicrobial_usage',
                source_id=f'demo-{order_id}',
                title=f"Broad-Spectrum Alert: {scenario['medication_name']}",
                summary=f"{scenario['medication_name']} > 72h ({duration_hours:.0f}h)",
                details={
                    'medication_name': scenario['medication_name'],
                    'rxnorm_code': scenario['rxnorm_code'],
                    'medication_fhir_id': order_id,
                    'duration_hours': duration_hours,
                    'threshold_hours': 72,
                    'dose': scenario['dose'],
                    'route': scenario['route'],
                    'start_date': start_time.isoformat(),
                    'recommendation': scenario['recommendation'],
                    'location': scenario['unit'],
                    'department': scenario['department'],
                    'patient_name': patient['name'],
                    'patient_mrn': patient['mrn'],
                    'patient_fhir_id': patient['id'],
                },
                patient_id=patient['id'],
                patient_mrn=patient['mrn'],
                patient_name=patient['name'],
                patient_location=scenario['unit'],
                severity=scenario['severity'],
                priority_score=90 if scenario['severity'] == AlertSeverity.CRITICAL else 75,
                status=AlertStatus.RESOLVED if is_resolved else scenario['status'],
            )

            # Backdate created_at
            Alert.objects.filter(id=alert.id).update(created_at=created_time)

            # Handle acknowledged status
            if scenario['status'] == AlertStatus.ACKNOWLEDGED:
                ack_time = created_time + timedelta(hours=random.randint(1, 4))
                Alert.objects.filter(id=alert.id).update(acknowledged_at=ack_time)

            # Handle resolved status
            if is_resolved:
                resolved_time = created_time + timedelta(hours=random.randint(2, 12))
                Alert.objects.filter(id=alert.id).update(
                    resolved_at=resolved_time,
                    resolution_reason=scenario.get('resolution_reason', 'therapy_changed'),
                    resolution_notes=scenario.get('resolution_notes', ''),
                )

            AlertAudit.objects.create(
                alert=alert,
                action='created',
                old_status=None,
                new_status=AlertStatus.PENDING,
                details={'source': 'demo_usage_generator'},
            )

            created_count += 1
            status_str = scenario['status'].upper()
            self.stdout.write(
                f'  Created [{status_str}]: {scenario["medication_name"]} '
                f'{duration_hours:.0f}h ({scenario["severity"].upper()}) - '
                f'{patient["name"]} ({scenario["unit"]})'
            )

        self.stdout.write(self.style.SUCCESS(
            f'\nSuccessfully created {created_count} demo antimicrobial usage alerts'
        ))
