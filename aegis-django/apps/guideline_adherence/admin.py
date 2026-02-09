from django.contrib import admin

from .models import (
    BundleEpisode, ElementResult, EpisodeAssessment,
    EpisodeReview, MonitorState,
)


@admin.register(BundleEpisode)
class BundleEpisodeAdmin(admin.ModelAdmin):
    list_display = [
        'patient_mrn', 'bundle_name', 'status',
        'adherence_percentage', 'adherence_level', 'trigger_time', 'created_at',
    ]
    list_filter = ['status', 'bundle_id', 'adherence_level']
    search_fields = ['patient_mrn', 'patient_name', 'bundle_name']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(ElementResult)
class ElementResultAdmin(admin.ModelAdmin):
    list_display = ['episode', 'element_name', 'status', 'required', 'deadline', 'completed_at']
    list_filter = ['status', 'required']
    search_fields = ['element_name', 'element_id']


@admin.register(EpisodeAssessment)
class EpisodeAssessmentAdmin(admin.ModelAdmin):
    list_display = ['episode', 'assessment_type', 'primary_determination', 'confidence', 'model_used', 'created_at']
    list_filter = ['assessment_type', 'primary_determination', 'confidence']


@admin.register(EpisodeReview)
class EpisodeReviewAdmin(admin.ModelAdmin):
    list_display = ['episode', 'reviewer', 'reviewer_decision', 'is_override', 'reviewed_at']
    list_filter = ['reviewer_decision', 'is_override']
    search_fields = ['reviewer', 'notes']


@admin.register(MonitorState)
class MonitorStateAdmin(admin.ModelAdmin):
    list_display = ['monitor_type', 'last_poll_time', 'last_run_status', 'updated_at']
