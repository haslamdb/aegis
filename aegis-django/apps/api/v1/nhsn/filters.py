"""Filters for the NHSN Reporting API."""

import django_filters

from apps.nhsn_reporting.models import (
    NHSNEvent, HAIEventType,
    DenominatorMonthly,
    AUMonthlySummary,
    ARQuarterlySummary,
)


class NHSNEventFilter(django_filters.FilterSet):
    hai_type = django_filters.ChoiceFilter(choices=HAIEventType.choices)
    reported = django_filters.BooleanFilter()
    location_code = django_filters.CharFilter()

    class Meta:
        model = NHSNEvent
        fields = ['hai_type', 'reported', 'location_code']


class DenominatorMonthlyFilter(django_filters.FilterSet):
    month = django_filters.CharFilter()
    location_code = django_filters.CharFilter()

    class Meta:
        model = DenominatorMonthly
        fields = ['month', 'location_code']


class AUMonthlySummaryFilter(django_filters.FilterSet):
    reporting_month = django_filters.CharFilter()
    location_code = django_filters.CharFilter()

    class Meta:
        model = AUMonthlySummary
        fields = ['reporting_month', 'location_code']


class ARQuarterlySummaryFilter(django_filters.FilterSet):
    reporting_quarter = django_filters.CharFilter()
    location_code = django_filters.CharFilter()

    class Meta:
        model = ARQuarterlySummary
        fields = ['reporting_quarter', 'location_code']
