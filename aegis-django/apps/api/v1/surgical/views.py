"""ViewSet for the Surgical Prophylaxis API (read-only)."""

from datetime import timedelta

from django.db.models import Count, Q, Avg, Max, Subquery, OuterRef
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.surgical_prophylaxis.models import (
    SurgicalCase, ProphylaxisEvaluation, ProcedureCategory,
)
from apps.api.permissions import IsPhysicianOrHigher

from .serializers import CaseListSerializer, CaseDetailSerializer
from .filters import CaseFilter


class SurgicalCaseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Surgical Prophylaxis case API (read-only).

    list:   GET  /api/v1/surgical/cases/
    detail: GET  /api/v1/surgical/cases/{uuid}/
    stats:  GET  /api/v1/surgical/cases/stats/
    """

    queryset = SurgicalCase.objects.all()
    filterset_class = CaseFilter
    permission_classes = [IsPhysicianOrHigher]

    def get_serializer_class(self):
        if self.action == 'list':
            return CaseListSerializer
        return CaseDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'retrieve':
            qs = qs.prefetch_related('evaluations', 'medications')
        return qs

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Compliance summary statistics."""
        days = int(request.query_params.get('days', 30))
        start = timezone.now() - timedelta(days=days)

        cases = SurgicalCase.objects.filter(created_at__gte=start)
        total_cases = cases.count()

        # Get latest evaluation per case (DB-agnostic, no DISTINCT ON)
        latest_eval_times = (
            ProphylaxisEvaluation.objects.filter(
                case__in=cases, excluded=False,
            )
            .values('case_id')
            .annotate(max_time=Max('evaluation_time'))
        )
        latest_eval_ids = []
        for entry in latest_eval_times:
            ev = ProphylaxisEvaluation.objects.filter(
                case_id=entry['case_id'],
                evaluation_time=entry['max_time'],
                excluded=False,
            ).values_list('id', flat=True).first()
            if ev:
                latest_eval_ids.append(ev)
        latest_evals = ProphylaxisEvaluation.objects.filter(id__in=latest_eval_ids)

        evaluated = latest_evals.count()
        compliant = latest_evals.filter(bundle_compliant=True).count()
        avg_score = latest_evals.aggregate(avg=Avg('compliance_score'))['avg'] or 0

        by_category = (
            cases.values('procedure_category')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        excluded = ProphylaxisEvaluation.objects.filter(
            case__in=cases, excluded=True,
        ).values('case_id').distinct().count()

        return Response({
            'days': days,
            'total_cases': total_cases,
            'evaluated_cases': evaluated,
            'excluded_cases': excluded,
            'compliant_cases': compliant,
            'compliance_rate': round(
                (compliant / evaluated * 100) if evaluated > 0 else 0, 1
            ),
            'avg_compliance_score': round(avg_score, 1),
            'by_category': {
                item['procedure_category']: item['count']
                for item in by_category
            },
        })
