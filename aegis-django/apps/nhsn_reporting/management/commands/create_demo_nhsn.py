"""Create demo data for NHSN Reporting module."""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.nhsn_reporting.models import (
    NHSNEvent, HAIEventType,
    DenominatorDaily, DenominatorMonthly,
    AUMonthlySummary, AUAntimicrobialUsage, AUPatientLevel, AntimicrobialRoute,
    ARQuarterlySummary, ARIsolate, ARSusceptibility, ARPhenotypeSummary,
    SusceptibilityResult, ResistancePhenotype,
    SubmissionAudit,
)


# CCHMC units for demo data
CCHMC_LOCATIONS = [
    ('G1-NICU', 'NICU'),
    ('G3-PICU', 'ICU'),
    ('G6-CICU', 'ICU'),
    ('A5-HemeOnc', 'Ward'),
    ('A6-HospMed', 'Ward'),
    ('G5-BMT', 'BMT'),
]

ANTIMICROBIALS = [
    ('VAN', 'Vancomycin', 'Glycopeptides', 2.0),
    ('MER', 'Meropenem', 'Carbapenems', 3.0),
    ('CEF', 'Ceftriaxone', 'Cephalosporins', 2.0),
    ('PIP', 'Piperacillin-Tazobactam', 'Beta-lactam combinations', 14.0),
    ('AMP', 'Ampicillin', 'Penicillins', 6.0),
    ('GEN', 'Gentamicin', 'Aminoglycosides', 0.24),
    ('FLU', 'Fluconazole', 'Antifungals', 0.2),
    ('LIN', 'Linezolid', 'Oxazolidinones', 1.2),
    ('CLI', 'Clindamycin', 'Lincosamides', 1.2),
    ('MTZ', 'Metronidazole', 'Nitroimidazoles', 1.5),
]

ORGANISMS = [
    ('SA', 'Staphylococcus aureus', 'Staphylococcus'),
    ('CONS', 'Coagulase-negative Staphylococcus', 'Staphylococcus'),
    ('EC', 'Escherichia coli', 'Enterobacterales'),
    ('KP', 'Klebsiella pneumoniae', 'Enterobacterales'),
    ('EF', 'Enterococcus faecalis', 'Enterococcus'),
    ('EFM', 'Enterococcus faecium', 'Enterococcus'),
    ('PA', 'Pseudomonas aeruginosa', 'Non-fermenter'),
    ('CA', 'Candida albicans', 'Yeast'),
]

PATHOGENS_FOR_HAI = ['Staphylococcus aureus', 'Escherichia coli', 'Klebsiella pneumoniae',
                      'Enterococcus faecalis', 'Candida albicans', 'Pseudomonas aeruginosa']


class Command(BaseCommand):
    help = 'Create demo NHSN reporting data'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Clear existing data first')
        parser.add_argument('--count', type=int, default=6, help='Number of months of data to generate')

    def handle(self, *args, **options):
        if options['clear']:
            self._clear_data()

        months = options['count']
        self.stdout.write(f"Creating {months} months of demo NHSN data...")

        self._create_denominator_data(months)
        self._create_au_data(months)
        self._create_ar_data(months)
        self._create_hai_events()
        self._create_submission_audit()

        self.stdout.write(self.style.SUCCESS("Demo NHSN data created successfully."))

    def _clear_data(self):
        self.stdout.write("Clearing existing NHSN data...")
        SubmissionAudit.objects.all().delete()
        ARSusceptibility.objects.all().delete()
        ARPhenotypeSummary.objects.all().delete()
        ARIsolate.objects.all().delete()
        ARQuarterlySummary.objects.all().delete()
        AUPatientLevel.objects.all().delete()
        AUAntimicrobialUsage.objects.all().delete()
        AUMonthlySummary.objects.all().delete()
        DenominatorDaily.objects.all().delete()
        DenominatorMonthly.objects.all().delete()
        NHSNEvent.objects.all().delete()

    def _create_denominator_data(self, months):
        """Create monthly denominator data for each location."""
        today = date.today()

        for i in range(months):
            month_date = today.replace(day=1) - timedelta(days=30 * i)
            month_str = month_date.strftime('%Y-%m')

            for loc_code, loc_type in CCHMC_LOCATIONS:
                base_pd = random.randint(200, 800) if loc_type == 'ICU' else random.randint(100, 400)

                DenominatorMonthly.objects.update_or_create(
                    month=month_str,
                    location_code=loc_code,
                    defaults={
                        'location_type': loc_type,
                        'patient_days': base_pd,
                        'central_line_days': int(base_pd * random.uniform(0.2, 0.6)),
                        'urinary_catheter_days': int(base_pd * random.uniform(0.1, 0.4)),
                        'ventilator_days': int(base_pd * random.uniform(0.1, 0.5)) if loc_type == 'ICU' else int(base_pd * random.uniform(0, 0.05)),
                        'admissions': random.randint(20, 80),
                    },
                )

        # Calculate utilization ratios
        for denom in DenominatorMonthly.objects.all():
            denom.calculate_utilization()
            denom.save(update_fields=['central_line_utilization', 'urinary_catheter_utilization', 'ventilator_utilization', 'updated_at'])

        count = DenominatorMonthly.objects.count()
        self.stdout.write(f"  Created {count} monthly denominator records")

    def _create_au_data(self, months):
        """Create monthly AU summaries with antimicrobial usage."""
        today = date.today()

        for i in range(months):
            month_date = today.replace(day=1) - timedelta(days=30 * i)
            month_str = month_date.strftime('%Y-%m')

            for loc_code, loc_type in CCHMC_LOCATIONS:
                denom = DenominatorMonthly.objects.filter(month=month_str, location_code=loc_code).first()
                patient_days = denom.patient_days if denom else random.randint(200, 600)

                summary, _ = AUMonthlySummary.objects.update_or_create(
                    reporting_month=month_str,
                    location_code=loc_code,
                    defaults={
                        'location_type': loc_type,
                        'patient_days': patient_days,
                        'admissions': random.randint(20, 80),
                    },
                )

                # Create 4-7 antimicrobial usage records per location/month
                selected_abx = random.sample(ANTIMICROBIALS, random.randint(4, 7))
                for code, name, abx_class, ddd_std in selected_abx:
                    route = random.choice([AntimicrobialRoute.IV, AntimicrobialRoute.IV, AntimicrobialRoute.PO])
                    dot = random.randint(5, 80)
                    ddd = round(dot * random.uniform(0.5, 1.5), 1)

                    AUAntimicrobialUsage.objects.create(
                        summary=summary,
                        antimicrobial_code=code,
                        antimicrobial_name=name,
                        antimicrobial_class=abx_class,
                        route=route,
                        days_of_therapy=dot,
                        defined_daily_doses=ddd,
                        doses_administered=dot * random.randint(2, 4),
                        patients_treated=random.randint(3, 25),
                    )

        count = AUMonthlySummary.objects.count()
        usage_count = AUAntimicrobialUsage.objects.count()
        self.stdout.write(f"  Created {count} AU summaries with {usage_count} usage records")

    def _create_ar_data(self, months):
        """Create quarterly AR summaries with isolates and susceptibilities."""
        today = date.today()
        quarters_created = set()

        for i in range(months):
            month_date = today.replace(day=1) - timedelta(days=30 * i)
            q = (month_date.month - 1) // 3 + 1
            quarter_str = f"{month_date.year}-Q{q}"

            if quarter_str in quarters_created:
                continue
            quarters_created.add(quarter_str)

            for loc_code, loc_type in CCHMC_LOCATIONS[:4]:  # Top 4 locations
                summary, _ = ARQuarterlySummary.objects.update_or_create(
                    reporting_quarter=quarter_str,
                    location_code=loc_code,
                    defaults={'location_type': loc_type},
                )

                # Create 5-15 isolates per location/quarter
                num_isolates = random.randint(5, 15)
                for j in range(num_isolates):
                    org_code, org_name, org_group = random.choice(ORGANISMS)
                    specimen_date = month_date + timedelta(days=random.randint(0, 85))

                    isolate = ARIsolate.objects.create(
                        summary=summary,
                        patient_id=f"PAT{random.randint(10000, 99999)}",
                        patient_mrn=f"MRN{random.randint(100000, 999999)}",
                        encounter_id=f"ENC{random.randint(100000, 999999)}",
                        specimen_date=specimen_date,
                        specimen_type=random.choice(['Blood', 'Urine', 'Respiratory', 'CSF']),
                        organism_code=org_code,
                        organism_name=org_name,
                        location_code=loc_code,
                        is_first_isolate=True,
                    )

                    # Add 3-6 susceptibility results per isolate
                    abx_subset = random.sample(ANTIMICROBIALS[:8], random.randint(3, 6))
                    for abx_code, abx_name, _, _ in abx_subset:
                        interp = random.choices(
                            [SusceptibilityResult.SUSCEPTIBLE, SusceptibilityResult.INTERMEDIATE, SusceptibilityResult.RESISTANT],
                            weights=[70, 10, 20],
                        )[0]
                        ARSusceptibility.objects.create(
                            isolate=isolate,
                            antimicrobial_code=abx_code,
                            antimicrobial_name=abx_name,
                            interpretation=interp,
                            mic_value=f"<={random.choice(['0.5', '1', '2', '4'])}" if interp == SusceptibilityResult.SUSCEPTIBLE else f">={random.choice(['8', '16', '32'])}",
                            testing_method='MIC',
                            breakpoint_source='CLSI',
                        )

                # Create phenotype summaries
                for phenotype in [ResistancePhenotype.MRSA, ResistancePhenotype.VRE, ResistancePhenotype.ESBL, ResistancePhenotype.CRE]:
                    total = random.randint(5, 30)
                    resistant = random.randint(0, int(total * 0.4))
                    pheno = ARPhenotypeSummary.objects.create(
                        summary=summary,
                        organism_code=phenotype.value,
                        organism_name=phenotype.label,
                        phenotype=phenotype,
                        total_isolates=total,
                        resistant_isolates=resistant,
                    )
                    pheno.calculate_percent()
                    pheno.save(update_fields=['percent_resistant', 'updated_at'])

        ar_count = ARQuarterlySummary.objects.count()
        iso_count = ARIsolate.objects.count()
        self.stdout.write(f"  Created {ar_count} AR summaries with {iso_count} isolates")

    def _create_hai_events(self):
        """Create sample HAI events."""
        today = date.today()

        hai_types = [HAIEventType.CLABSI, HAIEventType.CAUTI, HAIEventType.VAE, HAIEventType.SSI]

        for i in range(12):
            event_date = today - timedelta(days=random.randint(1, 180))
            hai_type = random.choice(hai_types)
            loc = random.choice(CCHMC_LOCATIONS)
            reported = random.random() < 0.4  # 40% already reported

            NHSNEvent.objects.create(
                event_date=event_date,
                hai_type=hai_type,
                location_code=loc[0],
                pathogen_code=random.choice(PATHOGENS_FOR_HAI),
                reported=reported,
                reported_at=timezone.now() - timedelta(days=random.randint(1, 30)) if reported else None,
            )

        count = NHSNEvent.objects.count()
        unreported = NHSNEvent.objects.filter(reported=False).count()
        self.stdout.write(f"  Created {count} HAI events ({unreported} unreported)")

    def _create_submission_audit(self):
        """Create sample submission audit records."""
        actions = ['csv_export', 'mark_submitted', 'direct_submit']
        types = ['au', 'ar', 'hai']

        for i in range(5):
            SubmissionAudit.objects.create(
                action=random.choice(actions),
                submission_type=random.choice(types),
                reporting_period=f"2026-{random.randint(1, 12):02d}",
                user='demo_ip',
                event_count=random.randint(1, 20),
                success=True,
                notes='Demo submission',
            )

        self.stdout.write(f"  Created {SubmissionAudit.objects.count()} audit records")
