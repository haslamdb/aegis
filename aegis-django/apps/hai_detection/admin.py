from django.contrib import admin

from .models import HAICandidate, HAIClassification, HAIReview, LLMAuditLog


@admin.register(HAICandidate)
class HAICandidateAdmin(admin.ModelAdmin):
    list_display = ('id', 'hai_type', 'patient_mrn', 'organism', 'status', 'created_at')
    list_filter = ('hai_type', 'status', 'meets_initial_criteria', 'nhsn_reported')
    search_fields = ('patient_mrn', 'patient_name', 'organism')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(HAIClassification)
class HAIClassificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate', 'decision', 'confidence', 'model_used', 'created_at')
    list_filter = ('decision', 'model_used', 'strictness_level')
    readonly_fields = ('id', 'created_at')


@admin.register(HAIReview)
class HAIReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate', 'reviewer', 'reviewer_decision', 'is_override', 'reviewed', 'created_at')
    list_filter = ('reviewer_decision', 'is_override', 'reviewed', 'queue_type')
    readonly_fields = ('id', 'created_at', 'reviewed_at')


@admin.register(LLMAuditLog)
class LLMAuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate', 'model', 'success', 'input_tokens', 'output_tokens', 'response_time_ms', 'created_at')
    list_filter = ('model', 'success')
    readonly_fields = ('created_at',)
