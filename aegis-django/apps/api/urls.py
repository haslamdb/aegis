"""
Root URL configuration for AEGIS API.

Provides:
- /api/schema/ — OpenAPI 3.0 schema (YAML)
- /api/docs/  — Swagger UI
- /api/v1/    — Versioned API endpoints
"""

from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path('schema/', SpectacularAPIView.as_view(), name='api-schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='api-schema'), name='api-docs'),
    path('v1/', include('apps.api.v1.urls')),
]
