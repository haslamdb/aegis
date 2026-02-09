"""ViewSet for the ABX Indications API."""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.abx_indications.models import (
    IndicationCandidate, IndicationReview,
    CandidateStatus, AgentCategoryChoice,
)
from apps.alerts.models import AlertStatus, ResolutionReason
from apps.api.permissions import IsPhysicianOrHigher, CanEditAlerts
from apps.api.throttling import WriteRateThrottle

from .serializers import (
    CandidateListSerializer,
    CandidateDetailSerializer,
    CandidateReviewSubmitSerializer,
    IndicationReviewSerializer,
)
from .filters import CandidateFilter


class IndicationCandidateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ABX Indication Candidate API.

    list:          GET  /api/v1/indications/candidates/
    detail:        GET  /api/v1/indications/candidates/{uuid}/
    submit_review: POST /api/v1/indications/candidates/{uuid}/submit_review/
    stats:         GET  /api/v1/indications/candidates/stats/
    """

    queryset = IndicationCandidate.objects.all()
    filterset_class = CandidateFilter
    permission_classes = [IsPhysicianOrHigher]

    def get_serializer_class(self):
        if self.action == 'list':
            return CandidateListSerializer
        return CandidateDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'retrieve':
            qs = qs.prefetch_related('reviews')
        return qs

    def _get_ip(self, request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    @action(detail=True, methods=['post'],
            permission_classes=[CanEditAlerts],
            throttle_classes=[WriteRateThrottle],
            serializer_class=CandidateReviewSubmitSerializer,
            url_path='submit_review')
    def submit_review(self, request, pk=None):
        """Submit a review for an indication candidate."""
        serializer = CandidateReviewSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        candidate = self.get_object()

        review = IndicationReview.objects.create(
            candidate=candidate,
            reviewer=request.user,
            syndrome_decision=serializer.validated_data['syndrome_decision'],
            confirmed_syndrome=serializer.validated_data.get('confirmed_syndrome', ''),
            confirmed_syndrome_display=serializer.validated_data.get('confirmed_syndrome_display', ''),
            agent_decision=serializer.validated_data.get('agent_decision', ''),
            agent_notes=serializer.validated_data.get('agent_notes', ''),
            is_override=serializer.validated_data.get('is_override', False),
            notes=serializer.validated_data.get('notes', ''),
        )

        candidate.status = CandidateStatus.REVIEWED
        candidate.save(update_fields=['status', 'updated_at'])

        # Resolve associated alert if present
        if candidate.alert and candidate.alert.status != AlertStatus.RESOLVED:
            candidate.alert.resolve(
                request.user,
                ResolutionReason.ACCEPTED,
                notes=f"Reviewed: {review.get_syndrome_decision_display()}",
                ip_address=self._get_ip(request),
            )

        return Response(IndicationReviewSerializer(review).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Summary statistics for indication monitoring."""
        days = int(request.query_params.get('days', 30))
        start = timezone.now() - timedelta(days=days)

        active = IndicationCandidate.objects.filter(
            status__in=[CandidateStatus.PENDING, CandidateStatus.ALERTED],
        )
        pending_count = active.count()

        red_flag_count = active.filter(
            Q(indication_not_documented=True) |
            Q(likely_viral=True) |
            Q(never_appropriate=True) |
            Q(asymptomatic_bacteriuria=True)
        ).count()

        off_guideline_count = active.filter(
            cchmc_agent_category=AgentCategoryChoice.OFF_GUIDELINE,
        ).count()

        reviewed = IndicationCandidate.objects.filter(
            status__in=[CandidateStatus.REVIEWED, CandidateStatus.AUTO_ACCEPTED],
            updated_at__gte=start,
        )

        by_status = (
            IndicationCandidate.objects.filter(created_at__gte=start)
            .values('status')
            .annotate(count=Count('id'))
        )

        by_syndrome = (
            IndicationCandidate.objects.filter(created_at__gte=start)
            .exclude(clinical_syndrome='')
            .values('clinical_syndrome', 'clinical_syndrome_display')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )

        reviews_period = IndicationReview.objects.filter(reviewed_at__gte=start)
        override_count = reviews_period.filter(is_override=True).count()

        return Response({
            'days': days,
            'pending_count': pending_count,
            'red_flag_count': red_flag_count,
            'off_guideline_count': off_guideline_count,
            'reviewed_count': reviewed.count(),
            'by_status': {item['status']: item['count'] for item in by_status},
            'top_syndromes': [
                {
                    'syndrome': item['clinical_syndrome'],
                    'display': item['clinical_syndrome_display'],
                    'count': item['count'],
                }
                for item in by_syndrome
            ],
            'review_overrides': override_count,
        })
