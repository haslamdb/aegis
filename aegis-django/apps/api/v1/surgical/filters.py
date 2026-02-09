"""Filters for the Surgical Prophylaxis API."""

import django_filters

from apps.surgical_prophylaxis.models import SurgicalCase, ProcedureCategory


class CaseFilter(django_filters.FilterSet):
    procedure_category = django_filters.ChoiceFilter(choices=ProcedureCategory.choices)
    patient_mrn = django_filters.CharFilter(lookup_expr='icontains')
    scheduled_after = django_filters.IsoDateTimeFilter(
        field_name='scheduled_or_time', lookup_expr='gte',
    )
    scheduled_before = django_filters.IsoDateTimeFilter(
        field_name='scheduled_or_time', lookup_expr='lte',
    )
    created_after = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='gte',
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='lte',
    )

    class Meta:
        model = SurgicalCase
        fields = [
            'procedure_category', 'patient_mrn',
            'scheduled_after', 'scheduled_before',
            'created_after', 'created_before',
        ]
