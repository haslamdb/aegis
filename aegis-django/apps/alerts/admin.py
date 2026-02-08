"""Django admin for alerts app."""

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone

from .models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    """Admin interface for Alert model."""

    list_display = [
        'id_short',
        'alert_type_badge',
        'severity_badge',
        'patient_mrn',
        'patient_location',
        'status_badge',
        'created_at',
        'is_actionable_display',
    ]

    list_filter = [
        'alert_type',
        'severity',
        'status',
        'source_module',
        'created_at',
    ]

    search_fields = [
        'id',
        'patient_mrn',
        'patient_name',
        'title',
        'summary',
    ]

    readonly_fields = [
        'id',
        'created_at',
        'updated_at',
        'sent_at',
        'acknowledged_at',
        'acknowledged_by',
        'resolved_at',
        'resolved_by',
    ]

    fieldsets = (
        ('Alert Information', {
            'fields': ('id', 'alert_type', 'source_module', 'source_id', 'title', 'summary', 'details')
        }),
        ('Patient Information', {
            'fields': ('patient_id', 'patient_mrn', 'patient_name', 'patient_location')
        }),
        ('Priority', {
            'fields': ('severity', 'priority_score')
        }),
        ('Status', {
            'fields': (
                'status',
                'sent_at',
                'acknowledged_at',
                'acknowledged_by',
                'resolved_at',
                'resolved_by',
                'resolution_reason',
                'resolution_notes',
            )
        }),
        ('Snooze', {
            'fields': ('snoozed_until', 'snoozed_by'),
            'classes': ('collapse',)
        }),
        ('Other', {
            'fields': ('notes', 'expires_at', 'notification_sent', 'notification_channels'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    date_hierarchy = 'created_at'
    ordering = ['-created_at']

    def id_short(self, obj):
        """Display shortened UUID."""
        return str(obj.id)[:8]
    id_short.short_description = 'ID'

    def alert_type_badge(self, obj):
        """Display alert type as badge."""
        colors = {
            'clabsi': '#dc3545',
            'ssi': '#dc3545',
            'cauti': '#dc3545',
            'vae': '#dc3545',
            'cdi': '#dc3545',
        }
        color = colors.get(obj.alert_type, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_alert_type_display()
        )
    alert_type_badge.short_description = 'Type'

    def severity_badge(self, obj):
        """Display severity as colored badge."""
        colors = {
            'critical': '#dc3545',
            'high': '#fd7e14',
            'medium': '#ffc107',
            'low': '#20c997',
            'info': '#17a2b8',
        }
        color = colors.get(obj.severity, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_severity_display()
        )
    severity_badge.short_description = 'Severity'

    def status_badge(self, obj):
        """Display status as colored badge."""
        colors = {
            'pending': '#ffc107',
            'sent': '#17a2b8',
            'acknowledged': '#6f42c1',
            'in_progress': '#007bff',
            'snoozed': '#6c757d',
            'resolved': '#28a745',
            'expired': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def is_actionable_display(self, obj):
        """Display whether alert is actionable."""
        if obj.is_actionable():
            return format_html('<span style="color: green;">✓ Yes</span>')
        return format_html('<span style="color: gray;">✗ No</span>')
    is_actionable_display.short_description = 'Actionable'


@admin.register(AlertAudit)
class AlertAuditAdmin(admin.ModelAdmin):
    """Admin interface for AlertAudit model."""

    list_display = [
        'alert',
        'action',
        'performed_by',
        'performed_at',
        'status_change',
        'ip_address',
    ]

    list_filter = [
        'action',
        'performed_at',
    ]

    search_fields = [
        'alert__id',
        'alert__patient_mrn',
        'performed_by__username',
        'action',
    ]

    readonly_fields = [
        'alert',
        'action',
        'performed_by',
        'performed_at',
        'old_status',
        'new_status',
        'details',
        'ip_address',
    ]

    date_hierarchy = 'performed_at'
    ordering = ['-performed_at']

    def status_change(self, obj):
        """Display status change."""
        if obj.old_status and obj.new_status:
            return f"{obj.old_status} → {obj.new_status}"
        return '-'
    status_change.short_description = 'Status Change'

    def has_add_permission(self, request):
        """Disable manual creation."""
        return False

    def has_change_permission(self, request, obj=None):
        """Make read-only."""
        return False
