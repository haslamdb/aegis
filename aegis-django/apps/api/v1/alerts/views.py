"""ViewSet for the Alert API."""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.alerts.models import Alert, AlertStatus, AlertSeverity
from apps.api.permissions import IsPhysicianOrHigher, CanEditAlerts
from apps.api.throttling import WriteRateThrottle
from apps.api.mixins import AuditLogMixin

from .serializers import (
    AlertListSerializer,
    AlertDetailSerializer,
    AlertAcknowledgeSerializer,
    AlertSnoozeSerializer,
    AlertResolveSerializer,
    AlertAddNoteSerializer,
)
from .filters import AlertFilter


class AlertViewSet(AuditLogMixin, viewsets.ReadOnlyModelViewSet):
    """
    Alert management API.

    list:   GET  /api/v1/alerts/
    detail: GET  /api/v1/alerts/{uuid}/
    acknowledge: POST /api/v1/alerts/{uuid}/acknowledge/
    snooze:      POST /api/v1/alerts/{uuid}/snooze/
    resolve:     POST /api/v1/alerts/{uuid}/resolve/
    add_note:    POST /api/v1/alerts/{uuid}/add_note/
    stats:       GET  /api/v1/alerts/stats/
    """

    queryset = Alert.objects.all()
    filterset_class = AlertFilter
    permission_classes = [IsPhysicianOrHigher]

    def get_serializer_class(self):
        if self.action == 'list':
            return AlertListSerializer
        return AlertDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'retrieve':
            qs = qs.prefetch_related('audit_log')
        return qs

    def _get_ip(self, request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    @action(detail=True, methods=['post'],
            permission_classes=[CanEditAlerts],
            throttle_classes=[WriteRateThrottle],
            serializer_class=AlertAcknowledgeSerializer)
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        if alert.status == AlertStatus.RESOLVED:
            return Response(
                {'detail': 'Cannot acknowledge a resolved alert.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        alert.acknowledge(request.user, ip_address=self._get_ip(request))
        return Response(AlertDetailSerializer(alert).data)

    @action(detail=True, methods=['post'],
            permission_classes=[CanEditAlerts],
            throttle_classes=[WriteRateThrottle],
            serializer_class=AlertSnoozeSerializer)
    def snooze(self, request, pk=None):
        serializer = AlertSnoozeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alert = self.get_object()
        until = timezone.now() + timedelta(hours=serializer.validated_data['hours'])
        alert.snooze(request.user, until, ip_address=self._get_ip(request))
        return Response(AlertDetailSerializer(alert).data)

    @action(detail=True, methods=['post'],
            permission_classes=[CanEditAlerts],
            throttle_classes=[WriteRateThrottle],
            serializer_class=AlertResolveSerializer)
    def resolve(self, request, pk=None):
        serializer = AlertResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alert = self.get_object()
        alert.resolve(
            request.user,
            serializer.validated_data['reason'],
            notes=serializer.validated_data.get('notes'),
            ip_address=self._get_ip(request),
        )
        return Response(AlertDetailSerializer(alert).data)

    @action(detail=True, methods=['post'],
            permission_classes=[CanEditAlerts],
            throttle_classes=[WriteRateThrottle],
            serializer_class=AlertAddNoteSerializer,
            url_path='add_note')
    def add_note(self, request, pk=None):
        serializer = AlertAddNoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alert = self.get_object()

        if not alert.details:
            alert.details = {}
        if 'notes' not in alert.details:
            alert.details['notes'] = []

        alert.details['notes'].append({
            'user': request.user.username,
            'timestamp': timezone.now().isoformat(),
            'text': serializer.validated_data['note'],
        })
        alert.save(update_fields=['details', 'updated_at'])
        alert.create_audit_entry(
            action='note_added',
            user=request.user,
            ip_address=self._get_ip(request),
            extra_details={'note': serializer.validated_data['note']},
        )
        return Response(AlertDetailSerializer(alert).data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        days = int(request.query_params.get('days', 30))
        start = timezone.now() - timedelta(days=days)
        qs = Alert.objects.filter(created_at__gte=start)

        by_status = qs.values('status').annotate(count=Count('id'))
        by_severity = qs.values('severity').annotate(count=Count('id'))
        by_type = qs.values('alert_type').annotate(count=Count('id')).order_by('-count')[:10]

        return Response({
            'days': days,
            'total': qs.count(),
            'by_status': {item['status']: item['count'] for item in by_status},
            'by_severity': {item['severity']: item['count'] for item in by_severity},
            'top_types': {item['alert_type']: item['count'] for item in by_type},
        })
