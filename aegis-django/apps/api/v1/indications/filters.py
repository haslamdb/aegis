"""Filters for the ABX Indications API."""

import django_filters

from apps.abx_indications.models import (
    IndicationCandidate, CandidateStatus, AgentCategoryChoice,
)


class CandidateFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=CandidateStatus.choices)
    medication_name = django_filters.CharFilter(lookup_expr='icontains')
    clinical_syndrome = django_filters.CharFilter()
    syndrome_category = django_filters.CharFilter()
    cchmc_agent_category = django_filters.ChoiceFilter(choices=AgentCategoryChoice.choices)
    patient_mrn = django_filters.CharFilter(lookup_expr='icontains')
    created_after = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='gte',
    )
    created_before = django_filters.IsoDateTimeFilter(
        field_name='created_at', lookup_expr='lte',
    )

    class Meta:
        model = IndicationCandidate
        fields = [
            'status', 'medication_name', 'clinical_syndrome',
            'syndrome_category', 'cchmc_agent_category', 'patient_mrn',
            'created_after', 'created_before',
        ]
