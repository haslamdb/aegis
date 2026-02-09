from django.urls import path
from . import views

app_name = 'surgical_prophylaxis'

urlpatterns = [
    # Page views
    path('', views.dashboard, name='dashboard'),
    path('case/<uuid:pk>/', views.case_detail, name='case_detail'),
    path('compliance/', views.compliance, name='compliance'),
    path('realtime/', views.realtime, name='realtime'),
    path('help/', views.help_page, name='help'),

    # API endpoints
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/<uuid:pk>/acknowledge/', views.api_acknowledge, name='api_acknowledge'),
    path('api/<uuid:pk>/resolve/', views.api_resolve, name='api_resolve'),
    path('api/<uuid:pk>/add-note/', views.api_add_note, name='api_add_note'),
    path('api/export/', views.api_export, name='api_export'),
]
