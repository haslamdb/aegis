from django.urls import path
from . import views

app_name = 'outbreak_detection'

urlpatterns = [
    # Page views
    path('', views.dashboard, name='dashboard'),
    path('clusters/', views.clusters_list, name='clusters_list'),
    path('clusters/<uuid:cluster_id>/', views.cluster_detail, name='cluster_detail'),
    path('clusters/<uuid:cluster_id>/status/', views.update_cluster_status, name='update_cluster_status'),
    path('alerts/', views.alerts_list, name='alerts_list'),
    path('alerts/<uuid:alert_id>/acknowledge/', views.acknowledge_alert, name='acknowledge_alert'),
    path('help/', views.help_page, name='help'),

    # API endpoints
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/active-clusters/', views.api_active_clusters, name='api_active_clusters'),
]
