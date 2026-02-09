"""ViewSets for the NHSN Reporting API."""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.api.permissions import CanManageNHSNReporting
from apps.api.throttling import WriteRateThrottle
from apps.nhsn_reporting.models import (
    NHSNEvent,
    DenominatorMonthly,
    AUMonthlySummary,
    ARQuarterlySummary,
)
from apps.nhsn_reporting.services import NHSNReportingService

from .serializers import (
    NHSNEventListSerializer,
    NHSNEventDetailSerializer,
    MarkSubmittedSerializer,
    DenominatorMonthlySerializer,
    AUMonthlySummarySerializer,
    ARQuarterlySummarySerializer,
)
from .filters import (
    NHSNEventFilter,
    DenominatorMonthlyFilter,
    AUMonthlySummaryFilter,
    ARQuarterlySummaryFilter,
)


class NHSNEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    NHSN Event API.

    list:           GET  /api/v1/nhsn/events/
    detail:         GET  /api/v1/nhsn/events/{uuid}/
    mark_submitted: POST /api/v1/nhsn/events/mark_submitted/
    """

    queryset = NHSNEvent.objects.all().select_related('candidate')
    filterset_class = NHSNEventFilter
    permission_classes = [CanManageNHSNReporting]

    def get_serializer_class(self):
        if self.action == 'list':
            return NHSNEventListSerializer
        return NHSNEventDetailSerializer

    @action(
        detail=False,
        methods=['post'],
        throttle_classes=[WriteRateThrottle],
        serializer_class=MarkSubmittedSerializer,
        url_path='mark_submitted',
    )
    def mark_submitted(self, request):
        serializer = MarkSubmittedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event_ids = serializer.validated_data['event_ids']

        service = NHSNReportingService()
        count = service.mark_submitted(
            [str(eid) for eid in event_ids],
            request.user.username,
        )
        return Response({'success': True, 'marked_count': count})


class DenominatorMonthlyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Monthly denominators API.

    list:   GET /api/v1/nhsn/denominators/
    detail: GET /api/v1/nhsn/denominators/{uuid}/
    """

    queryset = DenominatorMonthly.objects.all()
    serializer_class = DenominatorMonthlySerializer
    filterset_class = DenominatorMonthlyFilter
    permission_classes = [CanManageNHSNReporting]


class AUMonthlySummaryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    AU monthly summaries API.

    list:   GET /api/v1/nhsn/au-summaries/
    detail: GET /api/v1/nhsn/au-summaries/{uuid}/
    """

    queryset = AUMonthlySummary.objects.all()
    serializer_class = AUMonthlySummarySerializer
    filterset_class = AUMonthlySummaryFilter
    permission_classes = [CanManageNHSNReporting]


class ARQuarterlySummaryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    AR quarterly summaries API.

    list:   GET /api/v1/nhsn/ar-summaries/
    detail: GET /api/v1/nhsn/ar-summaries/{uuid}/
    """

    queryset = ARQuarterlySummary.objects.all()
    serializer_class = ARQuarterlySummarySerializer
    filterset_class = ARQuarterlySummaryFilter
    permission_classes = [CanManageNHSNReporting]


class NHSNStatsViewSet(viewsets.ViewSet):
    """
    NHSN summary stats.

    stats: GET /api/v1/nhsn/stats/
    """

    permission_classes = [CanManageNHSNReporting]

    def list(self, request):
        service = NHSNReportingService()
        stats = service.get_stats()
        return Response(stats)
