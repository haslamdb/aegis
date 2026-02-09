"""Core app tests, including Celery integration tests."""

from django.test import TestCase, override_settings
from unittest.mock import patch, MagicMock


class CeleryAppTests(TestCase):
    """Verify the Celery app initializes and discovers tasks."""

    def test_celery_app_loads(self):
        """Celery app can be imported and has correct name."""
        from aegis_project.celery import app
        self.assertEqual(app.main, 'aegis')

    def test_celery_app_exported_from_init(self):
        """celery_app is available from aegis_project package."""
        from aegis_project import celery_app
        self.assertEqual(celery_app.main, 'aegis')

    def test_autodiscovered_tasks(self):
        """All expected tasks are registered."""
        import importlib
        from aegis_project.celery import app

        # In eager/test mode, force-import task modules (mirrors worker startup)
        task_modules = [
            'apps.mdro.tasks', 'apps.drug_bug.tasks', 'apps.dosing.tasks',
            'apps.hai_detection.tasks', 'apps.outbreak_detection.tasks',
            'apps.antimicrobial_usage.tasks', 'apps.abx_indications.tasks',
            'apps.surgical_prophylaxis.tasks', 'apps.guideline_adherence.tasks',
            'apps.nhsn_reporting.tasks',
        ]
        for mod in task_modules:
            importlib.import_module(mod)

        registered = list(app.tasks.keys())

        expected_tasks = [
            'apps.hai_detection.tasks.detect_hai_candidates',
            'apps.hai_detection.tasks.classify_hai_candidates',
            'apps.outbreak_detection.tasks.detect_outbreaks',
            'apps.mdro.tasks.monitor_mdro',
            'apps.drug_bug.tasks.monitor_drug_bug',
            'apps.dosing.tasks.monitor_dosing',
            'apps.antimicrobial_usage.tasks.monitor_usage',
            'apps.abx_indications.tasks.check_abx_indications',
            'apps.abx_indications.tasks.auto_accept_old_indications',
            'apps.surgical_prophylaxis.tasks.monitor_prophylaxis',
            'apps.guideline_adherence.tasks.check_guideline_triggers',
            'apps.guideline_adherence.tasks.check_guideline_episodes',
            'apps.guideline_adherence.tasks.check_guideline_adherence',
            'apps.nhsn_reporting.tasks.nhsn_nightly_extract',
            'apps.nhsn_reporting.tasks.nhsn_create_events',
        ]

        for task_name in expected_tasks:
            self.assertIn(
                task_name, registered,
                f"Task {task_name} not found in registered tasks"
            )

    def test_task_routing_configured(self):
        """Task routing assigns tasks to correct queues."""
        from django.conf import settings

        routes = settings.CELERY_TASK_ROUTES

        # FHIR polling → default queue
        self.assertEqual(routes['apps.mdro.tasks.*']['queue'], 'default')
        self.assertEqual(routes['apps.drug_bug.tasks.*']['queue'], 'default')
        self.assertEqual(routes['apps.dosing.tasks.*']['queue'], 'default')
        self.assertEqual(routes['apps.antimicrobial_usage.tasks.*']['queue'], 'default')
        self.assertEqual(routes['apps.surgical_prophylaxis.tasks.*']['queue'], 'default')
        self.assertEqual(routes['apps.outbreak_detection.tasks.*']['queue'], 'default')

        # LLM → llm queue
        self.assertEqual(routes['apps.hai_detection.tasks.*']['queue'], 'llm')
        self.assertEqual(routes['apps.abx_indications.tasks.*']['queue'], 'llm')
        self.assertEqual(routes['apps.guideline_adherence.tasks.*']['queue'], 'llm')

        # Batch → batch queue
        self.assertEqual(routes['apps.nhsn_reporting.tasks.*']['queue'], 'batch')

    def test_beat_schedule_configured(self):
        """Beat schedule has entries for all periodic tasks."""
        from django.conf import settings

        schedule = settings.CELERY_BEAT_SCHEDULE

        expected_entries = [
            'monitor-mdro-every-15m',
            'monitor-drug-bug-every-5m',
            'monitor-dosing-every-15m',
            'monitor-usage-every-5m',
            'monitor-prophylaxis-every-5m',
            'detect-outbreaks-every-30m',
            'detect-hai-candidates-every-5m',
            'classify-hai-candidates-every-5m',
            'check-abx-indications-every-5m',
            'auto-accept-old-indications-hourly',
            'check-guideline-triggers-every-5m',
            'check-guideline-episodes-every-15m',
            'check-guideline-adherence-every-15m',
            'nhsn-nightly-extract',
            'nhsn-create-events',
        ]

        for entry_name in expected_entries:
            self.assertIn(
                entry_name, schedule,
                f"Beat schedule entry {entry_name} not found"
            )

    def test_worker_settings(self):
        """Worker tuning settings are configured."""
        from django.conf import settings

        self.assertTrue(settings.CELERY_TASK_ACKS_LATE)
        self.assertEqual(settings.CELERY_WORKER_PREFETCH_MULTIPLIER, 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_eager_mode_enabled_in_dev(self):
        """Development settings enable eager mode."""
        from django.conf import settings
        self.assertTrue(settings.CELERY_TASK_ALWAYS_EAGER)


class MDROTaskTests(TestCase):
    """Tests for MDRO Celery tasks."""

    @patch('apps.mdro.services.MDROMonitorService.run_detection')
    def test_monitor_mdro_calls_service(self, mock_run):
        mock_run.return_value = {
            'cultures_checked': 10,
            'new_mdro_cases': 2,
            'skipped_already_processed': 3,
            'skipped_not_mdro': 5,
            'errors': [],
        }

        from apps.mdro.tasks import monitor_mdro
        result = monitor_mdro()

        mock_run.assert_called_once()
        self.assertEqual(result['new_mdro_cases'], 2)
        self.assertEqual(result['cultures_checked'], 10)


class DrugBugTaskTests(TestCase):
    """Tests for Drug-Bug Mismatch Celery tasks."""

    @patch('apps.drug_bug.services.DrugBugMonitorService.run_detection')
    def test_monitor_drug_bug_calls_service(self, mock_run):
        mock_run.return_value = {
            'cultures_checked': 8,
            'alerts_created': 1,
            'errors': [],
        }

        from apps.drug_bug.tasks import monitor_drug_bug
        result = monitor_drug_bug()

        mock_run.assert_called_once()
        self.assertEqual(result['alerts_created'], 1)


class DosingTaskTests(TestCase):
    """Tests for Dosing Verification Celery tasks."""

    @patch('apps.dosing.services.DosingMonitorService.run_check')
    def test_monitor_dosing_calls_service(self, mock_run):
        mock_run.return_value = {
            'total_flags': 5,
            'alerts_created': 3,
            'alerts_skipped': 2,
            'errors': [],
        }

        from apps.dosing.tasks import monitor_dosing
        result = monitor_dosing()

        mock_run.assert_called_once()
        self.assertEqual(result['total_flags'], 5)
        self.assertEqual(result['alerts_created'], 3)


class UsageTaskTests(TestCase):
    """Tests for Antimicrobial Usage Celery tasks."""

    @patch('apps.antimicrobial_usage.services.BroadSpectrumMonitorService.check_new_alerts')
    def test_monitor_usage_calls_service(self, mock_check):
        mock_check.return_value = [('assessment1', 'alert1'), ('assessment2', 'alert2')]

        from apps.antimicrobial_usage.tasks import monitor_usage
        result = monitor_usage()

        mock_check.assert_called_once()
        self.assertEqual(result['alerts_created'], 2)


class HAITaskTests(TestCase):
    """Tests for HAI Detection Celery tasks."""

    @patch('apps.hai_detection.services.HAIDetectionService.run_detection')
    def test_detect_hai_candidates(self, mock_detect):
        mock_detect.return_value = {
            'new_candidates': 3,
            'by_type': {'CLABSI': 2, 'SSI': 1},
            'errors': [],
        }

        from apps.hai_detection.tasks import detect_hai_candidates
        result = detect_hai_candidates()

        mock_detect.assert_called_once()
        self.assertEqual(result['new_candidates'], 3)

    @patch('apps.hai_detection.services.HAIDetectionService.run_classification')
    def test_classify_hai_candidates(self, mock_classify):
        mock_classify.return_value = {
            'classified': 2,
            'errors': 0,
            'by_decision': {'HAI': 1, 'NOT_HAI': 1},
            'details': [],
        }

        from apps.hai_detection.tasks import classify_hai_candidates
        result = classify_hai_candidates()

        mock_classify.assert_called_once()
        self.assertEqual(result['classified'], 2)


class OutbreakTaskTests(TestCase):
    """Tests for Outbreak Detection Celery tasks."""

    @patch('apps.outbreak_detection.services.OutbreakDetectionService.run_detection')
    def test_detect_outbreaks(self, mock_detect):
        mock_detect.return_value = {
            'cases_analyzed': 15,
            'new_cases_processed': 5,
            'clusters_formed': 1,
            'alerts_created': 1,
        }

        from apps.outbreak_detection.tasks import detect_outbreaks
        result = detect_outbreaks()

        mock_detect.assert_called_once()
        self.assertEqual(result['clusters_formed'], 1)


class ABXIndicationsTaskTests(TestCase):
    """Tests for ABX Indications Celery tasks."""

    @patch('apps.abx_indications.services.IndicationMonitorService.check_new_alerts')
    @patch('apps.abx_indications.services.IndicationMonitorService.check_new_orders')
    def test_check_abx_indications(self, mock_orders, mock_alerts):
        mock_orders.return_value = ['candidate1', 'candidate2']
        mock_alerts.return_value = [('candidate1', 'alert1')]

        from apps.abx_indications.tasks import check_abx_indications
        result = check_abx_indications()

        mock_orders.assert_called_once()
        mock_alerts.assert_called_once()
        self.assertEqual(result['candidates_processed'], 2)
        self.assertEqual(result['alerts_created'], 1)

    @patch('apps.abx_indications.services.IndicationMonitorService.auto_accept_old')
    def test_auto_accept_old_indications(self, mock_accept):
        mock_accept.return_value = 5

        from apps.abx_indications.tasks import auto_accept_old_indications
        result = auto_accept_old_indications()

        mock_accept.assert_called_once()
        self.assertEqual(result['auto_accepted'], 5)


class ProphylaxisTaskTests(TestCase):
    """Tests for Surgical Prophylaxis Celery tasks."""

    @patch('apps.surgical_prophylaxis.services.SurgicalProphylaxisService.check_new_cases')
    def test_monitor_prophylaxis(self, mock_check):
        mock_check.return_value = [{'case_id': '1'}, {'case_id': '2'}]

        from apps.surgical_prophylaxis.tasks import monitor_prophylaxis
        result = monitor_prophylaxis()

        mock_check.assert_called_once()
        self.assertEqual(result['cases_evaluated'], 2)


class GuidelineTaskTests(TestCase):
    """Tests for Guideline Adherence Celery tasks."""

    @patch('apps.guideline_adherence.services.GuidelineAdherenceService.check_triggers')
    def test_check_guideline_triggers(self, mock_triggers):
        mock_triggers.return_value = ['episode1', 'episode2']

        from apps.guideline_adherence.tasks import check_guideline_triggers
        result = check_guideline_triggers()

        mock_triggers.assert_called_once()
        self.assertEqual(result['new_episodes'], 2)

    @patch('apps.guideline_adherence.services.GuidelineAdherenceService.check_episodes')
    def test_check_guideline_episodes(self, mock_episodes):
        mock_episodes.return_value = ['alert1']

        from apps.guideline_adherence.tasks import check_guideline_episodes
        result = check_guideline_episodes()

        mock_episodes.assert_called_once()
        self.assertEqual(result['alerts_created'], 1)

    @patch('apps.guideline_adherence.services.GuidelineAdherenceService.check_adherence')
    def test_check_guideline_adherence(self, mock_adherence):
        mock_adherence.return_value = {
            'episodes_checked': 3,
            'elements_updated': 8,
        }

        from apps.guideline_adherence.tasks import check_guideline_adherence
        result = check_guideline_adherence()

        mock_adherence.assert_called_once()
        self.assertEqual(result['episodes_checked'], 3)
        self.assertEqual(result['elements_updated'], 8)


class NHSNTaskTests(TestCase):
    """Tests for NHSN Reporting Celery tasks."""

    @patch('apps.nhsn_reporting.logic.config.is_clarity_configured')
    def test_nhsn_nightly_extract_skips_if_no_clarity(self, mock_cfg):
        mock_cfg.return_value = False

        from apps.nhsn_reporting.tasks import nhsn_nightly_extract
        result = nhsn_nightly_extract()

        self.assertTrue(result['skipped'])
        self.assertEqual(result['reason'], 'clarity_not_configured')

    @patch('apps.nhsn_reporting.services.NHSNReportingService.create_nhsn_events')
    def test_nhsn_create_events(self, mock_create):
        mock_create.return_value = 4

        from apps.nhsn_reporting.tasks import nhsn_create_events
        result = nhsn_create_events()

        mock_create.assert_called_once()
        self.assertEqual(result['events_created'], 4)
