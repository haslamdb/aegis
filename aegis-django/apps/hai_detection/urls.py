"""URL configuration for HAI Detection module."""

from django.urls import path

from . import views

app_name = 'hai_detection'

urlpatterns = [
    # Page views
    path('', views.dashboard, name='dashboard'),
    path('candidates/<uuid:candidate_id>/', views.candidate_detail, name='candidate_detail'),
    path('history/', views.history, name='history'),
    path('reports/', views.reports, name='reports'),
    path('help/', views.help_page, name='help'),

    # API endpoints
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/candidates/', views.api_candidates, name='api_candidates'),
    path('api/candidates/<uuid:candidate_id>/review/', views.api_submit_review, name='api_submit_review'),
    path('api/override-stats/', views.api_override_stats, name='api_override_stats'),
    path('api/recent-overrides/', views.api_recent_overrides, name='api_recent_overrides'),
]
