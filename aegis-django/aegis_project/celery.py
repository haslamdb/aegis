"""
Celery application configuration for AEGIS.

Sets up the Celery app with Django settings integration and
autodiscovery of tasks across all AEGIS apps.
"""

import os

from celery import Celery

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aegis_project.settings.development')

app = Celery('aegis')

# Load config from Django settings, using CELERY_ namespace
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodiscover tasks.py in all installed apps
app.autodiscover_tasks()
