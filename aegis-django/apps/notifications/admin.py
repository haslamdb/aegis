"""Notifications admin."""
from django.contrib import admin
from .models import NotificationLog

@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'channel', 'recipient', 'status', 'sent_at', 'delivered_at']
    list_filter = ['channel', 'status', 'created_at']
    search_fields = ['recipient', 'alert__patient_mrn']
    readonly_fields = ['id', 'created_at', 'updated_at', 'sent_at', 'delivered_at']
