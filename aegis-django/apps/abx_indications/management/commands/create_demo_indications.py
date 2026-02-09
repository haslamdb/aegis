"""Create demo indication candidates for development and testing.

Usage:
    python manage.py create_demo_indications
    python manage.py create_demo_indications --clear
    python manage.py create_demo_indications --count 20
"""

import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Create demo ABX indication candidates with CCHMC unit locations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear existing demo data first',
        )
        parser.add_argument(
            '--count', type=int, default=10,
            help='Number of demo candidates to create (default: 10)',
        )

    def handle(self, *args, **options):
        from apps.abx_indications.models import (
            IndicationCandidate, IndicationReview, IndicationLLMAuditLog,
            CandidateStatus, SyndromeConfidence, TherapyIntent,
            AgentCategoryChoice, SyndromeDecision, AgentDecision,
        )
        from apps.alerts.models import (
            Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity,
        )

        if options['clear']:
            self.stdout.write('Clearing existing ABX indication demo data...')
            # Delete alerts first (due to FK)
            alert_ids = IndicationCandidate.objects.values_list('alert_id', flat=True)
            Alert.objects.filter(id__in=alert_ids).delete()
            IndicationLLMAuditLog.objects.all().delete()
            IndicationReview.objects.all().delete()
            IndicationCandidate.objects.all().delete()
            self.stdout.write(self.style.SUCCESS('Cleared.'))

        # Demo scenarios with CCHMC hospital units
        scenarios = [
            {
                # 1. Appropriate use - no alert
                'patient_name': 'Demo Patient A',
                'patient_mrn': 'MRN-IND-001',
                'medication_name': 'Meropenem',
                'rxnorm_code': '29561',
                'location': 'G3NE - PICU',
                'service': 'Pediatric Critical Care',
                'clinical_syndrome': 'sepsis',
                'clinical_syndrome_display': 'Sepsis',
                'syndrome_category': 'bloodstream',
                'syndrome_confidence': SyndromeConfidence.DEFINITE,
                'therapy_intent': TherapyIntent.EMPIRIC,
                'supporting_evidence': ['Fever 39.2C', 'WBC 22k', 'Tachycardia', 'Hypotension'],
                'evidence_quotes': ['"Started on empiric meropenem for sepsis"'],
                'guideline_disease_ids': ['neonatal_sepsis', 'fever_neutropenia'],
                'cchmc_agent_category': AgentCategoryChoice.FIRST_LINE,
                'cchmc_disease_matched': 'Sepsis',
                'cchmc_first_line_agents': ['meropenem', 'cefepime'],
                'cchmc_recommendation': 'Meropenem is a first-line agent for sepsis',
                'alert_type': None,
            },
            {
                # 2. Appropriate use - no alert
                'patient_name': 'Demo Patient B',
                'patient_mrn': 'MRN-IND-002',
                'medication_name': 'Vancomycin',
                'rxnorm_code': '11124',
                'location': 'G1NE - NICU',
                'service': 'Neonatology',
                'clinical_syndrome': 'line_infection',
                'clinical_syndrome_display': 'Central Line Infection / CLABSI',
                'syndrome_category': 'bloodstream',
                'syndrome_confidence': SyndromeConfidence.PROBABLE,
                'therapy_intent': TherapyIntent.EMPIRIC,
                'supporting_evidence': ['PICC line day 14', 'Blood culture positive CoNS', 'Fever'],
                'evidence_quotes': ['"Blood culture grew CoNS, started vancomycin"'],
                'guideline_disease_ids': ['clabsi_cons'],
                'cchmc_agent_category': AgentCategoryChoice.FIRST_LINE,
                'cchmc_disease_matched': 'CLABSI - CoNS',
                'cchmc_first_line_agents': ['vancomycin'],
                'cchmc_recommendation': 'Vancomycin is first-line for CoNS CLABSI',
                'alert_type': None,
            },
            {
                # 3. No indication documented - HIGH alert
                'patient_name': 'Demo Patient C',
                'patient_mrn': 'MRN-IND-003',
                'medication_name': 'Ceftriaxone',
                'rxnorm_code': '3356',
                'location': 'A6N - Hospital Medicine',
                'service': 'Hospital Medicine',
                'clinical_syndrome': 'empiric_unknown',
                'clinical_syndrome_display': 'Empiric - Source Unknown',
                'syndrome_category': 'unknown',
                'syndrome_confidence': SyndromeConfidence.UNCLEAR,
                'therapy_intent': TherapyIntent.UNKNOWN,
                'supporting_evidence': [],
                'evidence_quotes': [],
                'guideline_disease_ids': [],
                'indication_not_documented': True,
                'alert_type': AlertType.ABX_NO_INDICATION,
                'alert_severity': AlertSeverity.HIGH,
            },
            {
                # 4. Never appropriate - CRITICAL alert
                'patient_name': 'Demo Patient D',
                'patient_mrn': 'MRN-IND-004',
                'medication_name': 'Amoxicillin',
                'rxnorm_code': '723',
                'location': 'A7N - Neuroscience',
                'service': 'Neurology',
                'clinical_syndrome': 'bronchiolitis',
                'clinical_syndrome_display': 'Bronchiolitis',
                'syndrome_category': 'respiratory',
                'syndrome_confidence': SyndromeConfidence.DEFINITE,
                'therapy_intent': TherapyIntent.EMPIRIC,
                'supporting_evidence': ['RSV positive', 'Wheezing', 'Nasal congestion'],
                'evidence_quotes': ['"RSV positive bronchiolitis, started amoxicillin"'],
                'guideline_disease_ids': [],
                'never_appropriate': True,
                'alert_type': AlertType.ABX_NEVER_APPROPRIATE,
                'alert_severity': AlertSeverity.CRITICAL,
            },
            {
                # 5. Off-guideline - MEDIUM alert
                'patient_name': 'Demo Patient E',
                'patient_mrn': 'MRN-IND-005',
                'medication_name': 'Ciprofloxacin',
                'rxnorm_code': '2551',
                'location': 'A4N - GI/Nephrology',
                'service': 'Nephrology',
                'clinical_syndrome': 'uti_simple',
                'clinical_syndrome_display': 'Uncomplicated UTI / Cystitis',
                'syndrome_category': 'urinary',
                'syndrome_confidence': SyndromeConfidence.DEFINITE,
                'therapy_intent': TherapyIntent.EMPIRIC,
                'supporting_evidence': ['Dysuria', 'UA positive LE and nitrites', 'Urine culture pending'],
                'evidence_quotes': ['"Simple cystitis, started ciprofloxacin"'],
                'guideline_disease_ids': ['simple_cystitis'],
                'cchmc_agent_category': AgentCategoryChoice.OFF_GUIDELINE,
                'cchmc_disease_matched': 'Simple Cystitis',
                'cchmc_first_line_agents': ['cephalexin', 'trimethoprim-sulfamethoxazole'],
                'cchmc_recommendation': 'Ciprofloxacin is off-guideline for simple cystitis. Recommended: cephalexin, TMP-SMX',
                'alert_type': AlertType.ABX_OFF_GUIDELINE,
                'alert_severity': AlertSeverity.MEDIUM,
            },
            {
                # 6. Appropriate - no alert
                'patient_name': 'Demo Patient F',
                'patient_mrn': 'MRN-IND-006',
                'medication_name': 'Piperacillin-Tazobactam',
                'rxnorm_code': '18631',
                'location': 'G6SE - CICU',
                'service': 'Cardiothoracic Surgery',
                'clinical_syndrome': 'intraabdominal_infection',
                'clinical_syndrome_display': 'Intra-abdominal Infection',
                'syndrome_category': 'intraabdominal',
                'syndrome_confidence': SyndromeConfidence.PROBABLE,
                'therapy_intent': TherapyIntent.EMPIRIC,
                'supporting_evidence': ['Post-op fever', 'Abdominal distension', 'Elevated WBC'],
                'evidence_quotes': ['"Concern for peritonitis, started pip-tazo"'],
                'guideline_disease_ids': ['appendicitis_bowel_perforation'],
                'cchmc_agent_category': AgentCategoryChoice.FIRST_LINE,
                'cchmc_disease_matched': 'Appendicitis/Bowel Perforation',
                'cchmc_first_line_agents': ['piperacillin-tazobactam'],
                'cchmc_recommendation': 'Pip-tazo is first-line for intra-abdominal infection',
                'alert_type': None,
            },
            {
                # 7. Alternative agent, reviewed
                'patient_name': 'Demo Patient G',
                'patient_mrn': 'MRN-IND-007',
                'medication_name': 'Vancomycin',
                'rxnorm_code': '11124',
                'location': 'G5NE - BMT',
                'service': 'BMT/Oncology',
                'clinical_syndrome': 'febrile_neutropenia',
                'clinical_syndrome_display': 'Febrile Neutropenia',
                'syndrome_category': 'febrile_neutropenia',
                'syndrome_confidence': SyndromeConfidence.DEFINITE,
                'therapy_intent': TherapyIntent.EMPIRIC,
                'supporting_evidence': ['ANC < 100', 'Temp 38.8', 'BMT day +12'],
                'evidence_quotes': ['"Febrile neutropenia, added vancomycin for MRSA coverage"'],
                'guideline_disease_ids': ['fever_neutropenia'],
                'cchmc_agent_category': AgentCategoryChoice.ALTERNATIVE,
                'cchmc_disease_matched': 'Fever and Neutropenia',
                'cchmc_first_line_agents': ['cefepime'],
                'cchmc_recommendation': 'Vancomycin is an acceptable alternative for high-risk FN',
                'alert_type': None,
                'reviewed': True,
            },
            {
                # 8. Alternative, no alert
                'patient_name': 'Demo Patient H',
                'patient_mrn': 'MRN-IND-008',
                'medication_name': 'Levofloxacin',
                'rxnorm_code': '82122',
                'location': 'A5N - GI/Hematology',
                'service': 'Gastroenterology',
                'clinical_syndrome': 'uti_complicated',
                'clinical_syndrome_display': 'Complicated UTI / Pyelonephritis',
                'syndrome_category': 'urinary',
                'syndrome_confidence': SyndromeConfidence.PROBABLE,
                'therapy_intent': TherapyIntent.DIRECTED,
                'supporting_evidence': ['Flank pain', 'Pyuria', 'E. coli on culture (R to TMP-SMX)'],
                'evidence_quotes': ['"Pyelo with resistant E. coli, switched to levofloxacin"'],
                'guideline_disease_ids': ['pyelonephritis'],
                'cchmc_agent_category': AgentCategoryChoice.ALTERNATIVE,
                'cchmc_disease_matched': 'Pyelonephritis',
                'cchmc_first_line_agents': ['ceftriaxone', 'ampicillin'],
                'cchmc_recommendation': 'Levofloxacin is an alternative for pyelonephritis',
                'alert_type': None,
            },
            {
                # 9. First-line, reviewed
                'patient_name': 'Demo Patient I',
                'patient_mrn': 'MRN-IND-009',
                'medication_name': 'Cefepime',
                'rxnorm_code': '2180',
                'location': 'A3N - Orthopedics',
                'service': 'Orthopedics',
                'clinical_syndrome': 'osteomyelitis',
                'clinical_syndrome_display': 'Osteomyelitis',
                'syndrome_category': 'bone_joint',
                'syndrome_confidence': SyndromeConfidence.DEFINITE,
                'therapy_intent': TherapyIntent.EMPIRIC,
                'supporting_evidence': ['Bone pain', 'Elevated CRP', 'MRI positive'],
                'evidence_quotes': ['"Acute osteomyelitis left tibia, started IV cefepime"'],
                'guideline_disease_ids': ['osteomyelitis_acute'],
                'cchmc_agent_category': AgentCategoryChoice.FIRST_LINE,
                'cchmc_disease_matched': 'Acute Osteomyelitis',
                'cchmc_first_line_agents': ['cefazolin', 'cefepime'],
                'cchmc_recommendation': 'Cefepime is first-line for osteomyelitis',
                'alert_type': None,
                'reviewed': True,
            },
            {
                # 10. Likely viral - HIGH alert
                'patient_name': 'Demo Patient J',
                'patient_mrn': 'MRN-IND-010',
                'medication_name': 'Meropenem',
                'rxnorm_code': '29561',
                'location': 'G4NE - NICU',
                'service': 'Neonatology',
                'clinical_syndrome': 'viral_uri',
                'clinical_syndrome_display': 'Viral Upper Respiratory Infection',
                'syndrome_category': 'respiratory',
                'syndrome_confidence': SyndromeConfidence.PROBABLE,
                'therapy_intent': TherapyIntent.EMPIRIC,
                'supporting_evidence': ['Rhinorrhea', 'Cough', 'Viral panel positive rhinovirus'],
                'evidence_quotes': ['"URI symptoms, rhinovirus positive, started meropenem empirically"'],
                'guideline_disease_ids': [],
                'likely_viral': True,
                'never_appropriate': True,
                'alert_type': AlertType.ABX_NEVER_APPROPRIATE,
                'alert_severity': AlertSeverity.CRITICAL,
            },
        ]

        created = 0
        for i, scenario in enumerate(scenarios[:options['count']]):
            fhir_id = f'demo-indication-{uuid.uuid4().hex[:8]}'

            candidate = IndicationCandidate.objects.create(
                patient_id=f'fhir-patient-ind-{i+1:03d}',
                patient_mrn=scenario['patient_mrn'],
                patient_name=scenario['patient_name'],
                patient_location=scenario['location'],
                medication_request_id=fhir_id,
                medication_name=scenario['medication_name'],
                rxnorm_code=scenario.get('rxnorm_code', ''),
                order_date=timezone.now() - timedelta(hours=i * 3 + 2),
                location=scenario['location'],
                service=scenario.get('service', ''),
                clinical_syndrome=scenario['clinical_syndrome'],
                clinical_syndrome_display=scenario['clinical_syndrome_display'],
                syndrome_category=scenario['syndrome_category'],
                syndrome_confidence=scenario['syndrome_confidence'],
                therapy_intent=scenario.get('therapy_intent', TherapyIntent.UNKNOWN),
                supporting_evidence=scenario.get('supporting_evidence', []),
                evidence_quotes=scenario.get('evidence_quotes', []),
                guideline_disease_ids=scenario.get('guideline_disease_ids', []),
                indication_not_documented=scenario.get('indication_not_documented', False),
                likely_viral=scenario.get('likely_viral', False),
                asymptomatic_bacteriuria=scenario.get('asymptomatic_bacteriuria', False),
                never_appropriate=scenario.get('never_appropriate', False),
                cchmc_disease_matched=scenario.get('cchmc_disease_matched', ''),
                cchmc_agent_category=scenario.get('cchmc_agent_category', ''),
                cchmc_first_line_agents=scenario.get('cchmc_first_line_agents'),
                cchmc_recommendation=scenario.get('cchmc_recommendation', ''),
            )

            # Create alert if needed
            if scenario.get('alert_type'):
                severity = scenario.get('alert_severity', AlertSeverity.MEDIUM)
                alert = Alert.objects.create(
                    alert_type=scenario['alert_type'],
                    source_module='abx_indications',
                    source_id=str(candidate.id),
                    title=f"ABX Alert: {scenario['medication_name']}",
                    summary=f"{scenario['medication_name']} - {scenario['clinical_syndrome_display']}",
                    details={
                        'medication_name': scenario['medication_name'],
                        'clinical_syndrome': scenario['clinical_syndrome'],
                        'clinical_syndrome_display': scenario['clinical_syndrome_display'],
                    },
                    patient_id=candidate.patient_id,
                    patient_mrn=scenario['patient_mrn'],
                    patient_name=scenario['patient_name'],
                    patient_location=scenario['location'],
                    severity=severity,
                    priority_score=95 if severity == AlertSeverity.CRITICAL else 80,
                )
                AlertAudit.objects.create(
                    alert=alert,
                    action='created',
                    new_status=AlertStatus.PENDING,
                    details={'source': 'demo_data'},
                )
                candidate.status = CandidateStatus.ALERTED
                candidate.alert = alert
                candidate.save(update_fields=['status', 'alert'])

            # Create review if marked as reviewed
            if scenario.get('reviewed'):
                IndicationReview.objects.create(
                    candidate=candidate,
                    syndrome_decision=SyndromeDecision.CONFIRM_SYNDROME,
                    agent_decision=AgentDecision.APPROPRIATE,
                    notes='Demo review',
                )
                candidate.status = CandidateStatus.REVIEWED
                candidate.save(update_fields=['status'])

            # Create LLM audit log entry
            IndicationLLMAuditLog.objects.create(
                candidate=candidate,
                model='qwen2.5:7b',
                success=True,
                input_tokens=1200 + i * 100,
                output_tokens=180 + i * 20,
                response_time_ms=800 + i * 50,
            )

            created += 1
            self.stdout.write(
                f'  [{candidate.status}] {scenario["medication_name"]} - '
                f'{scenario["patient_mrn"]} @ {scenario["location"]} - '
                f'{scenario["clinical_syndrome_display"]}'
            )

        self.stdout.write(self.style.SUCCESS(f'\nCreated {created} demo indication candidates'))
