from django.contrib import admin
from .models import (
    SurgicalCase, ProphylaxisEvaluation, ProphylaxisMedication,
    ComplianceMetric, SurgicalJourney, PatientLocation,
    PreOpCheck, AlertEscalation,
)


class ProphylaxisMedicationInline(admin.TabularInline):
    model = ProphylaxisMedication
    extra = 0
    readonly_fields = ('fhir_id', 'created_at')


class ProphylaxisEvaluationInline(admin.StackedInline):
    model = ProphylaxisEvaluation
    extra = 0
    readonly_fields = ('evaluation_time', 'created_at')


@admin.register(SurgicalCase)
class SurgicalCaseAdmin(admin.ModelAdmin):
    list_display = ('case_id', 'patient_mrn', 'procedure_description',
                    'procedure_category', 'scheduled_or_time', 'created_at')
    list_filter = ('procedure_category', 'is_emergency', 'has_beta_lactam_allergy',
                   'mrsa_colonized')
    search_fields = ('case_id', 'patient_mrn', 'patient_name', 'procedure_description')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [ProphylaxisMedicationInline, ProphylaxisEvaluationInline]


@admin.register(ProphylaxisEvaluation)
class ProphylaxisEvaluationAdmin(admin.ModelAdmin):
    list_display = ('case', 'bundle_compliant', 'compliance_score', 'elements_met',
                    'elements_total', 'excluded', 'evaluation_time')
    list_filter = ('bundle_compliant', 'excluded')
    search_fields = ('case__patient_mrn', 'case__procedure_description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProphylaxisMedication)
class ProphylaxisMedicationAdmin(admin.ModelAdmin):
    list_display = ('case', 'medication_type', 'medication_name', 'dose_mg',
                    'route', 'event_time')
    list_filter = ('medication_type', 'route')
    search_fields = ('medication_name', 'case__patient_mrn')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ComplianceMetric)
class ComplianceMetricAdmin(admin.ModelAdmin):
    list_display = ('period_type', 'period_start', 'period_end', 'total_cases',
                    'bundle_compliance_rate', 'procedure_category')
    list_filter = ('period_type', 'procedure_category')


@admin.register(SurgicalJourney)
class SurgicalJourneyAdmin(admin.ModelAdmin):
    list_display = ('journey_id', 'patient_mrn', 'current_state', 'order_exists',
                    'administered', 'scheduled_time', 'completed_at')
    list_filter = ('current_state', 'order_exists', 'administered', 'excluded')
    search_fields = ('journey_id', 'patient_mrn', 'patient_name')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(PatientLocation)
class PatientLocationAdmin(admin.ModelAdmin):
    list_display = ('patient_mrn', 'location_code', 'location_state', 'event_time')
    list_filter = ('location_state',)
    search_fields = ('patient_mrn', 'location_code')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(PreOpCheck)
class PreOpCheckAdmin(admin.ModelAdmin):
    list_display = ('journey', 'trigger_type', 'alert_required', 'alert_severity',
                    'order_exists', 'administered', 'trigger_time')
    list_filter = ('trigger_type', 'alert_required', 'alert_severity')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AlertEscalation)
class AlertEscalationAdmin(admin.ModelAdmin):
    list_display = ('alert_ref', 'trigger_type', 'escalation_level', 'recipient_role',
                    'delivery_channel', 'delivery_status', 'sent_at', 'escalated')
    list_filter = ('trigger_type', 'delivery_status', 'escalated', 'recipient_role')
    search_fields = ('alert_ref',)
    readonly_fields = ('created_at', 'updated_at')
