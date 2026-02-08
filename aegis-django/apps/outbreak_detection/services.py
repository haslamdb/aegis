"""
Outbreak Detection Service.

Combines data source queries and detection logic into a single service class.
Replaces Flask's detector.py, sources.py, and db.py with Django ORM operations.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Count, Q
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertSeverity, AlertStatus
from apps.hai_detection.models import HAICandidate
from apps.mdro.models import MDROCase

from .models import OutbreakCluster, ClusterCase, ClusterStatus, ClusterSeverity

logger = logging.getLogger(__name__)


def _get_config():
    """Get outbreak detection config from settings."""
    return getattr(settings, 'OUTBREAK_DETECTION', {})


class OutbreakDetectionService:
    """Service for outbreak detection operations."""

    def __init__(self):
        conf = _get_config()
        self.window_days = conf.get('CLUSTER_WINDOW_DAYS', 14)
        self.min_cluster_size = conf.get('MIN_CLUSTER_SIZE', 2)

    # ------------------------------------------------------------------
    # Data Sources - query existing Django models
    # ------------------------------------------------------------------

    def get_recent_cases(self, days=None):
        """Get recent cases from MDRO and HAI sources via Django ORM.

        Returns normalized list of dicts for detection processing.
        """
        window = days or self.window_days
        cutoff = timezone.now() - timedelta(days=window)
        cases = []

        # MDRO cases
        mdro_cases = MDROCase.objects.filter(
            culture_date__gte=cutoff,
        ).values(
            'id', 'patient_id', 'patient_mrn', 'culture_date',
            'organism', 'mdro_type', 'unit',
        )
        for mc in mdro_cases:
            cases.append({
                'source': 'mdro',
                'source_id': str(mc['id']),
                'patient_id': mc['patient_id'],
                'patient_mrn': mc['patient_mrn'],
                'event_date': mc['culture_date'],
                'organism': mc['organism'],
                'infection_type': mc['mdro_type'],
                'unit': mc['unit'] or '',
            })

        # HAI cases (confirmed, non-CDI)
        hai_cases = HAICandidate.objects.filter(
            status='confirmed',
            culture_date__gte=cutoff,
        ).exclude(
            hai_type='cdi',
        ).values(
            'id', 'patient_id', 'patient_mrn', 'culture_date',
            'organism', 'hai_type', 'patient_location',
        )
        for hc in hai_cases:
            cases.append({
                'source': 'hai',
                'source_id': str(hc['id']),
                'patient_id': hc['patient_id'],
                'patient_mrn': hc['patient_mrn'],
                'event_date': hc['culture_date'],
                'organism': hc['organism'],
                'infection_type': hc['hai_type'],
                'unit': hc['patient_location'] or '',
            })

        # CDI cases (confirmed CDI from HAI)
        cdi_cases = HAICandidate.objects.filter(
            hai_type='cdi',
            status='confirmed',
            culture_date__gte=cutoff,
        ).values(
            'id', 'patient_id', 'patient_mrn', 'culture_date',
            'patient_location',
        )
        for cc in cdi_cases:
            cases.append({
                'source': 'cdi',
                'source_id': str(cc['id']),
                'patient_id': cc['patient_id'],
                'patient_mrn': cc['patient_mrn'],
                'event_date': cc['culture_date'],
                'organism': 'Clostridioides difficile',
                'infection_type': 'cdi',
                'unit': cc['patient_location'] or '',
            })

        return cases

    # ------------------------------------------------------------------
    # Detection Logic
    # ------------------------------------------------------------------

    def run_detection(self, days=None):
        """Run outbreak detection on recent cases.

        Returns dict with detection results.
        """
        result = {
            'cases_analyzed': 0,
            'new_cases_processed': 0,
            'clusters_formed': 0,
            'clusters_updated': 0,
            'alerts_created': 0,
        }

        all_cases = self.get_recent_cases(days=days)
        result['cases_analyzed'] = len(all_cases)
        logger.info(f"Analyzing {len(all_cases)} cases for outbreak detection")

        for case_data in all_cases:
            try:
                process_result = self._process_case(case_data)
                if process_result['processed']:
                    result['new_cases_processed'] += 1
                    if process_result.get('cluster_formed'):
                        result['clusters_formed'] += 1
                    elif process_result.get('cluster_updated'):
                        result['clusters_updated'] += 1
                    if process_result.get('alert_created'):
                        result['alerts_created'] += 1
            except Exception as e:
                logger.error(f"Error processing case {case_data.get('source_id')}: {e}")

        return result

    def _process_case(self, case_data):
        """Process a single case for outbreak detection."""
        result = {
            'processed': False,
            'cluster_formed': False,
            'cluster_updated': False,
            'alert_created': False,
        }

        source = case_data['source']
        source_id = case_data['source_id']
        unit = case_data.get('unit', '')

        # Skip if already processed (ClusterCase exists)
        if ClusterCase.objects.filter(source=source, source_id=source_id).exists():
            return result

        # Need unit for clustering
        if not unit:
            return result

        infection_type = case_data['infection_type']
        event_date = case_data['event_date']

        # Find matching active cluster (same infection type + unit)
        existing_cluster = OutbreakCluster.objects.filter(
            infection_type=infection_type,
            unit=unit,
            status__in=[ClusterStatus.ACTIVE, ClusterStatus.INVESTIGATING],
        ).first()

        if existing_cluster:
            previous_severity = existing_cluster.severity
            try:
                case = ClusterCase.objects.create(
                    cluster=existing_cluster,
                    source=source,
                    source_id=source_id,
                    patient_id=case_data['patient_id'],
                    patient_mrn=case_data['patient_mrn'],
                    event_date=event_date,
                    organism=case_data.get('organism'),
                    infection_type=infection_type,
                    unit=unit,
                )
                existing_cluster.add_case(case)
                result['cluster_updated'] = True
                result['processed'] = True

                # Check for severity escalation
                if existing_cluster.severity != previous_severity:
                    self._create_cluster_alert(existing_cluster, 'cluster_escalated')
                    result['alert_created'] = True

            except IntegrityError:
                # Case already processed (race condition)
                pass
        else:
            # No existing cluster - create case and potentially form a new cluster
            # First, check if there are other unprocessed cases in same type+unit
            # For now, create a new cluster when min_cluster_size would be met

            # Create a new cluster with this case
            cluster = OutbreakCluster.objects.create(
                infection_type=infection_type,
                organism=case_data.get('organism'),
                unit=unit,
                window_days=self.window_days,
            )
            try:
                case = ClusterCase.objects.create(
                    cluster=cluster,
                    source=source,
                    source_id=source_id,
                    patient_id=case_data['patient_id'],
                    patient_mrn=case_data['patient_mrn'],
                    event_date=event_date,
                    organism=case_data.get('organism'),
                    infection_type=infection_type,
                    unit=unit,
                )
                cluster.add_case(case)
                result['cluster_formed'] = True
                result['processed'] = True

                # Create alert if cluster meets minimum size
                if cluster.case_count >= self.min_cluster_size:
                    self._create_cluster_alert(cluster, 'cluster_formed')
                    result['alert_created'] = True

            except IntegrityError:
                cluster.delete()

        return result

    def _create_cluster_alert(self, cluster, alert_type_label):
        """Create an Alert + AlertAudit for a cluster event."""
        if alert_type_label == 'cluster_formed':
            title = f"Potential Outbreak: {cluster.infection_type.upper()} in {cluster.unit}"
            summary = (
                f"{cluster.case_count} cases detected within {cluster.window_days} days. "
                f"Investigation recommended."
            )
        else:
            title = f"Outbreak Escalation: {cluster.infection_type.upper()} in {cluster.unit}"
            summary = (
                f"Cluster severity escalated to {cluster.get_severity_display()}. "
                f"Now {cluster.case_count} cases."
            )

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
            title=title,
            summary=summary,
            details={
                'cluster_id': str(cluster.id),
                'infection_type': cluster.infection_type,
                'unit': cluster.unit,
                'organism': cluster.organism,
                'case_count': cluster.case_count,
                'alert_subtype': alert_type_label,
            },
            patient_id='',
            patient_mrn='',
            patient_name='',
            patient_location=cluster.unit,
            severity=severity_map.get(cluster.severity, AlertSeverity.MEDIUM),
            status=AlertStatus.PENDING,
        )

        AlertAudit.objects.create(
            alert=alert,
            action='created',
            details=f"Outbreak {alert_type_label}: {cluster.infection_type.upper()} in {cluster.unit}",
        )

        return alert

    # ------------------------------------------------------------------
    # Cluster Management
    # ------------------------------------------------------------------

    def resolve_cluster(self, cluster_id, resolved_by, notes=None):
        """Mark a cluster as resolved."""
        try:
            cluster = OutbreakCluster.objects.get(id=cluster_id)
        except OutbreakCluster.DoesNotExist:
            return False

        cluster.resolve(resolved_by, notes)

        # Resolve associated pending alerts
        Alert.objects.filter(
            source_module='outbreak_detection',
            source_id=str(cluster_id),
            status=AlertStatus.PENDING,
        ).update(status=AlertStatus.RESOLVED)

        return True

    def update_cluster_status(self, cluster_id, status, notes=None, updated_by=None):
        """Update cluster status."""
        try:
            cluster = OutbreakCluster.objects.get(id=cluster_id)
        except OutbreakCluster.DoesNotExist:
            return False

        if status == 'resolved' or status == ClusterStatus.RESOLVED:
            return self.resolve_cluster(cluster_id, updated_by, notes)

        if status == 'not_outbreak':
            override_notes = f"[NOT AN OUTBREAK]"
            if notes:
                override_notes += f" {notes}"
            return self.resolve_cluster(cluster_id, updated_by, override_notes)

        cluster.status = status
        cluster.save(update_fields=['status', 'updated_at'])

        # Create audit on associated alerts
        alerts = Alert.objects.filter(
            source_module='outbreak_detection',
            source_id=str(cluster_id),
        )
        for alert in alerts:
            AlertAudit.objects.create(
                alert=alert,
                action='status_changed',
                performed_by=updated_by or '',
                details=f"Cluster status changed to {status}",
            )

        return True

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self):
        """Get summary statistics for outbreak detection."""
        active = OutbreakCluster.objects.filter(status=ClusterStatus.ACTIVE)
        investigating = OutbreakCluster.objects.filter(status=ClusterStatus.INVESTIGATING)
        resolved = OutbreakCluster.objects.filter(status=ClusterStatus.RESOLVED)

        pending_alerts = Alert.objects.filter(
            source_module='outbreak_detection',
            status=AlertStatus.PENDING,
        ).count()

        # By severity (active + investigating only)
        active_clusters = OutbreakCluster.objects.filter(
            status__in=[ClusterStatus.ACTIVE, ClusterStatus.INVESTIGATING],
        )
        by_severity = {}
        for sev in ClusterSeverity:
            count = active_clusters.filter(severity=sev).count()
            if count > 0:
                by_severity[sev.value] = count

        # By type (active + investigating only)
        by_type = {}
        type_counts = active_clusters.values('infection_type').annotate(
            count=Count('id'),
        )
        for tc in type_counts:
            by_type[tc['infection_type']] = tc['count']

        return {
            'active_clusters': active.count(),
            'investigating_clusters': investigating.count(),
            'resolved_clusters': resolved.count(),
            'pending_alerts': pending_alerts,
            'by_severity': by_severity,
            'by_type': by_type,
        }
