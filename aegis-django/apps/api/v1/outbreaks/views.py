"""ViewSet for the Outbreak Detection API."""

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.outbreak_detection.models import (
    OutbreakCluster, ClusterCase, ClusterStatus, ClusterSeverity,
)
from apps.api.permissions import IsPhysicianOrHigher, CanManageOutbreakDetection
from apps.api.throttling import WriteRateThrottle

from .serializers import (
    OutbreakClusterListSerializer,
    OutbreakClusterDetailSerializer,
    ClusterStatusUpdateSerializer,
)
from .filters import OutbreakClusterFilter


class OutbreakClusterViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Outbreak Cluster management API.

    list:          GET  /api/v1/outbreaks/clusters/
    detail:        GET  /api/v1/outbreaks/clusters/{uuid}/
    update_status: POST /api/v1/outbreaks/clusters/{uuid}/update_status/
    stats:         GET  /api/v1/outbreaks/clusters/stats/
    """

    queryset = OutbreakCluster.objects.all()
    filterset_class = OutbreakClusterFilter
    permission_classes = [IsPhysicianOrHigher]

    def get_serializer_class(self):
        if self.action == 'list':
            return OutbreakClusterListSerializer
        return OutbreakClusterDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'retrieve':
            qs = qs.prefetch_related('cases')
        return qs

    @action(detail=True, methods=['post'],
            permission_classes=[CanManageOutbreakDetection],
            throttle_classes=[WriteRateThrottle],
            serializer_class=ClusterStatusUpdateSerializer,
            url_path='update_status')
    def update_status(self, request, pk=None):
        """Update cluster status (investigate, resolve, etc.)."""
        serializer = ClusterStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cluster = self.get_object()

        new_status = serializer.validated_data['status']
        notes = serializer.validated_data.get('notes', '')
        reviewer = request.user.get_full_name() or request.user.username

        if new_status == ClusterStatus.RESOLVED:
            cluster.resolve(resolved_by=reviewer, notes=notes)
        else:
            cluster.status = new_status
            if notes:
                cluster.resolution_notes = notes
            cluster.save(update_fields=['status', 'resolution_notes', 'updated_at'])

        return Response(OutbreakClusterDetailSerializer(cluster).data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get outbreak cluster summary statistics."""
        days = int(request.query_params.get('days', 30))
        cutoff = timezone.now() - timedelta(days=days)

        qs = OutbreakCluster.objects.all()
        recent = qs.filter(created_at__gte=cutoff)

        # Active clusters (not just recent — all currently active)
        active_statuses = [ClusterStatus.ACTIVE, ClusterStatus.INVESTIGATING]
        active = qs.filter(status__in=active_statuses)

        by_status = recent.values('status').annotate(count=Count('id'))
        by_severity = active.values('severity').annotate(count=Count('id'))
        by_type = active.values('infection_type').annotate(count=Count('id'))

        total_cases = ClusterCase.objects.filter(
            cluster__status__in=active_statuses,
        ).count()

        return Response({
            'days': days,
            'total_recent': recent.count(),
            'active_clusters': active.count(),
            'active_cases': total_cases,
            'by_status': {item['status']: item['count'] for item in by_status},
            'by_severity': {item['severity']: item['count'] for item in by_severity},
            'by_infection_type': {item['infection_type']: item['count'] for item in by_type},
        })
