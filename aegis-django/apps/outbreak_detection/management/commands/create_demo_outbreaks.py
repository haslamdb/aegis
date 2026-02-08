"""
Create demo outbreak detection data for development and testing.

Generates realistic outbreak clusters with cases using real CCHMC hospital units.

Usage:
    python manage.py create_demo_outbreaks                    # Create demo clusters
    python manage.py create_demo_outbreaks --clear            # Clear and recreate
    python manage.py create_demo_outbreaks --clear --count 8  # Clear and create 8
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertSeverity, AlertStatus
from apps.outbreak_detection.models import (
    OutbreakCluster, ClusterCase, ClusterStatus, ClusterSeverity,
)


# Demo cluster scenarios using real CCHMC units
CLUSTER_SCENARIOS = [
    {
        'infection_type': 'mrsa',
        'organism': 'MRSA',
        'unit': 'G3NE',  # PICU
        'case_count': 3,
        'severity': ClusterSeverity.MEDIUM,
        'status': ClusterStatus.ACTIVE,
        'patients': [
            {'mrn': 'MRN100201', 'organism': 'MRSA'},
            {'mrn': 'MRN100202', 'organism': 'MRSA'},
            {'mrn': 'MRN100203', 'organism': 'MRSA'},
        ],
    },
    {
        'infection_type': 'vre',
        'organism': 'VRE (Enterococcus faecium)',
        'unit': 'A6N',  # Hospital Medicine
        'case_count': 4,
        'severity': ClusterSeverity.HIGH,
        'status': ClusterStatus.ACTIVE,
        'patients': [
            {'mrn': 'MRN100301', 'organism': 'VRE (Enterococcus faecium)'},
            {'mrn': 'MRN100302', 'organism': 'VRE (Enterococcus faecium)'},
            {'mrn': 'MRN100303', 'organism': 'VRE (Enterococcus faecium)'},
            {'mrn': 'MRN100304', 'organism': 'VRE (Enterococcus faecium)'},
        ],
    },
    {
        'infection_type': 'cre',
        'organism': 'CRE (Klebsiella pneumoniae)',
        'unit': 'G5NE',  # BMT
        'case_count': 3,
        'severity': ClusterSeverity.HIGH,
        'status': ClusterStatus.INVESTIGATING,
        'patients': [
            {'mrn': 'MRN100401', 'organism': 'CRE (Klebsiella pneumoniae)'},
            {'mrn': 'MRN100402', 'organism': 'CRE (Klebsiella pneumoniae)'},
            {'mrn': 'MRN100403', 'organism': 'CRE (Klebsiella pneumoniae)'},
        ],
    },
    {
        'infection_type': 'cdi',
        'organism': 'Clostridioides difficile',
        'unit': 'A4N',  # GI/Nephrology
        'case_count': 4,
        'severity': ClusterSeverity.HIGH,
        'status': ClusterStatus.ACTIVE,
        'patients': [
            {'mrn': 'MRN100501', 'organism': 'Clostridioides difficile'},
            {'mrn': 'MRN100502', 'organism': 'Clostridioides difficile'},
            {'mrn': 'MRN100503', 'organism': 'Clostridioides difficile'},
            {'mrn': 'MRN100504', 'organism': 'Clostridioides difficile'},
        ],
    },
    {
        'infection_type': 'clabsi',
        'organism': 'Staphylococcus aureus',
        'unit': 'G6SE',  # CICU
        'case_count': 2,
        'severity': ClusterSeverity.LOW,
        'status': ClusterStatus.ACTIVE,
        'patients': [
            {'mrn': 'MRN100601', 'organism': 'Staphylococcus aureus'},
            {'mrn': 'MRN100602', 'organism': 'Staphylococcus aureus'},
        ],
    },
    {
        'infection_type': 'esbl',
        'organism': 'ESBL (Escherichia coli)',
        'unit': 'G1NE',  # NICU
        'case_count': 3,
        'severity': ClusterSeverity.MEDIUM,
        'status': ClusterStatus.RESOLVED,
        'resolved': True,
        'patients': [
            {'mrn': 'MRN100701', 'organism': 'ESBL (Escherichia coli)'},
            {'mrn': 'MRN100702', 'organism': 'ESBL (Escherichia coli)'},
            {'mrn': 'MRN100703', 'organism': 'ESBL (Escherichia coli)'},
        ],
    },
]


class Command(BaseCommand):
    help = 'Create demo outbreak detection data for development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear existing outbreak data before creating',
        )
        parser.add_argument(
            '--count', type=int, default=len(CLUSTER_SCENARIOS),
            help=f'Number of clusters to create (default: {len(CLUSTER_SCENARIOS)})',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write("Clearing existing outbreak data...")
            ClusterCase.objects.all().delete()
            OutbreakCluster.objects.all().delete()
            Alert.objects.filter(source_module='outbreak_detection').delete()
            self.stdout.write(self.style.SUCCESS("  Cleared."))

        count = min(options['count'], len(CLUSTER_SCENARIOS))
        self.stdout.write(f"Creating {count} demo outbreak clusters...")

        now = timezone.now()
        scenarios = CLUSTER_SCENARIOS[:count]
        created = 0

        for scenario in scenarios:
            # Create cluster
            days_ago_start = random.randint(3, 12)
            first_case = now - timedelta(days=days_ago_start)
            last_case = now - timedelta(days=random.randint(0, 2))

            cluster = OutbreakCluster.objects.create(
                infection_type=scenario['infection_type'],
                organism=scenario['organism'],
                unit=scenario['unit'],
                case_count=scenario['case_count'],
                first_case_date=first_case,
                last_case_date=last_case,
                window_days=14,
                status=scenario['status'],
                severity=scenario['severity'],
            )

            # Add resolution if resolved
            if scenario.get('resolved'):
                cluster.resolved_at = now - timedelta(days=1)
                cluster.resolved_by = 'Dr. Chen (IP)'
                cluster.resolution_notes = (
                    'Environmental cleaning completed. Contact precautions in place. '
                    'No new cases in 7 days. Cluster considered resolved.'
                )
                cluster.save()

            # Create cases
            for i, patient in enumerate(scenario['patients']):
                case_date = first_case + timedelta(days=i * random.randint(1, 3))
                if case_date > last_case:
                    case_date = last_case

                source = 'mdro'
                if scenario['infection_type'] == 'cdi':
                    source = 'cdi'
                elif scenario['infection_type'] in ('clabsi', 'cauti', 'ssi', 'vae'):
                    source = 'hai'

                ClusterCase.objects.create(
                    cluster=cluster,
                    source=source,
                    source_id=f"demo-{scenario['infection_type']}-{patient['mrn']}",
                    patient_id=f"Patient/{patient['mrn']}",
                    patient_mrn=patient['mrn'],
                    event_date=case_date,
                    organism=patient['organism'],
                    infection_type=scenario['infection_type'],
                    unit=scenario['unit'],
                )

            # Create alert for non-resolved clusters
            if scenario['status'] != ClusterStatus.RESOLVED:
                severity_map = {
                    ClusterSeverity.LOW: AlertSeverity.LOW,
                    ClusterSeverity.MEDIUM: AlertSeverity.MEDIUM,
                    ClusterSeverity.HIGH: AlertSeverity.HIGH,
                    ClusterSeverity.CRITICAL: AlertSeverity.CRITICAL,
                }

                alert = Alert.objects.create(
                    alert_type=AlertType.OUTBREAK_CLUSTER,
                    source_module='outbreak_detection',
                    source_id=str(cluster.id),
                    title=f"Potential Outbreak: {scenario['infection_type'].upper()} in {scenario['unit']}",
                    summary=(
                        f"{scenario['case_count']} {scenario['organism']} cases in "
                        f"{scenario['unit']} within 14 days"
                    ),
                    details={
                        'cluster_id': str(cluster.id),
                        'infection_type': scenario['infection_type'],
                        'unit': scenario['unit'],
                        'organism': scenario['organism'],
                        'case_count': scenario['case_count'],
                    },
                    patient_id='',
                    patient_mrn='',
                    patient_name='',
                    patient_location=scenario['unit'],
                    severity=severity_map.get(scenario['severity'], AlertSeverity.MEDIUM),
                    status=AlertStatus.PENDING,
                )

                AlertAudit.objects.create(
                    alert=alert,
                    action='created',
                    details=f"Demo outbreak cluster: {scenario['infection_type'].upper()} in {scenario['unit']}",
                )

            created += 1
            status_label = scenario['status'].label if hasattr(scenario['status'], 'label') else scenario['status']
            self.stdout.write(
                f"  {scenario['infection_type'].upper()} in {scenario['unit']} - "
                f"{scenario['case_count']} cases ({status_label})"
            )

        self.stdout.write(self.style.SUCCESS(
            f"\nCreated {created} outbreak clusters with cases and alerts."
        ))

        # Summary
        total_cases = ClusterCase.objects.count()
        total_alerts = Alert.objects.filter(source_module='outbreak_detection').count()
        self.stdout.write(f"  Total cluster cases: {total_cases}")
        self.stdout.write(f"  Total alerts: {total_alerts}")
