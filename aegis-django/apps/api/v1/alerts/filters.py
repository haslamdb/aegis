"""Filters for the Alert API."""

import django_filters

from apps.alerts.models import Alert, AlertType, AlertStatus, AlertSeverity


class AlertFilter(django_filters.FilterSet):
    alert_type = django_filters.ChoiceFilter(choices=AlertType.choices)
    status = django_filters.ChoiceFilter(choices=AlertStatus.choices)
    severity = django_filters.ChoiceFilter(choices=AlertSeverity.choices)
    source_module = django_filters.CharFilter()
    patient_mrn = django_filters.CharFilter(lookup_expr='icontains')
    created_after = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='gte',
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='lte',
    )

    class Meta:
        model = Alert
        fields = [
            'alert_type', 'status', 'severity', 'source_module',
            'patient_mrn', 'created_after', 'created_before',
        ]
