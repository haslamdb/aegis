"""Django models for NHSN Reporting module.

11 models covering HAI event submission, AU/AR data, denominators,
and submission audit tracking.
"""

from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


# ============================================================
# Enums
# ============================================================

class HAIEventType(models.TextChoices):
    CLABSI = 'clabsi', 'CLABSI'
    CAUTI = 'cauti', 'CAUTI'
    SSI = 'ssi', 'SSI'
    VAE = 'vae', 'VAE'


class AntimicrobialRoute(models.TextChoices):
    IV = 'IV', 'IV'
    PO = 'PO', 'PO'
    IM = 'IM', 'IM'
    TOPICAL = 'TOPICAL', 'Topical'
    INHALED = 'INHALED', 'Inhaled'


class SusceptibilityResult(models.TextChoices):
    SUSCEPTIBLE = 'S', 'Susceptible'
    INTERMEDIATE = 'I', 'Intermediate'
    RESISTANT = 'R', 'Resistant'
    NON_SUSCEPTIBLE = 'NS', 'Non-susceptible'


class ResistancePhenotype(models.TextChoices):
    MRSA = 'MRSA', 'Methicillin-resistant S. aureus'
    MSSA = 'MSSA', 'Methicillin-susceptible S. aureus'
    VRE = 'VRE', 'Vancomycin-resistant Enterococcus'
    VSE = 'VSE', 'Vancomycin-susceptible Enterococcus'
    ESBL = 'ESBL', 'Extended-spectrum beta-lactamase'
    CRE = 'CRE', 'Carbapenem-resistant Enterobacterales'
    CRPA = 'CRPA', 'Carbapenem-resistant P. aeruginosa'
    CRAB = 'CRAB', 'Carbapenem-resistant A. baumannii'
    MDR = 'MDR', 'Multi-drug resistant'


# ============================================================
# HAI Event Submission
# ============================================================

class NHSNEvent(UUIDModel, TimeStampedModel):
    """Confirmed HAI event for NHSN submission."""

    candidate = models.ForeignKey(
        'hai_detection.HAICandidate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='nhsn_events',
    )
    event_date = models.DateField()
    hai_type = models.CharField(max_length=20, choices=HAIEventType.choices)
    location_code = models.CharField(max_length=50, blank=True, default='')
    pathogen_code = models.CharField(max_length=100, blank=True, default='')
    reported = models.BooleanField(default=False)
    reported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'nhsn_events'
        ordering = ['-event_date']

    def __str__(self):
        status = 'Reported' if self.reported else 'Pending'
        return f"{self.get_hai_type_display()} {self.event_date} ({status})"


# ============================================================
# Denominator Models
# ============================================================

class DenominatorDaily(TimeStampedModel):
    """Daily denominator data for a location."""

    date = models.DateField()
    location_code = models.CharField(max_length=50)
    location_type = models.CharField(max_length=50, blank=True, default='')
    patient_days = models.IntegerField(default=0)
    central_line_days = models.IntegerField(default=0)
    urinary_catheter_days = models.IntegerField(default=0)
    ventilator_days = models.IntegerField(default=0)
    admissions = models.IntegerField(default=0)

    class Meta:
        db_table = 'nhsn_denominators_daily'
        unique_together = [('date', 'location_code')]
        ordering = ['-date', 'location_code']

    def __str__(self):
        return f"{self.location_code} {self.date}: {self.patient_days} pt-days"


class DenominatorMonthly(UUIDModel, TimeStampedModel):
    """Monthly aggregated denominator data for NHSN submission."""

    month = models.CharField(max_length=7)  # YYYY-MM
    location_code = models.CharField(max_length=50)
    location_type = models.CharField(max_length=50, blank=True, default='')
    patient_days = models.IntegerField(default=0)
    central_line_days = models.IntegerField(default=0)
    urinary_catheter_days = models.IntegerField(default=0)
    ventilator_days = models.IntegerField(default=0)
    admissions = models.IntegerField(default=0)
    central_line_utilization = models.FloatField(null=True, blank=True)
    urinary_catheter_utilization = models.FloatField(null=True, blank=True)
    ventilator_utilization = models.FloatField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'nhsn_denominators_monthly'
        unique_together = [('month', 'location_code')]
        ordering = ['-month', 'location_code']

    def __str__(self):
        return f"{self.location_code} {self.month}: {self.patient_days} pt-days"

    def calculate_utilization(self):
        """Calculate device utilization ratios."""
        if self.patient_days > 0:
            self.central_line_utilization = self.central_line_days / self.patient_days
            self.urinary_catheter_utilization = self.urinary_catheter_days / self.patient_days
            self.ventilator_utilization = self.ventilator_days / self.patient_days


# ============================================================
# Antibiotic Usage (AU) Models
# ============================================================

class AUMonthlySummary(UUIDModel, TimeStampedModel):
    """Monthly AU summary by location for NHSN submission."""

    reporting_month = models.CharField(max_length=7)  # YYYY-MM
    location_code = models.CharField(max_length=50)
    location_type = models.CharField(max_length=50, blank=True, default='')
    patient_days = models.IntegerField(default=0)
    admissions = models.IntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'nhsn_au_monthly'
        unique_together = [('reporting_month', 'location_code')]
        ordering = ['-reporting_month', 'location_code']

    def __str__(self):
        return f"AU {self.location_code} {self.reporting_month}"


class AUAntimicrobialUsage(TimeStampedModel):
    """Aggregated antimicrobial usage data for a summary period."""

    summary = models.ForeignKey(
        AUMonthlySummary,
        on_delete=models.CASCADE,
        related_name='usage_records',
    )
    antimicrobial_code = models.CharField(max_length=50)
    antimicrobial_name = models.CharField(max_length=255)
    antimicrobial_class = models.CharField(max_length=100, blank=True, default='')
    route = models.CharField(max_length=20, choices=AntimicrobialRoute.choices, default=AntimicrobialRoute.IV)
    days_of_therapy = models.FloatField(default=0)
    defined_daily_doses = models.FloatField(null=True, blank=True)
    doses_administered = models.IntegerField(default=0)
    patients_treated = models.IntegerField(default=0)

    class Meta:
        db_table = 'nhsn_au_usage'
        ordering = ['antimicrobial_class', 'antimicrobial_name']

    def __str__(self):
        return f"{self.antimicrobial_name} ({self.route}): {self.days_of_therapy} DOT"


class AUPatientLevel(TimeStampedModel):
    """Patient-level antimicrobial usage for audit trail."""

    patient_id = models.CharField(max_length=255)
    patient_mrn = models.CharField(max_length=100)
    encounter_id = models.CharField(max_length=255)
    antimicrobial_code = models.CharField(max_length=50)
    antimicrobial_name = models.CharField(max_length=255)
    route = models.CharField(max_length=20, choices=AntimicrobialRoute.choices)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    total_doses = models.IntegerField(default=0)
    days_of_therapy = models.FloatField(default=0)
    location_code = models.CharField(max_length=50, blank=True, default='')
    indication = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'nhsn_au_patient_level'
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.patient_mrn}: {self.antimicrobial_name} {self.start_date}"


# ============================================================
# Antimicrobial Resistance (AR) Models
# ============================================================

class ARQuarterlySummary(UUIDModel, TimeStampedModel):
    """Quarterly AR summary by location for NHSN submission."""

    reporting_quarter = models.CharField(max_length=7)  # YYYY-Q#
    location_code = models.CharField(max_length=50)
    location_type = models.CharField(max_length=50, blank=True, default='')
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'nhsn_ar_quarterly'
        unique_together = [('reporting_quarter', 'location_code')]
        ordering = ['-reporting_quarter', 'location_code']

    def __str__(self):
        return f"AR {self.location_code} {self.reporting_quarter}"


class ARIsolate(UUIDModel, TimeStampedModel):
    """Individual isolate record for AR reporting."""

    summary = models.ForeignKey(
        ARQuarterlySummary,
        on_delete=models.CASCADE,
        related_name='isolates',
    )
    patient_id = models.CharField(max_length=255)
    patient_mrn = models.CharField(max_length=100)
    encounter_id = models.CharField(max_length=255)
    specimen_date = models.DateField()
    specimen_type = models.CharField(max_length=50)
    organism_code = models.CharField(max_length=100)
    organism_name = models.CharField(max_length=255)
    specimen_source = models.CharField(max_length=100, blank=True, default='')
    location_code = models.CharField(max_length=50, blank=True, default='')
    is_first_isolate = models.BooleanField(default=True)
    is_hai_associated = models.BooleanField(default=False)
    hai_event = models.ForeignKey(
        NHSNEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='isolates',
    )

    class Meta:
        db_table = 'nhsn_ar_isolates'
        ordering = ['-specimen_date']

    def __str__(self):
        return f"{self.organism_name} ({self.specimen_type}) {self.specimen_date}"


class ARSusceptibility(TimeStampedModel):
    """Susceptibility result for an isolate."""

    isolate = models.ForeignKey(
        ARIsolate,
        on_delete=models.CASCADE,
        related_name='susceptibilities',
    )
    antimicrobial_code = models.CharField(max_length=50)
    antimicrobial_name = models.CharField(max_length=255)
    interpretation = models.CharField(max_length=5, choices=SusceptibilityResult.choices)
    mic_value = models.CharField(max_length=50, blank=True, default='')
    mic_numeric = models.FloatField(null=True, blank=True)
    disk_zone = models.FloatField(null=True, blank=True)
    testing_method = models.CharField(max_length=50, blank=True, default='')
    breakpoint_source = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        db_table = 'nhsn_ar_susceptibilities'
        ordering = ['antimicrobial_name']

    def __str__(self):
        return f"{self.antimicrobial_name}: {self.get_interpretation_display()}"


class ARPhenotypeSummary(TimeStampedModel):
    """Aggregated phenotype summary for AR reporting."""

    summary = models.ForeignKey(
        ARQuarterlySummary,
        on_delete=models.CASCADE,
        related_name='phenotypes',
    )
    organism_code = models.CharField(max_length=100)
    organism_name = models.CharField(max_length=255)
    phenotype = models.CharField(max_length=20, choices=ResistancePhenotype.choices)
    total_isolates = models.IntegerField(default=0)
    resistant_isolates = models.IntegerField(default=0)
    percent_resistant = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 'nhsn_ar_phenotypes'
        ordering = ['organism_name', 'phenotype']

    def __str__(self):
        return f"{self.organism_name} {self.get_phenotype_display()}: {self.percent_resistant}%"

    def calculate_percent(self):
        """Calculate percent resistant."""
        if self.total_isolates > 0:
            self.percent_resistant = round(
                (self.resistant_isolates / self.total_isolates) * 100, 1
            )


# ============================================================
# Submission Audit
# ============================================================

class SubmissionAudit(TimeStampedModel):
    """Tracks NHSN submission activities."""

    action = models.CharField(max_length=50)  # csv_export, direct_submit, mark_submitted
    submission_type = models.CharField(max_length=20)  # au, ar, hai
    reporting_period = models.CharField(max_length=20)  # YYYY-MM or YYYY-Q#
    user = models.CharField(max_length=255)
    event_count = models.IntegerField(default=0)
    success = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'nhsn_submission_audit'
        ordering = ['-created_at']

    def __str__(self):
        status = 'OK' if self.success else 'FAIL'
        return f"{self.action} {self.submission_type} {self.reporting_period} [{status}]"
