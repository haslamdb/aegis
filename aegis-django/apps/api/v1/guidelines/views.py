"""ViewSet for the Guideline Adherence API."""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.guideline_adherence.models import (
    BundleEpisode, EpisodeReview, EpisodeAssessment,
    EpisodeStatus, AdherenceLevel,
)
from apps.api.permissions import IsPhysicianOrHigher, CanManageGuidelineAdherence
from apps.api.throttling import WriteRateThrottle

from .serializers import (
    EpisodeListSerializer,
    EpisodeDetailSerializer,
    EpisodeReviewSubmitSerializer,
    EpisodeReviewSerializer,
)
from .filters import EpisodeFilter


class GuidelineEpisodeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Guideline Adherence episode API.

    list:          GET  /api/v1/guidelines/episodes/
    detail:        GET  /api/v1/guidelines/episodes/{uuid}/
    submit_review: POST /api/v1/guidelines/episodes/{uuid}/submit_review/
    stats:         GET  /api/v1/guidelines/episodes/stats/
    """

    queryset = BundleEpisode.objects.all()
    filterset_class = EpisodeFilter
    permission_classes = [IsPhysicianOrHigher]

    def get_serializer_class(self):
        if self.action == 'list':
            return EpisodeListSerializer
        return EpisodeDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'retrieve':
            qs = qs.prefetch_related('element_results', 'assessments', 'reviews')
        return qs

    def _get_ip(self, request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    @action(detail=True, methods=['post'],
            permission_classes=[CanManageGuidelineAdherence],
            throttle_classes=[WriteRateThrottle],
            serializer_class=EpisodeReviewSubmitSerializer,
            url_path='submit_review')
    def submit_review(self, request, pk=None):
        """Submit a review decision for an episode."""
        serializer = EpisodeReviewSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        episode = self.get_object()

        latest_assessment = episode.assessments.order_by('-created_at').first()
        llm_decision = ''
        if latest_assessment:
            llm_decision = latest_assessment.primary_determination

        reviewer_decision = serializer.validated_data['reviewer_decision']
        is_override = llm_decision != '' and reviewer_decision != llm_decision

        review = EpisodeReview.objects.create(
            episode=episode,
            assessment=latest_assessment,
            reviewer=request.user.username,
            reviewer_decision=reviewer_decision,
            llm_decision=llm_decision,
            is_override=is_override,
            override_reason_category=serializer.validated_data.get('override_reason', ''),
            deviation_type=serializer.validated_data.get('deviation_type', ''),
            notes=serializer.validated_data.get('notes', ''),
        )

        episode.review_status = 'reviewed'
        episode.overall_determination = reviewer_decision
        episode.save(update_fields=['review_status', 'overall_determination', 'updated_at'])

        return Response(EpisodeReviewSerializer(review).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Summary stats by bundle and adherence level."""
        days = int(request.query_params.get('days', 30))
        start = timezone.now() - timedelta(days=days)

        active = BundleEpisode.objects.filter(status=EpisodeStatus.ACTIVE).count()
        completed = BundleEpisode.objects.filter(
            status__in=[EpisodeStatus.COMPLETE, EpisodeStatus.CLOSED],
            completed_at__gte=start,
        )
        total_completed = completed.count()
        full = completed.filter(adherence_level=AdherenceLevel.FULL).count()

        by_bundle = (
            completed.values('bundle_id', 'bundle_name')
            .annotate(
                count=Count('id'),
                full_count=Count('id', filter=Q(adherence_level=AdherenceLevel.FULL)),
            )
            .order_by('bundle_id')
        )

        by_adherence = completed.values('adherence_level').annotate(count=Count('id'))

        reviews_period = EpisodeReview.objects.filter(reviewed_at__gte=start)
        review_count = reviews_period.count()
        override_count = reviews_period.filter(is_override=True).count()

        return Response({
            'days': days,
            'active_episodes': active,
            'completed_episodes': total_completed,
            'full_adherence': full,
            'overall_compliance': round(
                (full / total_completed * 100) if total_completed > 0 else 0, 1
            ),
            'by_bundle': [
                {
                    'bundle_id': item['bundle_id'],
                    'bundle_name': item['bundle_name'],
                    'total': item['count'],
                    'full_adherence': item['full_count'],
                    'compliance_pct': round(
                        (item['full_count'] / item['count'] * 100) if item['count'] > 0 else 0, 1
                    ),
                }
                for item in by_bundle
            ],
            'by_adherence_level': {
                item['adherence_level']: item['count'] for item in by_adherence
            },
            'reviews': review_count,
            'overrides': override_count,
            'override_rate': round(
                (override_count / review_count * 100) if review_count > 0 else 0, 1
            ),
        })
