from django.urls import path

from . import views

app_name = 'nhsn_reporting'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Detail views
    path('au/', views.au_detail, name='au_detail'),
    path('ar/', views.ar_detail, name='ar_detail'),
    path('hai/', views.hai_events, name='hai_events'),
    path('denominators/', views.denominators, name='denominators'),
    path('submission/', views.submission, name='submission'),
    path('help/', views.help_page, name='help'),

    # API endpoints
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/au/export/', views.api_au_export, name='api_au_export'),
    path('api/ar/export/', views.api_ar_export, name='api_ar_export'),
    path('api/hai/export/', views.api_hai_export, name='api_hai_export'),
    path('api/hai/mark-submitted/', views.api_mark_submitted, name='api_mark_submitted'),
    path('api/hai/direct/', views.api_direct_submit, name='api_direct_submit'),
    path('api/hai/test-direct/', views.api_test_direct, name='api_test_direct'),
]
