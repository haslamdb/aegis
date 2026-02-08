"""URL routing for Action Analytics."""

from django.urls import path
from . import views

app_name = 'action_analytics'

urlpatterns = [
    # Dashboard pages
    path('', views.overview, name='overview'),
    path('by-module/', views.by_module, name='by_module'),
    path('time-spent/', views.time_spent, name='time_spent'),
    path('productivity/', views.productivity, name='productivity'),
    
    # JSON API endpoints
    path('api/overview/', views.api_overview, name='api_overview'),
    path('api/by-module/', views.api_by_module, name='api_by_module'),
    path('api/time-spent/', views.api_time_spent, name='api_time_spent'),
    path('api/productivity/', views.api_productivity, name='api_productivity'),
]
