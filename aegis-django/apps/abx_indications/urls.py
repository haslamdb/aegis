"""ABX Indication Monitoring - URL Configuration."""

from django.urls import path
from . import views

app_name = 'abx_indications'

urlpatterns = [
    # Dashboard views
    path('', views.dashboard, name='dashboard'),
    path('candidate/<uuid:pk>/', views.candidate_detail, name='detail'),
    path('history/', views.history, name='history'),
    path('help/', views.help_page, name='help'),

    # API endpoints
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/<uuid:pk>/review/', views.api_review, name='api_review'),
    path('api/<uuid:pk>/acknowledge/', views.api_acknowledge, name='api_acknowledge'),
    path('api/<uuid:pk>/resolve/', views.api_resolve, name='api_resolve'),
    path('api/<uuid:pk>/add-note/', views.api_add_note, name='api_add_note'),

    # CSV export
    path('api/export/', views.api_export, name='api_export'),
]
