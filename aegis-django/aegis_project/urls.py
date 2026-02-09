"""
URL configuration for aegis_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication
    path('auth/', include('apps.authentication.urls')),

    # AEGIS modules
    path('action-analytics/', include('apps.action_analytics.urls')),
    path('asp-alerts/', include('apps.asp_alerts.urls')),
    path('mdro-surveillance/', include('apps.mdro.urls')),
    path('drug-bug/', include('apps.drug_bug.urls')),
    path('dosing/', include('apps.dosing.urls')),
    path('hai-detection/', include('apps.hai_detection.urls')),
    path('outbreak-detection/', include('apps.outbreak_detection.urls')),
    path('antimicrobial-usage/', include('apps.antimicrobial_usage.urls')),
    path('abx-indications/', include('apps.abx_indications.urls')),
    path('surgical-prophylaxis/', include('apps.surgical_prophylaxis.urls')),
]
