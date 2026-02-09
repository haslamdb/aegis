"""Filters for the Outbreak Detection API."""

import django_filters

from apps.outbreak_detection.models import (
    OutbreakCluster, ClusterStatus, ClusterSeverity,
)


class OutbreakClusterFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=ClusterStatus.choices)
    severity = django_filters.ChoiceFilter(choices=ClusterSeverity.choices)
    infection_type = django_filters.CharFilter(lookup_expr='iexact')
    unit = django_filters.CharFilter(lookup_expr='icontains')
    created_after = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='gte',
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='lte',
    )

    class Meta:
        model = OutbreakCluster
        fields = [
            'status', 'severity', 'infection_type', 'unit',
            'created_after', 'created_before',
        ]
