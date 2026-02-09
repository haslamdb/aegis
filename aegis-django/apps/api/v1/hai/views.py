"""ViewSet for the HAI Detection API."""

from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.hai_detection.models import (
    HAICandidate, HAIClassification, HAIReview,
    HAIType, CandidateStatus, ClassificationDecision,
    ReviewerDecision, ReviewQueueType,
)
from apps.alerts.models import Alert, AlertStatus
from apps.api.permissions import IsPhysicianOrHigher, CanManageHAIDetection
from apps.api.throttling import WriteRateThrottle

from .serializers import (
    HAICandidateListSerializer,
    HAICandidateDetailSerializer,
    HAIReviewSubmitSerializer,
)
from .filters import HAICandidateFilter


class HAICandidateViewSet(viewsets.ReadOnlyModelViewSet):
    """
    HAI Candidate management API.

    list:          GET  /api/v1/hai/candidates/
    detail:        GET  /api/v1/hai/candidates/{uuid}/
    submit_review: POST /api/v1/hai/candidates/{uuid}/submit_review/
    stats:         GET  /api/v1/hai/candidates/stats/
    """

    queryset = HAICandidate.objects.all()
    filterset_class = HAICandidateFilter
    permission_classes = [IsPhysicianOrHigher]

    def get_serializer_class(self):
        if self.action == 'list':
            return HAICandidateListSerializer
        return HAICandidateDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'retrieve':
            qs = qs.prefetch_related('classifications', 'reviews')
        return qs

    @action(detail=True, methods=['post'],
            permission_classes=[CanManageHAIDetection],
            throttle_classes=[WriteRateThrottle],
            serializer_class=HAIReviewSubmitSerializer,
            url_path='submit_review')
    def submit_review(self, request, pk=None):
        """Submit an IP review for a candidate."""
        serializer = HAIReviewSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        candidate = self.get_object()

        decision = serializer.validated_data['decision']
        notes = serializer.validated_data.get('notes', '')
        override_reason = serializer.validated_data.get('override_reason', '')
        override_reason_category = serializer.validated_data.get('override_reason_category', '')
        extraction_corrections = serializer.validated_data.get('extraction_corrections')

        reviewer = request.user.get_full_name() or request.user.username

        # Map to ReviewerDecision
        decision_map = {
            'confirmed': ReviewerDecision.CONFIRMED,
            'rejected': ReviewerDecision.REJECTED,
            'needs_more_info': ReviewerDecision.NEEDS_MORE_INFO,
        }
        decision_enum = decision_map[decision]

        # Determine override status
        latest_classification = candidate.latest_classification
        llm_decision = ''
        classification = None
        is_override = False

        if latest_classification:
            classification = latest_classification
            llm_decision = latest_classification.decision

            if llm_decision == ClassificationDecision.HAI_CONFIRMED and decision == 'rejected':
                is_override = True
            elif llm_decision == ClassificationDecision.NOT_HAI and decision == 'confirmed':
                is_override = True

        # Build review notes
        decision_notes = {
            'confirmed': 'HAI confirmed by IP review.',
            'rejected': 'Not HAI.',
            'needs_more_info': 'Additional review required.',
        }
        full_notes = f"{decision_notes[decision]} {notes}".strip()

        # Create the review
        review = HAIReview.objects.create(
            candidate=candidate,
            classification=classification,
            queue_type=ReviewQueueType.IP_REVIEW,
            reviewed=decision != 'needs_more_info',
            reviewer=reviewer,
            reviewer_decision=decision_enum,
            reviewer_notes=full_notes,
            llm_decision=llm_decision,
            is_override=is_override,
            override_reason=override_reason if is_override else '',
            override_reason_category=override_reason_category if is_override else '',
            extraction_corrections=extraction_corrections if is_override else None,
            reviewed_at=timezone.now() if decision != 'needs_more_info' else None,
        )

        # Update candidate status for final decisions
        if decision in ('confirmed', 'rejected'):
            if decision == 'confirmed':
                candidate.status = CandidateStatus.CONFIRMED
            else:
                candidate.status = CandidateStatus.REJECTED
            candidate.save(update_fields=['status', 'updated_at'])

            # Update corresponding Alert if it exists
            alert = Alert.objects.filter(
                source_module='hai_detection',
                source_id=str(candidate.id),
            ).first()
            if alert:
                alert.status = AlertStatus.RESOLVED
                if candidate.status == CandidateStatus.CONFIRMED:
                    alert.resolution_reason = 'accepted'
                else:
                    alert.resolution_reason = 'false_positive'
                alert.resolution_notes = full_notes
                alert.resolved_at = timezone.now()
                alert.save(update_fields=[
                    'status', 'resolution_reason', 'resolution_notes', 'resolved_at',
                ])

        return Response({
            'new_status': candidate.status,
            'is_override': is_override,
            'review_id': str(review.id),
        })

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get HAI candidate summary statistics."""
        days = int(request.query_params.get('days', 30))
        cutoff = timezone.now() - timedelta(days=days)

        qs = HAICandidate.objects.all()
        recent = qs.filter(created_at__gte=cutoff)

        by_type = recent.values('hai_type').annotate(count=Count('id'))
        by_status = recent.values('status').annotate(count=Count('id'))

        # Active counts
        active_statuses = [
            CandidateStatus.PENDING,
            CandidateStatus.CLASSIFIED,
            CandidateStatus.PENDING_REVIEW,
        ]
        active_count = qs.filter(status__in=active_statuses).count()
        pending_review = qs.filter(status=CandidateStatus.PENDING_REVIEW).count()

        # Override rate
        reviews = HAIReview.objects.filter(
            reviewed=True, reviewed_at__gte=cutoff,
        )
        total_reviewed = reviews.count()
        overrides = reviews.filter(is_override=True).count()

        return Response({
            'days': days,
            'total': recent.count(),
            'active': active_count,
            'pending_review': pending_review,
            'by_type': {item['hai_type']: item['count'] for item in by_type},
            'by_status': {item['status']: item['count'] for item in by_status},
            'total_reviewed': total_reviewed,
            'overrides': overrides,
            'accuracy_pct': round(
                100 * (total_reviewed - overrides) / max(total_reviewed, 1), 1
            ),
        })
