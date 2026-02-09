from django.contrib import admin

from .models import (
    NHSNEvent, DenominatorDaily, DenominatorMonthly,
    AUMonthlySummary, AUAntimicrobialUsage, AUPatientLevel,
    ARQuarterlySummary, ARIsolate, ARSusceptibility, ARPhenotypeSummary,
    SubmissionAudit,
)


@admin.register(NHSNEvent)
class NHSNEventAdmin(admin.ModelAdmin):
    list_display = ['hai_type', 'event_date', 'location_code', 'pathogen_code', 'reported', 'created_at']
    list_filter = ['hai_type', 'reported']
    search_fields = ['pathogen_code', 'location_code']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(DenominatorDaily)
class DenominatorDailyAdmin(admin.ModelAdmin):
    list_display = ['date', 'location_code', 'patient_days', 'central_line_days', 'ventilator_days']
    list_filter = ['location_code']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(DenominatorMonthly)
class DenominatorMonthlyAdmin(admin.ModelAdmin):
    list_display = ['month', 'location_code', 'patient_days', 'central_line_days', 'ventilator_days', 'submitted_at']
    list_filter = ['location_code']
    search_fields = ['month']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(AUMonthlySummary)
class AUMonthlySummaryAdmin(admin.ModelAdmin):
    list_display = ['reporting_month', 'location_code', 'patient_days', 'admissions', 'submitted_at']
    list_filter = ['location_code']
    search_fields = ['reporting_month']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(AUAntimicrobialUsage)
class AUAntimicrobialUsageAdmin(admin.ModelAdmin):
    list_display = ['antimicrobial_name', 'antimicrobial_class', 'route', 'days_of_therapy', 'defined_daily_doses']
    list_filter = ['route', 'antimicrobial_class']
    search_fields = ['antimicrobial_name', 'antimicrobial_code']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(AUPatientLevel)
class AUPatientLevelAdmin(admin.ModelAdmin):
    list_display = ['patient_mrn', 'antimicrobial_name', 'route', 'start_date', 'days_of_therapy']
    list_filter = ['route']
    search_fields = ['patient_mrn', 'antimicrobial_name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ARQuarterlySummary)
class ARQuarterlySummaryAdmin(admin.ModelAdmin):
    list_display = ['reporting_quarter', 'location_code', 'submitted_at']
    list_filter = ['location_code']
    search_fields = ['reporting_quarter']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ARIsolate)
class ARIsolateAdmin(admin.ModelAdmin):
    list_display = ['organism_name', 'specimen_type', 'specimen_date', 'patient_mrn', 'is_first_isolate']
    list_filter = ['specimen_type', 'is_first_isolate', 'is_hai_associated']
    search_fields = ['organism_name', 'patient_mrn']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ARSusceptibility)
class ARSusceptibilityAdmin(admin.ModelAdmin):
    list_display = ['antimicrobial_name', 'interpretation', 'mic_value', 'testing_method']
    list_filter = ['interpretation']
    search_fields = ['antimicrobial_name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ARPhenotypeSummary)
class ARPhenotypeSummaryAdmin(admin.ModelAdmin):
    list_display = ['organism_name', 'phenotype', 'total_isolates', 'resistant_isolates', 'percent_resistant']
    list_filter = ['phenotype']
    search_fields = ['organism_name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(SubmissionAudit)
class SubmissionAuditAdmin(admin.ModelAdmin):
    list_display = ['action', 'submission_type', 'reporting_period', 'user', 'event_count', 'success', 'created_at']
    list_filter = ['action', 'submission_type', 'success']
    search_fields = ['user', 'notes']
    readonly_fields = ['created_at', 'updated_at']
