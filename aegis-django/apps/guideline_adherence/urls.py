"""Guideline Adherence - URL Configuration."""

from django.urls import path
from . import views

app_name = 'guideline_adherence'

urlpatterns = [
    # Dashboard views
    path('', views.dashboard, name='dashboard'),
    path('active/', views.active_episodes, name='active_episodes'),
    path('episode/<uuid:pk>/', views.episode_detail, name='episode_detail'),
    path('bundle/<str:bundle_id>/', views.bundle_detail, name='bundle_detail'),
    path('metrics/', views.metrics, name='metrics'),
    path('history/', views.history, name='history'),
    path('help/', views.help_page, name='help'),

    # API endpoints
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/episode/<uuid:pk>/review/', views.api_review, name='api_review'),
    path('api/<uuid:pk>/acknowledge/', views.api_acknowledge, name='api_acknowledge'),
    path('api/<uuid:pk>/resolve/', views.api_resolve, name='api_resolve'),
    path('api/export/', views.api_export, name='api_export'),
]
