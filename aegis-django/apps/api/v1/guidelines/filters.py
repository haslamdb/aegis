"""Filters for the Guideline Adherence API."""

import django_filters

from apps.guideline_adherence.models import (
    BundleEpisode, EpisodeStatus, AdherenceLevel,
)


class EpisodeFilter(django_filters.FilterSet):
    bundle_id = django_filters.CharFilter()
    status = django_filters.ChoiceFilter(choices=EpisodeStatus.choices)
    adherence_level = django_filters.ChoiceFilter(choices=AdherenceLevel.choices)
    patient_mrn = django_filters.CharFilter(lookup_expr='icontains')
    created_after = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='gte',
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='lte',
    )

    class Meta:
        model = BundleEpisode
        fields = [
            'bundle_id', 'status', 'adherence_level', 'patient_mrn',
            'created_after', 'created_before',
        ]
