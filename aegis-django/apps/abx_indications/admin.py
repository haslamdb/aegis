"""Admin configuration for ABX Indication Monitoring."""

from django.contrib import admin

from .models import IndicationCandidate, IndicationReview, IndicationLLMAuditLog


@admin.register(IndicationCandidate)
class IndicationCandidateAdmin(admin.ModelAdmin):
    list_display = [
        'patient_mrn', 'medication_name', 'clinical_syndrome_display',
        'syndrome_confidence', 'cchmc_agent_category', 'status', 'created_at',
    ]
    list_filter = [
        'status', 'syndrome_confidence', 'cchmc_agent_category',
        'indication_not_documented', 'likely_viral', 'never_appropriate',
    ]
    search_fields = ['patient_mrn', 'patient_name', 'medication_name', 'clinical_syndrome']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(IndicationReview)
class IndicationReviewAdmin(admin.ModelAdmin):
    list_display = [
        'candidate', 'reviewer', 'syndrome_decision', 'agent_decision',
        'is_override', 'reviewed_at',
    ]
    list_filter = ['syndrome_decision', 'agent_decision', 'is_override']
    search_fields = ['candidate__patient_mrn', 'notes']
    readonly_fields = ['id', 'reviewed_at']
    ordering = ['-reviewed_at']


@admin.register(IndicationLLMAuditLog)
class IndicationLLMAuditLogAdmin(admin.ModelAdmin):
    list_display = [
        'model', 'success', 'input_tokens', 'output_tokens',
        'response_time_ms', 'created_at',
    ]
    list_filter = ['success', 'model']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
