from django.contrib import admin
from .models import OutbreakCluster, ClusterCase


class ClusterCaseInline(admin.TabularInline):
    model = ClusterCase
    extra = 0
    readonly_fields = ('id', 'source', 'source_id', 'patient_mrn', 'event_date',
                       'organism', 'infection_type', 'unit', 'added_at')


@admin.register(OutbreakCluster)
class OutbreakClusterAdmin(admin.ModelAdmin):
    list_display = ('infection_type', 'unit', 'case_count', 'severity', 'status',
                    'first_case_date', 'last_case_date', 'created_at')
    list_filter = ('status', 'severity', 'infection_type')
    search_fields = ('unit', 'organism', 'infection_type')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [ClusterCaseInline]


@admin.register(ClusterCase)
class ClusterCaseAdmin(admin.ModelAdmin):
    list_display = ('patient_mrn', 'source', 'infection_type', 'organism',
                    'unit', 'event_date', 'cluster')
    list_filter = ('source', 'infection_type')
    search_fields = ('patient_mrn', 'source_id', 'organism')
    readonly_fields = ('id', 'added_at')
