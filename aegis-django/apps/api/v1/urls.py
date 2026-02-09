"""
AEGIS API v1 URL configuration.

All module ViewSets are registered on a single DefaultRouter.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .alerts.views import AlertViewSet
from .hai.views import HAICandidateViewSet
from .outbreaks.views import OutbreakClusterViewSet
from .guidelines.views import GuidelineEpisodeViewSet
from .surgical.views import SurgicalCaseViewSet
from .indications.views import IndicationCandidateViewSet
from .nhsn.views import (
    NHSNEventViewSet,
    DenominatorMonthlyViewSet,
    AUMonthlySummaryViewSet,
    ARQuarterlySummaryViewSet,
    NHSNStatsViewSet,
)
from .auth.views import CurrentUserView, ObtainTokenView

router = DefaultRouter()
router.register(r'alerts', AlertViewSet)
router.register(r'hai/candidates', HAICandidateViewSet, basename='hai-candidate')
router.register(r'outbreaks/clusters', OutbreakClusterViewSet, basename='outbreak-cluster')
router.register(r'guidelines/episodes', GuidelineEpisodeViewSet, basename='guideline-episode')
router.register(r'surgical/cases', SurgicalCaseViewSet, basename='surgical-case')
router.register(r'indications/candidates', IndicationCandidateViewSet, basename='indication-candidate')
router.register(r'nhsn/events', NHSNEventViewSet, basename='nhsn-event')
router.register(r'nhsn/denominators', DenominatorMonthlyViewSet, basename='nhsn-denominator')
router.register(r'nhsn/au-summaries', AUMonthlySummaryViewSet, basename='nhsn-au-summary')
router.register(r'nhsn/ar-summaries', ARQuarterlySummaryViewSet, basename='nhsn-ar-summary')
router.register(r'nhsn/stats', NHSNStatsViewSet, basename='nhsn-stats')

app_name = 'api-v1'

urlpatterns = [
    path('', include(router.urls)),
    path('auth/me/', CurrentUserView.as_view(), name='auth-me'),
    path('auth/token/', ObtainTokenView.as_view(), name='auth-token'),
]
