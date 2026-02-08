"""
MDRO Surveillance - URL Configuration
"""

from django.urls import path
from . import views

app_name = 'mdro'

urlpatterns = [
    # Dashboard views
    path('', views.dashboard, name='dashboard'),
    path('cases/', views.cases_list, name='cases'),
    path('cases/<uuid:case_id>/', views.case_detail, name='case_detail'),
    path('cases/<uuid:case_id>/review/', views.review_case, name='review_case'),
    path('analytics/', views.analytics, name='analytics'),
    path('help/', views.help_page, name='help'),

    # API endpoints
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/export/', views.api_export, name='api_export'),
]
