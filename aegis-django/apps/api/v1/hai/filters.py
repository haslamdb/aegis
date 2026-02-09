"""Filters for the HAI Detection API."""

import django_filters

from apps.hai_detection.models import HAICandidate, HAIType, CandidateStatus


class HAICandidateFilter(django_filters.FilterSet):
    hai_type = django_filters.ChoiceFilter(choices=HAIType.choices)
    status = django_filters.ChoiceFilter(choices=CandidateStatus.choices)
    patient_mrn = django_filters.CharFilter(lookup_expr='icontains')
    organism = django_filters.CharFilter(lookup_expr='icontains')
    created_after = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='gte',
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='lte',
    )

    class Meta:
        model = HAICandidate
        fields = [
            'hai_type', 'status', 'patient_mrn', 'organism',
            'created_after', 'created_before',
        ]
