"""
Create demo surgical prophylaxis data for development and testing.

Generates 8 realistic scenarios using real CCHMC hospital units and OR locations.

Usage:
    python manage.py create_demo_prophylaxis
    python manage.py create_demo_prophylaxis --clear
    python manage.py create_demo_prophylaxis --clear --count 8
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertSeverity, AlertStatus
from apps.surgical_prophylaxis.models import (
    SurgicalCase, ProphylaxisEvaluation, ProphylaxisMedication,
    ComplianceStatus, ProcedureCategory,
)
from apps.surgical_prophylaxis.logic.evaluator import ProphylaxisEvaluator


# 8 demo scenarios at CCHMC
DEMO_SCENARIOS = [
    {
        # 1. VSD Repair — Fully compliant cardiac case
        'case_id': 'demo-sp-001',
        'patient_mrn': 'MRN200101',
        'patient_name': 'Garcia, Sofia (3y)',
        'procedure_description': 'Ventricular Septal Defect Repair',
        'procedure_category': ProcedureCategory.CARDIAC,
        'cpt_codes': ['33681'],
        'location': 'OR-3',
        'surgeon_name': 'Dr. Patel (Cardiac Surgery)',
        'patient_weight_kg': 14.5,
        'patient_age_years': 3.0,
        'medications': [
            {'type': 'order', 'name': 'Cefazolin', 'dose': 350, 'route': 'IV',
             'offset_minutes': -45},
            {'type': 'administration', 'name': 'Cefazolin', 'dose': 350, 'route': 'IV',
             'offset_minutes': -30},
        ],
        'surgery_duration_hours': 3.5,
        'expected_compliant': True,
    },
    {
        # 2. Spinal Fusion — MRSA+ with vancomycin, compliant
        'case_id': 'demo-sp-002',
        'patient_mrn': 'MRN200102',
        'patient_name': 'Thompson, Jayden (14y)',
        'procedure_description': 'Posterior Spinal Fusion T4-L2',
        'procedure_category': ProcedureCategory.ORTHOPEDIC,
        'cpt_codes': ['22802'],
        'location': 'OR-5',
        'surgeon_name': 'Dr. Kim (Orthopedics)',
        'patient_weight_kg': 52.0,
        'patient_age_years': 14.0,
        'mrsa_colonized': True,
        'medications': [
            {'type': 'order', 'name': 'Cefazolin', 'dose': 2000, 'route': 'IV',
             'offset_minutes': -45},
            {'type': 'order', 'name': 'Vancomycin', 'dose': 780, 'route': 'IV',
             'offset_minutes': -90},
            {'type': 'administration', 'name': 'Cefazolin', 'dose': 2000, 'route': 'IV',
             'offset_minutes': -40},
            {'type': 'administration', 'name': 'Vancomycin', 'dose': 780, 'route': 'IV',
             'offset_minutes': -85},
        ],
        'surgery_duration_hours': 5.0,
        'expected_compliant': True,
    },
    {
        # 3. Appendectomy — Timing failure (120 min > 60 min window)
        'case_id': 'demo-sp-003',
        'patient_mrn': 'MRN200103',
        'patient_name': 'Williams, Ava (8y)',
        'procedure_description': 'Laparoscopic Appendectomy',
        'procedure_category': ProcedureCategory.GASTROINTESTINAL_UPPER,
        'cpt_codes': ['44970'],
        'location': 'OR-2',
        'surgeon_name': 'Dr. Rodriguez (General Surgery)',
        'patient_weight_kg': 27.0,
        'patient_age_years': 8.0,
        'medications': [
            {'type': 'order', 'name': 'Cefoxitin', 'dose': 800, 'route': 'IV',
             'offset_minutes': -130},
            {'type': 'administration', 'name': 'Cefoxitin', 'dose': 800, 'route': 'IV',
             'offset_minutes': -120},
        ],
        'surgery_duration_hours': 1.5,
        'expected_compliant': False,
        'expected_severity': AlertSeverity.MEDIUM,
    },
    {
        # 4. Colectomy — Wrong agent (cefazolin instead of cefoxitin)
        'case_id': 'demo-sp-004',
        'patient_mrn': 'MRN200104',
        'patient_name': 'Chen, Lucas (11y)',
        'procedure_description': 'Right Hemicolectomy',
        'procedure_category': ProcedureCategory.GASTROINTESTINAL_COLORECTAL,
        'cpt_codes': ['44160'],
        'location': 'OR-4',
        'surgeon_name': 'Dr. Anderson (Colorectal Surgery)',
        'patient_weight_kg': 38.0,
        'patient_age_years': 11.0,
        'medications': [
            {'type': 'order', 'name': 'Cefazolin', 'dose': 1000, 'route': 'IV',
             'offset_minutes': -40},
            {'type': 'administration', 'name': 'Cefazolin', 'dose': 1000, 'route': 'IV',
             'offset_minutes': -35},
        ],
        'surgery_duration_hours': 2.5,
        'expected_compliant': False,
        'expected_severity': AlertSeverity.HIGH,
    },
    {
        # 5. Cochlear Implant — Missing prophylaxis entirely
        'case_id': 'demo-sp-005',
        'patient_mrn': 'MRN200105',
        'patient_name': 'Brown, Mia (2y)',
        'procedure_description': 'Cochlear Implant Insertion',
        'procedure_category': ProcedureCategory.ENT,
        'cpt_codes': ['69930'],
        'location': 'OR-6',
        'surgeon_name': 'Dr. Lee (ENT)',
        'patient_weight_kg': 12.0,
        'patient_age_years': 2.0,
        'medications': [],
        'surgery_duration_hours': 2.0,
        'expected_compliant': False,
        'expected_severity': AlertSeverity.CRITICAL,
    },
    {
        # 6. Laparoscopic Cholecystectomy — Correctly withheld (no indication)
        'case_id': 'demo-sp-006',
        'patient_mrn': 'MRN200106',
        'patient_name': 'Davis, Emma (15y)',
        'procedure_description': 'Laparoscopic Cholecystectomy',
        'procedure_category': ProcedureCategory.HEPATOBILIARY,
        'cpt_codes': ['47562'],
        'location': 'OR-1',
        'surgeon_name': 'Dr. Wilson (General Surgery)',
        'patient_weight_kg': 55.0,
        'patient_age_years': 15.0,
        'medications': [],
        'surgery_duration_hours': 1.0,
        'expected_compliant': True,
        'no_indication': True,
    },
    {
        # 7. Emergency Craniotomy — Excluded (emergency)
        'case_id': 'demo-sp-007',
        'patient_mrn': 'MRN200107',
        'patient_name': 'Martinez, Diego (6y)',
        'procedure_description': 'Emergency Craniotomy for Epidural Hematoma',
        'procedure_category': ProcedureCategory.NEUROSURGERY,
        'cpt_codes': ['61312'],
        'location': 'OR-TRAUMA',
        'surgeon_name': 'Dr. Shah (Neurosurgery)',
        'patient_weight_kg': 21.0,
        'patient_age_years': 6.0,
        'is_emergency': True,
        'medications': [
            {'type': 'order', 'name': 'Cefazolin', 'dose': 500, 'route': 'IV',
             'offset_minutes': -15},
            {'type': 'administration', 'name': 'Cefazolin', 'dose': 500, 'route': 'IV',
             'offset_minutes': -10},
        ],
        'surgery_duration_hours': 2.0,
        'expected_compliant': True,
        'excluded': True,
    },
    {
        # 8. Perforated Appendectomy — Post-op continuation compliant
        'case_id': 'demo-sp-008',
        'patient_mrn': 'MRN200108',
        'patient_name': 'Johnson, Noah (10y)',
        'procedure_description': 'Open Appendectomy for Perforated Appendicitis',
        'procedure_category': ProcedureCategory.GASTROINTESTINAL_UPPER,
        'cpt_codes': ['44960'],
        'location': 'OR-2',
        'surgeon_name': 'Dr. Rodriguez (General Surgery)',
        'patient_weight_kg': 33.0,
        'patient_age_years': 10.0,
        'documented_infection': True,
        'medications': [
            {'type': 'order', 'name': 'Piperacillin-Tazobactam', 'dose': 3375, 'route': 'IV',
             'offset_minutes': -30},
            {'type': 'administration', 'name': 'Piperacillin-Tazobactam', 'dose': 3375,
             'route': 'IV', 'offset_minutes': -25},
        ],
        'surgery_duration_hours': 1.5,
        'expected_compliant': True,
        'excluded': True,
    },
]


class Command(BaseCommand):
    help = 'Create demo surgical prophylaxis data with 8 CCHMC scenarios'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear existing prophylaxis data before creating',
        )
        parser.add_argument(
            '--count', type=int, default=len(DEMO_SCENARIOS),
            help=f'Number of scenarios to create (default: {len(DEMO_SCENARIOS)})',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write("Clearing existing prophylaxis data...")
            ProphylaxisMedication.objects.all().delete()
            ProphylaxisEvaluation.objects.all().delete()
            SurgicalCase.objects.all().delete()
            Alert.objects.filter(
                alert_type=AlertType.SURGICAL_PROPHYLAXIS,
                source_module='surgical_prophylaxis',
            ).delete()
            self.stdout.write(self.style.SUCCESS("  Cleared."))

        count = min(options['count'], len(DEMO_SCENARIOS))
        scenarios = DEMO_SCENARIOS[:count]
        self.stdout.write(f"Creating {count} demo surgical cases...")

        now = timezone.now()
        evaluator = ProphylaxisEvaluator()
        created = 0

        for i, scenario in enumerate(scenarios):
            # Stagger cases over past few days
            hours_ago = random.randint(2, 72)
            incision_time = now - timedelta(hours=hours_ago)
            scheduled_time = incision_time - timedelta(minutes=random.randint(30, 120))
            surgery_end = incision_time + timedelta(
                hours=scenario.get('surgery_duration_hours', 2.0)
            )

            # Create case
            case = SurgicalCase.objects.create(
                case_id=scenario['case_id'],
                patient_mrn=scenario['patient_mrn'],
                patient_name=scenario['patient_name'],
                procedure_description=scenario['procedure_description'],
                procedure_category=scenario['procedure_category'],
                cpt_codes=scenario.get('cpt_codes', []),
                location=scenario.get('location', ''),
                surgeon_name=scenario.get('surgeon_name', ''),
                scheduled_or_time=scheduled_time,
                actual_incision_time=incision_time,
                surgery_end_time=surgery_end,
                patient_weight_kg=scenario.get('patient_weight_kg'),
                patient_age_years=scenario.get('patient_age_years'),
                has_beta_lactam_allergy=scenario.get('has_beta_lactam_allergy', False),
                mrsa_colonized=scenario.get('mrsa_colonized', False),
                is_emergency=scenario.get('is_emergency', False),
                already_on_therapeutic_abx=scenario.get('already_on_therapeutic_abx', False),
                documented_infection=scenario.get('documented_infection', False),
            )

            # Create medications
            for med in scenario.get('medications', []):
                med_time = incision_time + timedelta(minutes=med['offset_minutes'])
                ProphylaxisMedication.objects.create(
                    case=case,
                    medication_type=med['type'],
                    medication_name=med['name'],
                    dose_mg=med['dose'],
                    route=med.get('route', 'IV'),
                    event_time=med_time,
                )

            # Evaluate the case
            eval_result = evaluator.evaluate_case(case)
            evaluation = ProphylaxisEvaluation.objects.create(
                case=case,
                evaluation_time=now,
                **eval_result,
            )

            # Create alert for non-compliant, non-excluded cases
            alert = None
            if not evaluation.excluded and not evaluation.bundle_compliant:
                severity = scenario.get('expected_severity', AlertSeverity.MEDIUM)
                alert = Alert.objects.create(
                    alert_type=AlertType.SURGICAL_PROPHYLAXIS,
                    source_module='surgical_prophylaxis',
                    source_id=case.case_id,
                    title=f"Prophylaxis: {case.procedure_description[:80]}",
                    summary='; '.join(evaluation.recommendations) if evaluation.recommendations else 'Bundle non-compliant',
                    details={
                        'case_id': case.case_id,
                        'patient_mrn': case.patient_mrn,
                        'procedure': case.procedure_description,
                        'category': case.procedure_category,
                        'compliance_score': evaluation.compliance_score,
                        'elements_met': evaluation.elements_met,
                        'elements_total': evaluation.elements_total,
                    },
                    patient_mrn=case.patient_mrn,
                    patient_name=case.patient_name,
                    severity=severity,
                    status=AlertStatus.PENDING,
                )
                AlertAudit.objects.create(
                    alert=alert,
                    action='created',
                    details=f"Demo case: {case.procedure_description}",
                )
                evaluation.alert = alert
                evaluation.save(update_fields=['alert', 'updated_at'])

            # Output
            if evaluation.excluded:
                status_str = 'EXCLUDED'
            elif evaluation.bundle_compliant:
                status_str = 'COMPLIANT'
            else:
                status_str = f'NON-COMPLIANT ({evaluation.compliance_score:.0f}%)'

            alert_str = f' -> Alert: {alert.get_severity_display()}' if alert else ''
            self.stdout.write(
                f"  {i+1}. [{status_str}] {case.procedure_description[:45]} "
                f"@ {case.location} - {case.patient_name}{alert_str}"
            )

            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nCreated {created} demo surgical cases with evaluations."
        ))

        # Summary
        total_cases = SurgicalCase.objects.count()
        total_evals = ProphylaxisEvaluation.objects.count()
        total_meds = ProphylaxisMedication.objects.count()
        total_alerts = Alert.objects.filter(
            alert_type=AlertType.SURGICAL_PROPHYLAXIS,
            source_module='surgical_prophylaxis',
        ).count()
        compliant = ProphylaxisEvaluation.objects.filter(bundle_compliant=True).count()
        excluded = ProphylaxisEvaluation.objects.filter(excluded=True).count()

        self.stdout.write(f"  Total cases:       {total_cases}")
        self.stdout.write(f"  Total evaluations: {total_evals}")
        self.stdout.write(f"  Total medications: {total_meds}")
        self.stdout.write(f"  Compliant:         {compliant}")
        self.stdout.write(f"  Excluded:          {excluded}")
        self.stdout.write(f"  Alerts created:    {total_alerts}")
