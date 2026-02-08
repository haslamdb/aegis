"""Authentication URL configuration."""

from django.urls import path
from . import views

app_name = 'authentication'

urlpatterns = [
    path('login/', views.AegisLoginView.as_view(), name='login'),
    path('logout/', views.AegisLogoutView.as_view(), name='logout'),
]
