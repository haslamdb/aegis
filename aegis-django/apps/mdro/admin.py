"""
MDRO Surveillance - Admin Configuration
"""

from django.contrib import admin
from .models import MDROCase, MDROReview, MDROProcessingLog


class MDROReviewInline(admin.TabularInline):
    model = MDROReview
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(MDROCase)
class MDROCaseAdmin(admin.ModelAdmin):
    list_display = (
        'patient_mrn', 'mdro_type', 'organism', 'unit',
        'transmission_status', 'culture_date', 'reviewed_by',
    )
    list_filter = ('mdro_type', 'transmission_status', 'unit', 'is_new')
    search_fields = ('patient_mrn', 'patient_name', 'organism', 'culture_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [MDROReviewInline]

    fieldsets = (
        ('Patient', {
            'fields': ('patient_id', 'patient_mrn', 'patient_name')
        }),
        ('Culture', {
            'fields': ('culture_id', 'culture_date', 'specimen_type', 'organism')
        }),
        ('MDRO Classification', {
            'fields': ('mdro_type', 'resistant_antibiotics', 'susceptibilities', 'classification_reason')
        }),
        ('Location & Timing', {
            'fields': ('location', 'unit', 'admission_date', 'days_since_admission', 'transmission_status')
        }),
        ('Status', {
            'fields': ('is_new', 'prior_history', 'reviewed_at', 'reviewed_by', 'notes')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(MDROProcessingLog)
class MDROProcessingLogAdmin(admin.ModelAdmin):
    list_display = ('culture_id', 'is_mdro', 'mdro_type', 'processed_at')
    list_filter = ('is_mdro', 'mdro_type')
    search_fields = ('culture_id',)
    readonly_fields = ('processed_at',)
