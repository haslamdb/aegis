"""Create demo guideline adherence episodes for development and testing.

Creates 5 realistic CCHMC scenarios with BundleEpisode + ElementResult records.

Usage:
    python manage.py create_demo_guidelines
    python manage.py create_demo_guidelines --clear
    python manage.py create_demo_guidelines --count 3
"""

import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity
from apps.guideline_adherence.bundles import get_bundle
from apps.guideline_adherence.models import (
    BundleEpisode, ElementResult,
    EpisodeStatus, ElementCheckStatus, AdherenceLevel,
)


class Command(BaseCommand):
    help = 'Create demo guideline adherence episodes with CCHMC scenarios'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear existing demo data first',
        )
        parser.add_argument(
            '--count', type=int, default=5,
            help='Number of scenarios to create (default: 5, max: 5)',
        )

    def handle(self, *args, **options):
        now = timezone.now()

        if options['clear']:
            self.stdout.write('Clearing existing guideline adherence demo data...')
            # Find demo episodes by MRN prefix
            demo_episodes = BundleEpisode.objects.filter(
                patient_mrn__startswith='GA-DEMO-',
            )
            # Delete associated alerts
            demo_episode_ids = list(demo_episodes.values_list('id', flat=True))
            Alert.objects.filter(
                source_module='guideline_adherence',
                source_id__in=[str(eid) for eid in demo_episode_ids],
            ).delete()
            # Delete episodes (cascades to ElementResult)
            demo_episodes.delete()
            self.stdout.write(self.style.SUCCESS('Cleared.'))

        scenarios = self._get_scenarios(now)
        count = min(options['count'], len(scenarios))
        created = 0

        for scenario in scenarios[:count]:
            episode = self._create_episode(scenario, now)
            self._create_elements(episode, scenario)

            # Calculate adherence
            episode.calculate_adherence()

            # Override adherence level if specified
            if scenario.get('adherence_level'):
                episode.adherence_level = scenario['adherence_level']
                episode.save(update_fields=['adherence_level', 'updated_at'])

            # Create alerts if specified
            if scenario.get('alerts'):
                self._create_alerts(episode, scenario)

            created += 1

            # Status display
            level_display = episode.get_adherence_level_display()
            if episode.adherence_level == AdherenceLevel.FULL:
                style = self.style.SUCCESS
            elif episode.adherence_level == AdherenceLevel.PARTIAL:
                style = self.style.WARNING
            else:
                style = self.style.ERROR

            alert_count = len(scenario.get('alerts', []))
            alert_str = f' ({alert_count} alerts)' if alert_count else ''

            self.stdout.write(style(
                f'  [{level_display}] {scenario["bundle_name"]} - '
                f'{scenario["patient_name"]} ({scenario["patient_mrn"]}) '
                f'@ {scenario["patient_unit"]} - '
                f'{episode.adherence_percentage}% adherence{alert_str}'
            ))

        self.stdout.write(self.style.SUCCESS(
            f'\nCreated {created} demo guideline adherence episodes'
        ))

    def _get_scenarios(self, now):
        """Define the 5 demo scenarios."""
        return [
            # ============================================================
            # 1. Febrile Infant well-appearing (14d) - 100% compliant
            # ============================================================
            {
                'bundle_id': 'febrile_infant_2024',
                'bundle_name': 'Febrile Infant (8-60 days)',
                'patient_id': f'fhir-patient-ga-001-{uuid.uuid4().hex[:8]}',
                'patient_mrn': 'GA-DEMO-001',
                'patient_name': 'Baby Garcia',
                'encounter_id': f'enc-ga-001-{uuid.uuid4().hex[:8]}',
                'patient_unit': 'G4NE - NICU',
                'trigger_type': 'diagnosis',
                'trigger_code': 'R50.9',
                'trigger_description': 'Fever, unspecified in 14-day-old neonate',
                'trigger_time': now - timedelta(hours=6),
                'patient_age_days': 14,
                'patient_age_months': 0.46,
                'status': EpisodeStatus.COMPLETE,
                'adherence_level': AdherenceLevel.FULL,
                'clinical_context': {
                    'appearance': 'well-appearing',
                    'temp_max': 38.3,
                    'birth_history': 'Term, uncomplicated vaginal delivery',
                },
                'elements': [
                    # All 14 elements MET for a well-appearing 14-day infant
                    {'element_id': 'fi_ua', 'status': ElementCheckStatus.MET,
                     'value': 'Negative', 'notes': 'Catheterized specimen, no pyuria'},
                    {'element_id': 'fi_blood_cx', 'status': ElementCheckStatus.MET,
                     'value': 'Drawn', 'notes': 'Blood culture obtained prior to antibiotics'},
                    {'element_id': 'fi_inflammatory_markers', 'status': ElementCheckStatus.MET,
                     'value': 'ANC 4200, CRP 0.3', 'notes': 'Inflammatory markers within normal limits'},
                    {'element_id': 'fi_procalcitonin', 'status': ElementCheckStatus.MET,
                     'value': 'PCT 0.12 ng/mL', 'notes': 'Procalcitonin normal (<0.5)'},
                    {'element_id': 'fi_lp', 'status': ElementCheckStatus.MET,
                     'value': 'CSF: WBC 2, RBC 0, protein 45, glucose 55',
                     'notes': 'LP performed per guideline (age 8-21 days requires LP)'},
                    {'element_id': 'fi_urine_cx', 'status': ElementCheckStatus.MET,
                     'value': 'Sent', 'notes': 'Urine culture obtained from catheterized specimen'},
                    {'element_id': 'fi_parenteral_abx', 'status': ElementCheckStatus.MET,
                     'value': 'Ampicillin + Gentamicin', 'notes': 'Parenteral antibiotics initiated per age 8-21d guideline'},
                    {'element_id': 'fi_hsv_risk', 'status': ElementCheckStatus.MET,
                     'value': 'Low risk', 'notes': 'No maternal HSV history, no vesicles, well-appearing'},
                    {'element_id': 'fi_acyclovir', 'status': ElementCheckStatus.NOT_APPLICABLE,
                     'value': '', 'notes': 'Acyclovir not indicated - no HSV risk factors'},
                    {'element_id': 'fi_clinical_impression', 'status': ElementCheckStatus.MET,
                     'value': 'Well-appearing', 'notes': 'Documented well-appearing febrile neonate'},
                    {'element_id': 'fi_admission', 'status': ElementCheckStatus.MET,
                     'value': 'Admitted to NICU', 'notes': 'Admitted per guideline (age 8-21 days)'},
                    {'element_id': 'fi_repeat_im', 'status': ElementCheckStatus.NOT_APPLICABLE,
                     'value': '', 'notes': 'Initial inflammatory markers normal, repeat not needed'},
                    {'element_id': 'fi_safe_discharge', 'status': ElementCheckStatus.NOT_APPLICABLE,
                     'value': '', 'notes': 'Still admitted, discharge checklist deferred'},
                    {'element_id': 'fi_disposition', 'status': ElementCheckStatus.MET,
                     'value': 'Admit NICU, pending cultures 36-48h',
                     'notes': 'Disposition documented with plan'},
                ],
                'alerts': [],
            },

            # ============================================================
            # 2. Pediatric Sepsis (3y) - 66% compliant, 2 alerts
            # ============================================================
            {
                'bundle_id': 'sepsis_peds_2024',
                'bundle_name': 'Pediatric Sepsis Bundle',
                'patient_id': f'fhir-patient-ga-002-{uuid.uuid4().hex[:8]}',
                'patient_mrn': 'GA-DEMO-002',
                'patient_name': 'Aiden Wilson',
                'encounter_id': f'enc-ga-002-{uuid.uuid4().hex[:8]}',
                'patient_unit': 'G3NE - PICU',
                'trigger_type': 'diagnosis',
                'trigger_code': 'A41.9',
                'trigger_description': 'Sepsis, unspecified organism',
                'trigger_time': now - timedelta(hours=4),
                'patient_age_days': 1095,  # ~3 years
                'patient_age_months': 36.0,
                'status': EpisodeStatus.ACTIVE,
                'adherence_level': AdherenceLevel.PARTIAL,
                'clinical_context': {
                    'appearance': 'ill-appearing',
                    'temp_max': 40.1,
                    'hr': 178,
                    'sbp': 68,
                    'presenting_complaint': 'Fever, lethargy, poor perfusion',
                },
                'elements': [
                    {'element_id': 'sepsis_blood_cx', 'status': ElementCheckStatus.MET,
                     'value': 'Drawn at 14:32', 'notes': 'Blood culture obtained before antibiotics'},
                    {'element_id': 'sepsis_lactate', 'status': ElementCheckStatus.MET,
                     'value': '4.2 mmol/L', 'notes': 'Elevated lactate, indicates tissue hypoperfusion'},
                    {'element_id': 'sepsis_abx_1hr', 'status': ElementCheckStatus.NOT_MET,
                     'value': 'Cefepime given at 15:48 (76 min)',
                     'notes': 'Antibiotics administered 76 minutes after recognition - exceeded 1-hour window'},
                    {'element_id': 'sepsis_fluid_bolus', 'status': ElementCheckStatus.MET,
                     'value': '20 mL/kg NS at 14:40',
                     'notes': 'Appropriate fluid bolus given for hypotension'},
                    {'element_id': 'sepsis_repeat_lactate', 'status': ElementCheckStatus.NOT_MET,
                     'value': '', 'notes': 'Repeat lactate not obtained within 6 hours of elevated initial'},
                    {'element_id': 'sepsis_reassess_48h', 'status': ElementCheckStatus.PENDING,
                     'value': '', 'notes': 'Pending - 48-hour reassessment not yet due'},
                ],
                'alerts': [
                    {
                        'alert_type': AlertType.BUNDLE_INCOMPLETE,
                        'severity': AlertSeverity.HIGH,
                        'title': 'Pediatric Sepsis Bundle: Antibiotics Within 1 Hour',
                        'summary': 'Antibiotics delayed >1 hour for sepsis - Aiden Wilson (GA-DEMO-002)',
                        'element_id': 'sepsis_abx_1hr',
                        'element_name': 'Antibiotics Within 1 Hour',
                        'message': 'Overdue: Antibiotics Within 1 Hour for Pediatric Sepsis Bundle '
                                   '(cefepime given at 76 min, target <60 min)',
                    },
                    {
                        'alert_type': AlertType.BUNDLE_INCOMPLETE,
                        'severity': AlertSeverity.HIGH,
                        'title': 'Pediatric Sepsis Bundle: Repeat Lactate',
                        'summary': 'Repeat lactate not obtained - initial 4.2 mmol/L - Aiden Wilson',
                        'element_id': 'sepsis_repeat_lactate',
                        'element_name': 'Repeat Lactate (if elevated)',
                        'message': 'Overdue: Repeat Lactate for Pediatric Sepsis Bundle '
                                   '(initial lactate 4.2 mmol/L, repeat not obtained within 6h window)',
                    },
                ],
            },

            # ============================================================
            # 3. Neonatal HSV (10d) - 71% compliant, 1 critical alert
            # ============================================================
            {
                'bundle_id': 'neonatal_hsv_2024',
                'bundle_name': 'Neonatal HSV',
                'patient_id': f'fhir-patient-ga-003-{uuid.uuid4().hex[:8]}',
                'patient_mrn': 'GA-DEMO-003',
                'patient_name': 'Baby Chen',
                'encounter_id': f'enc-ga-003-{uuid.uuid4().hex[:8]}',
                'patient_unit': 'G1NE - NICU',
                'trigger_type': 'diagnosis',
                'trigger_code': 'P35.2',
                'trigger_description': 'Congenital herpes simplex infection',
                'trigger_time': now - timedelta(hours=3),
                'patient_age_days': 10,
                'patient_age_months': 0.33,
                'status': EpisodeStatus.ACTIVE,
                'adherence_level': AdherenceLevel.PARTIAL,
                'clinical_context': {
                    'appearance': 'ill-appearing',
                    'temp_max': 38.6,
                    'vesicles': True,
                    'maternal_hsv': 'unknown',
                    'seizures': False,
                },
                'elements': [
                    {'element_id': 'hsv_csf_pcr', 'status': ElementCheckStatus.MET,
                     'value': 'Sent', 'notes': 'CSF HSV PCR sent, results pending'},
                    {'element_id': 'hsv_surface_cultures', 'status': ElementCheckStatus.MET,
                     'value': 'Skin, eye, mouth swabs sent',
                     'notes': 'SEM cultures obtained per protocol'},
                    {'element_id': 'hsv_blood_pcr', 'status': ElementCheckStatus.MET,
                     'value': 'Sent', 'notes': 'Blood HSV PCR sent, results pending'},
                    {'element_id': 'hsv_lfts', 'status': ElementCheckStatus.MET,
                     'value': 'ALT 42, AST 38', 'notes': 'LFTs mildly elevated, monitoring'},
                    {'element_id': 'hsv_acyclovir_started', 'status': ElementCheckStatus.NOT_MET,
                     'value': 'Started at 82 min post-recognition',
                     'notes': 'IV acyclovir initiated >1 hour after recognition (target <1h)'},
                    {'element_id': 'hsv_acyclovir_dose', 'status': ElementCheckStatus.PENDING,
                     'value': '', 'notes': 'Pending dose verification (20 mg/kg IV Q8H)'},
                    {'element_id': 'hsv_id_consult', 'status': ElementCheckStatus.MET,
                     'value': 'ID consult placed',
                     'notes': 'Infectious Disease consultation ordered within 2 hours'},
                    {'element_id': 'hsv_ophthalmology', 'status': ElementCheckStatus.MET,
                     'value': 'Ophtho consult placed',
                     'notes': 'Ophthalmology consult ordered due to vesicles near eye'},
                    {'element_id': 'hsv_neuroimaging', 'status': ElementCheckStatus.MET,
                     'value': 'MRI scheduled',
                     'notes': 'Brain MRI ordered, pending scheduling'},
                    {'element_id': 'hsv_treatment_duration', 'status': ElementCheckStatus.PENDING,
                     'value': '', 'notes': 'Treatment duration to be determined by disease classification'},
                    {'element_id': 'hsv_suppressive', 'status': ElementCheckStatus.MET,
                     'value': 'Plan documented',
                     'notes': 'Suppressive therapy plan documented in treatment notes'},
                ],
                'alerts': [
                    {
                        'alert_type': AlertType.GUIDELINE_ADHERENCE,
                        'severity': AlertSeverity.CRITICAL,
                        'title': 'Neonatal HSV: Acyclovir Started',
                        'summary': 'CRITICAL: Acyclovir delayed >1 hour - Baby Chen (GA-DEMO-003)',
                        'element_id': 'hsv_acyclovir_started',
                        'element_name': 'Acyclovir Started',
                        'message': 'CRITICAL: IV acyclovir initiated 82 minutes after HSV recognition '
                                   '(target <1 hour). Delayed treatment in neonatal HSV increases '
                                   'morbidity and mortality risk.',
                    },
                ],
            },

            # ============================================================
            # 4. Febrile Infant ill-appearing (10d) - 100% compliant
            # ============================================================
            {
                'bundle_id': 'febrile_infant_2024',
                'bundle_name': 'Febrile Infant (8-60 days)',
                'patient_id': f'fhir-patient-ga-004-{uuid.uuid4().hex[:8]}',
                'patient_mrn': 'GA-DEMO-004',
                'patient_name': 'Baby Thompson',
                'encounter_id': f'enc-ga-004-{uuid.uuid4().hex[:8]}',
                'patient_unit': 'A6N - Hospital Medicine',
                'trigger_type': 'diagnosis',
                'trigger_code': 'R50.9',
                'trigger_description': 'Fever, unspecified in 10-day-old neonate (ill-appearing)',
                'trigger_time': now - timedelta(hours=2),
                'patient_age_days': 10,
                'patient_age_months': 0.33,
                'status': EpisodeStatus.ACTIVE,
                'adherence_level': AdherenceLevel.FULL,
                'clinical_context': {
                    'appearance': 'ill-appearing',
                    'is_ill_appearing': True,
                    'temp_max': 39.1,
                    'hr': 195,
                    'rr': 62,
                    'concern': 'Irritable, poor feeding, mottled skin',
                },
                'elements': [
                    {'element_id': 'fi_ua', 'status': ElementCheckStatus.MET,
                     'value': 'WBC >10/hpf', 'notes': 'Catheterized specimen, pyuria present'},
                    {'element_id': 'fi_blood_cx', 'status': ElementCheckStatus.MET,
                     'value': 'Drawn', 'notes': 'Blood culture obtained'},
                    {'element_id': 'fi_inflammatory_markers', 'status': ElementCheckStatus.MET,
                     'value': 'ANC 12400, CRP 4.8', 'notes': 'Elevated inflammatory markers'},
                    {'element_id': 'fi_procalcitonin', 'status': ElementCheckStatus.MET,
                     'value': 'PCT 2.1 ng/mL', 'notes': 'Procalcitonin elevated (>0.5)'},
                    {'element_id': 'fi_lp', 'status': ElementCheckStatus.MET,
                     'value': 'CSF: WBC 0, RBC 1, protein 52, glucose 48',
                     'notes': 'LP performed per guideline (age 8-21 days, ill-appearing)'},
                    {'element_id': 'fi_urine_cx', 'status': ElementCheckStatus.MET,
                     'value': 'Sent', 'notes': 'Urine culture from catheterized specimen'},
                    {'element_id': 'fi_parenteral_abx', 'status': ElementCheckStatus.MET,
                     'value': 'Ampicillin + Cefotaxime',
                     'notes': 'Parenteral antibiotics for ill-appearing neonate with elevated IMs'},
                    {'element_id': 'fi_hsv_risk', 'status': ElementCheckStatus.MET,
                     'value': 'Moderate risk - ill-appearing',
                     'notes': 'HSV risk assessed: ill-appearing triggers acyclovir consideration'},
                    {'element_id': 'fi_acyclovir', 'status': ElementCheckStatus.MET,
                     'value': 'Acyclovir started',
                     'notes': 'Acyclovir initiated for ill-appearing febrile neonate <21 days'},
                    {'element_id': 'fi_clinical_impression', 'status': ElementCheckStatus.MET,
                     'value': 'Ill-appearing',
                     'notes': 'Documented ill-appearing: irritable, mottled, poor feeding'},
                    {'element_id': 'fi_admission', 'status': ElementCheckStatus.MET,
                     'value': 'Admitted to Hospital Medicine',
                     'notes': 'Appropriate admission for ill-appearing febrile neonate'},
                    {'element_id': 'fi_repeat_im', 'status': ElementCheckStatus.PENDING,
                     'value': '', 'notes': 'Repeat inflammatory markers planned at 24 hours'},
                    {'element_id': 'fi_safe_discharge', 'status': ElementCheckStatus.NOT_APPLICABLE,
                     'value': '', 'notes': 'Not applicable - admitted, ill-appearing'},
                    {'element_id': 'fi_disposition', 'status': ElementCheckStatus.MET,
                     'value': 'Admit, full sepsis workup, IV abx + acyclovir',
                     'notes': 'Appropriate escalated disposition for ill-appearing infant'},
                ],
                'alerts': [],
            },

            # ============================================================
            # 5. C.diff Testing (8y) - 100% testing appropriate
            # ============================================================
            {
                'bundle_id': 'cdiff_testing_2024',
                'bundle_name': 'C. difficile Testing Stewardship',
                'patient_id': f'fhir-patient-ga-005-{uuid.uuid4().hex[:8]}',
                'patient_mrn': 'GA-DEMO-005',
                'patient_name': 'Maya Patel',
                'encounter_id': f'enc-ga-005-{uuid.uuid4().hex[:8]}',
                'patient_unit': 'A5N - GI/Hematology',
                'trigger_type': 'order',
                'trigger_code': '34713-8',
                'trigger_description': 'C. difficile test ordered',
                'trigger_time': now - timedelta(hours=1),
                'patient_age_days': 2920,  # ~8 years
                'patient_age_months': 96.0,
                'status': EpisodeStatus.COMPLETE,
                'adherence_level': AdherenceLevel.FULL,
                'clinical_context': {
                    'reason_for_testing': 'Persistent watery diarrhea after amoxicillin course',
                    'antibiotic_exposure': 'Amoxicillin 10 days ago for AOM',
                    'immunocompromised': False,
                },
                'elements': [
                    {'element_id': 'cdiff_age_appropriate', 'status': ElementCheckStatus.MET,
                     'value': 'Age 8 years', 'notes': 'Age >= 3 years, testing appropriate'},
                    {'element_id': 'cdiff_liquid_stools', 'status': ElementCheckStatus.MET,
                     'value': '5 liquid stools in 24h',
                     'notes': 'Documented >= 3 liquid/watery stools in past 24 hours'},
                    {'element_id': 'cdiff_no_laxatives', 'status': ElementCheckStatus.MET,
                     'value': 'No laxatives', 'notes': 'No laxatives administered in past 48 hours'},
                    {'element_id': 'cdiff_no_contrast', 'status': ElementCheckStatus.MET,
                     'value': 'No contrast', 'notes': 'No enteral contrast in past 48 hours'},
                    {'element_id': 'cdiff_no_tube_feed', 'status': ElementCheckStatus.MET,
                     'value': 'No tube feeds', 'notes': 'Patient on regular diet, no tube feeding changes'},
                    {'element_id': 'cdiff_no_gi_bleed', 'status': ElementCheckStatus.MET,
                     'value': 'No GI bleed', 'notes': 'No evidence of active gastrointestinal bleeding'},
                    {'element_id': 'cdiff_risk_factor', 'status': ElementCheckStatus.MET,
                     'value': 'Recent antibiotics (amoxicillin)',
                     'notes': 'C. diff risk factor present: amoxicillin course completed 10 days ago'},
                    {'element_id': 'cdiff_symptom_duration', 'status': ElementCheckStatus.MET,
                     'value': '72 hours of symptoms',
                     'notes': 'Symptoms persisting > 48 hours, appropriate for testing'},
                ],
                'alerts': [],
            },
        ]

    def _create_episode(self, scenario, now):
        """Create a BundleEpisode from a scenario definition."""
        episode = BundleEpisode.objects.create(
            patient_id=scenario['patient_id'],
            patient_mrn=scenario['patient_mrn'],
            patient_name=scenario['patient_name'],
            encounter_id=scenario['encounter_id'],
            bundle_id=scenario['bundle_id'],
            bundle_name=scenario['bundle_name'],
            trigger_type=scenario['trigger_type'],
            trigger_code=scenario.get('trigger_code', ''),
            trigger_description=scenario.get('trigger_description', ''),
            trigger_time=scenario['trigger_time'],
            patient_age_days=scenario.get('patient_age_days'),
            patient_age_months=scenario.get('patient_age_months'),
            patient_unit=scenario.get('patient_unit', ''),
            status=scenario.get('status', EpisodeStatus.ACTIVE),
            clinical_context=scenario.get('clinical_context', {}),
        )

        # Set completed_at for COMPLETE episodes
        if scenario.get('status') == EpisodeStatus.COMPLETE:
            episode.completed_at = now
            episode.save(update_fields=['completed_at', 'updated_at'])

        return episode

    def _create_elements(self, episode, scenario):
        """Create ElementResult records for an episode."""
        bundle = get_bundle(scenario['bundle_id'])
        if not bundle:
            self.stderr.write(f'Bundle {scenario["bundle_id"]} not found')
            return

        # Build a lookup of element definitions from the bundle
        bundle_elements = {be.element_id: be for be in bundle.elements}

        for elem_data in scenario.get('elements', []):
            element_id = elem_data['element_id']
            bundle_elem = bundle_elements.get(element_id)

            if not bundle_elem:
                self.stderr.write(f'  Element {element_id} not in bundle {scenario["bundle_id"]}')
                continue

            # Calculate deadline from trigger_time + time_window
            deadline = None
            if bundle_elem.time_window_hours:
                deadline = episode.trigger_time + timedelta(
                    hours=bundle_elem.time_window_hours
                )

            # Set completed_at for MET elements
            completed_at = None
            if elem_data['status'] == ElementCheckStatus.MET:
                # Completed sometime between trigger and deadline (or now)
                completed_at = episode.trigger_time + timedelta(
                    minutes=15 + hash(element_id) % 60
                )

            ElementResult.objects.create(
                episode=episode,
                element_id=element_id,
                element_name=bundle_elem.name,
                element_description=bundle_elem.description,
                status=elem_data['status'],
                required=bundle_elem.required,
                value=elem_data.get('value', ''),
                notes=elem_data.get('notes', ''),
                deadline=deadline,
                completed_at=completed_at,
                time_window_hours=bundle_elem.time_window_hours,
            )

    def _create_alerts(self, episode, scenario):
        """Create Alert and AlertAudit records for a scenario."""
        for alert_data in scenario.get('alerts', []):
            severity = alert_data.get('severity', AlertSeverity.HIGH)
            priority = 95 if severity == AlertSeverity.CRITICAL else 80

            alert = Alert.objects.create(
                alert_type=alert_data['alert_type'],
                source_module='guideline_adherence',
                source_id=str(episode.id),
                title=alert_data['title'],
                summary=alert_data['summary'],
                details={
                    'episode_id': str(episode.id),
                    'bundle_id': episode.bundle_id,
                    'bundle_name': episode.bundle_name,
                    'element_id': alert_data.get('element_id', ''),
                    'element_name': alert_data.get('element_name', ''),
                    'patient_unit': episode.patient_unit,
                    'trigger_time': episode.trigger_time.isoformat(),
                    'message': alert_data.get('message', ''),
                },
                patient_id=episode.patient_id,
                patient_mrn=episode.patient_mrn,
                patient_name=episode.patient_name,
                patient_location=episode.patient_unit,
                severity=severity,
                priority_score=priority,
            )

            AlertAudit.objects.create(
                alert=alert,
                action='created',
                new_status=AlertStatus.PENDING,
                details={'source': 'demo_data', 'message': alert_data.get('message', '')},
            )
