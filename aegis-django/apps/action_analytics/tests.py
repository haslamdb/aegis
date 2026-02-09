"""Tests for Action Analytics module."""

from datetime import date, timedelta

from django.test import TestCase, RequestFactory
from django.urls import reverse, resolve
from django.utils import timezone

from apps.authentication.models import User, UserRole
from apps.metrics.models import ProviderActivity, DailySnapshot
from apps.alerts.models import Alert, AlertType
from .analytics import ActionAnalyzer
from . import views


class ActionAnalyzerOverviewTests(TestCase):
    """Test ActionAnalyzer.get_overview() with real DB data."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='pharm_analyst', email='pharm@test.com',
            password='testpass123', role=UserRole.ASP_PHARMACIST,
        )

    def setUp(self):
        self.end = timezone.now().date()
        self.start = self.end - timedelta(days=30)

    def test_overview_empty_database(self):
        analyzer = ActionAnalyzer(self.start, self.end)
        data = analyzer.get_overview()
        self.assertEqual(data['total_actions'], 0)
        self.assertEqual(data['unique_patients'], 0)
        self.assertEqual(data['avg_duration_seconds'], 0)
        self.assertIn('date_range', data)

    def test_overview_counts_activities(self):
        ProviderActivity.objects.create(
            user=self.user, action_type='review', module='hai',
            patient_mrn='MRN001', duration_seconds=120,
        )
        ProviderActivity.objects.create(
            user=self.user, action_type='review', module='mdro',
            patient_mrn='MRN002', duration_seconds=60,
        )
        analyzer = ActionAnalyzer(self.start, self.end)
        data = analyzer.get_overview()
        self.assertEqual(data['total_actions'], 2)
        self.assertEqual(data['unique_patients'], 2)

    def test_overview_avg_duration(self):
        ProviderActivity.objects.create(
            user=self.user, action_type='review', module='hai',
            patient_mrn='MRN001', duration_seconds=100,
        )
        ProviderActivity.objects.create(
            user=self.user, action_type='review', module='hai',
            patient_mrn='MRN002', duration_seconds=200,
        )
        analyzer = ActionAnalyzer(self.start, self.end)
        data = analyzer.get_overview()
        self.assertEqual(data['avg_duration_seconds'], 150.0)

    def test_overview_returns_expected_keys(self):
        analyzer = ActionAnalyzer(self.start, self.end)
        data = analyzer.get_overview()
        expected_keys = {
            'total_actions', 'unique_patients', 'avg_duration_seconds',
            'by_module', 'by_user', 'date_range',
        }
        self.assertEqual(set(data.keys()), expected_keys)


class ActionAnalyzerByModuleTests(TestCase):
    """Test ActionAnalyzer.get_actions_by_module()."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='pharm2', email='pharm2@test.com',
            password='testpass123', role=UserRole.ASP_PHARMACIST,
        )
        ProviderActivity.objects.create(
            user=cls.user, action_type='review', module='hai',
            patient_mrn='MRN001', duration_seconds=100,
        )
        ProviderActivity.objects.create(
            user=cls.user, action_type='resolve', module='hai',
            patient_mrn='MRN002', duration_seconds=50,
        )
        ProviderActivity.objects.create(
            user=cls.user, action_type='review', module='mdro',
            patient_mrn='MRN003', duration_seconds=80,
        )

    def test_groups_by_module(self):
        end = timezone.now().date()
        start = end - timedelta(days=30)
        analyzer = ActionAnalyzer(start, end)
        data = analyzer.get_actions_by_module()
        modules = {d['module'] for d in data}
        self.assertIn('hai', modules)
        self.assertIn('mdro', modules)

    def test_module_counts_correct(self):
        end = timezone.now().date()
        start = end - timedelta(days=30)
        analyzer = ActionAnalyzer(start, end)
        data = analyzer.get_actions_by_module()
        hai_data = [d for d in data if d['module'] == 'hai'][0]
        self.assertEqual(hai_data['count'], 2)


class ActionAnalyzerTimeSpentTests(TestCase):
    """Test ActionAnalyzer.get_time_spent_analysis()."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='pharm3', email='pharm3@test.com',
            password='testpass123', role=UserRole.ASP_PHARMACIST,
        )
        ProviderActivity.objects.create(
            user=cls.user, action_type='review', module='hai',
            duration_seconds=300,
        )

    def test_time_spent_returns_expected_keys(self):
        end = timezone.now().date()
        start = end - timedelta(days=30)
        analyzer = ActionAnalyzer(start, end)
        data = analyzer.get_time_spent_analysis()
        self.assertIn('by_module', data)
        self.assertIn('total_time_seconds', data)

    def test_total_time_correct(self):
        end = timezone.now().date()
        start = end - timedelta(days=30)
        analyzer = ActionAnalyzer(start, end)
        data = analyzer.get_time_spent_analysis()
        self.assertEqual(data['total_time_seconds'], 300)


class ActionAnalyzerProductivityTests(TestCase):
    """Test ActionAnalyzer.get_user_productivity()."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='pharm4', email='pharm4@test.com',
            password='testpass123', role=UserRole.ASP_PHARMACIST,
            first_name='Test', last_name='Pharm',
        )
        ProviderActivity.objects.create(
            user=cls.user, action_type='review', module='hai',
            patient_mrn='MRN001', duration_seconds=120,
        )

    def test_productivity_includes_user_info(self):
        end = timezone.now().date()
        start = end - timedelta(days=30)
        analyzer = ActionAnalyzer(start, end)
        data = analyzer.get_user_productivity()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['user__username'], 'pharm4')
        self.assertEqual(data[0]['total_actions'], 1)


class ActionAnalyzerDateFilterTests(TestCase):
    """Test that date range filtering works correctly."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='pharm5', email='pharm5@test.com',
            password='testpass123', role=UserRole.ASP_PHARMACIST,
        )
        ProviderActivity.objects.create(
            user=cls.user, action_type='review', module='hai',
            duration_seconds=100,
        )

    def test_excludes_activities_outside_range(self):
        # Use a date range in the past that excludes today's data
        end = (timezone.now() - timedelta(days=60)).date()
        start = end - timedelta(days=30)
        analyzer = ActionAnalyzer(start, end)
        data = analyzer.get_overview()
        self.assertEqual(data['total_actions'], 0)

    def test_default_date_range(self):
        analyzer = ActionAnalyzer()
        data = analyzer.get_overview()
        self.assertEqual(data['total_actions'], 1)


class ActionAnalyticsURLTests(TestCase):
    """Verify URL routing for action_analytics views."""

    def test_overview_url_resolves(self):
        url = reverse('action_analytics:overview')
        self.assertEqual(resolve(url).func, views.overview)

    def test_by_module_url_resolves(self):
        url = reverse('action_analytics:by_module')
        self.assertEqual(resolve(url).func, views.by_module)

    def test_time_spent_url_resolves(self):
        url = reverse('action_analytics:time_spent')
        self.assertEqual(resolve(url).func, views.time_spent)

    def test_productivity_url_resolves(self):
        url = reverse('action_analytics:productivity')
        self.assertEqual(resolve(url).func, views.productivity)

    def test_api_overview_url_resolves(self):
        url = reverse('action_analytics:api_overview')
        self.assertEqual(resolve(url).func, views.api_overview)


class GetDaysParamTests(TestCase):
    """Test the _get_days_param helper."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_default_is_30(self):
        request = self.factory.get('/')
        self.assertEqual(views._get_days_param(request), 30)

    def test_custom_days(self):
        request = self.factory.get('/', {'days': '7'})
        self.assertEqual(views._get_days_param(request), 7)

    def test_clamps_minimum_to_1(self):
        request = self.factory.get('/', {'days': '0'})
        self.assertEqual(views._get_days_param(request), 1)

    def test_clamps_maximum_to_365(self):
        request = self.factory.get('/', {'days': '999'})
        self.assertEqual(views._get_days_param(request), 365)

    def test_invalid_value_returns_default(self):
        request = self.factory.get('/', {'days': 'abc'})
        self.assertEqual(views._get_days_param(request), 30)
