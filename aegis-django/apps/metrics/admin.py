"""Metrics admin."""
from django.contrib import admin
from .models import ProviderActivity, DailySnapshot

@admin.register(ProviderActivity)
class ProviderActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'action_type', 'module', 'patient_mrn', 'created_at']
    list_filter = ['action_type', 'module', 'created_at']
    search_fields = ['user__username', 'patient_mrn']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(DailySnapshot)
class DailySnapshotAdmin(admin.ModelAdmin):
    list_display = ['date', 'total_alerts', 'total_actions']
    list_filter = ['date']
    readonly_fields = ['created_at', 'updated_at']
