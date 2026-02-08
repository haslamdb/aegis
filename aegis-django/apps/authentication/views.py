"""Authentication views for AEGIS Django."""

from django.contrib.auth import views as auth_views
from django.contrib.auth import logout
from django.shortcuts import redirect


class AegisLoginView(auth_views.LoginView):
    """Login view with AEGIS template."""
    template_name = 'authentication/login.html'


class AegisLogoutView(auth_views.LogoutView):
    """Logout view - redirects to login page."""
    next_page = '/auth/login/'
