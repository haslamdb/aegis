"""
Django models for surgical prophylaxis monitoring.

Replaces Flask dataclasses and SQLite tables with Django ORM models.
Covers both batch ASHP bundle evaluation and real-time HL7 ADT tracking.
"""

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDModel
from apps.alerts.models import Alert


# --- Enums ---

class ComplianceStatus(models.TextChoices):
    """Status of individual bundle elements."""
    MET = 'met', 'Met'
    NOT_MET = 'not_met', 'Not Met'
    PENDING = 'pending', 'Pending'
    NOT_APPLICABLE = 'n/a', 'Not Applicable'
    UNABLE_TO_ASSESS = 'unable', 'Unable to Assess'


class ProcedureCategory(models.TextChoices):
    """Categories of surgical procedures."""
    CARDIAC = 'cardiac', 'Cardiac'
    THORACIC = 'thoracic', 'Thoracic'
    GASTROINTESTINAL_UPPER = 'gastrointestinal_upper', 'GI Upper'
    GASTROINTESTINAL_COLORECTAL = 'gastrointestinal_colorectal', 'GI Colorectal'
    HEPATOBILIARY = 'hepatobiliary', 'Hepatobiliary'
    ORTHOPEDIC = 'orthopedic', 'Orthopedic'
    NEUROSURGERY = 'neurosurgery', 'Neurosurgery'
    UROLOGY = 'urology', 'Urology'
    ENT = 'ent', 'ENT'
    HERNIA = 'hernia', 'Hernia'
    PLASTICS = 'plastics', 'Plastics'
    VASCULAR = 'vascular', 'Vascular'
    OTHER = 'other', 'Other'


class LocationState(models.TextChoices):
    """Patient location states in surgical workflow."""
    UNKNOWN = 'unknown', 'Unknown'
    INPATIENT = 'inpatient', 'Inpatient'
    PRE_OP_HOLDING = 'pre_op', 'Pre-Op Holding'
    OR_SUITE = 'or_suite', 'OR Suite'
    PACU = 'pacu', 'PACU'
    DISCHARGED = 'discharged', 'Discharged'


class AlertTrigger(models.TextChoices):
    """Alert trigger points in surgical workflow."""
    T24 = 't24', 'T-24h'
    T2 = 't2', 'T-2h'
    T60 = 't60', 'T-60min'
    T0 = 't0', 'T-0 (OR Entry)'
    PREOP_ARRIVAL = 'preop_arrival', 'Pre-Op Arrival'
    OR_ENTRY = 'or_entry', 'OR Entry'


# --- Core Models ---

class SurgicalCase(UUIDModel, TimeStampedModel):
    """
    Represents a surgical case for prophylaxis evaluation.

    One record per surgical procedure. Links to evaluations and medications.
    """
    case_id = models.CharField(
        max_length=100, unique=True,
        help_text="FHIR Procedure ID or external case identifier"
    )
    patient_mrn = models.CharField(max_length=100, db_index=True)
    patient_name = models.CharField(max_length=255, blank=True)
    encounter_id = models.CharField(max_length=100, blank=True)

    # Procedure info
    cpt_codes = models.JSONField(default=list, help_text="List of CPT code strings")
    procedure_description = models.CharField(max_length=500)
    procedure_category = models.CharField(
        max_length=30, choices=ProcedureCategory.choices,
        default=ProcedureCategory.OTHER
    )
    surgeon_id = models.CharField(max_length=100, blank=True)
    surgeon_name = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=100, blank=True)

    # Timing
    scheduled_or_time = models.DateTimeField(null=True, blank=True)
    actual_incision_time = models.DateTimeField(null=True, blank=True)
    surgery_end_time = models.DateTimeField(null=True, blank=True)

    # Patient factors
    patient_weight_kg = models.FloatField(null=True, blank=True)
    patient_age_years = models.FloatField(null=True, blank=True)
    allergies = models.JSONField(default=list)
    has_beta_lactam_allergy = models.BooleanField(default=False)
    mrsa_colonized = models.BooleanField(default=False)

    # Exclusion flags
    is_emergency = models.BooleanField(default=False)
    already_on_therapeutic_abx = models.BooleanField(default=False)
    documented_infection = models.BooleanField(default=False)

    class Meta:
        db_table = 'surgical_cases'
        verbose_name = 'Surgical Case'
        verbose_name_plural = 'Surgical Cases'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['patient_mrn']),
            models.Index(fields=['encounter_id']),
            models.Index(fields=['scheduled_or_time']),
            models.Index(fields=['procedure_category']),
        ]

    def __str__(self):
        return f"{self.patient_mrn} - {self.procedure_description[:50]}"

    @property
    def surgery_duration_hours(self):
        """Calculate surgery duration in hours."""
        if self.actual_incision_time and self.surgery_end_time:
            delta = self.surgery_end_time - self.actual_incision_time
            return delta.total_seconds() / 3600
        return None


class ProphylaxisEvaluation(TimeStampedModel):
    """
    Result of a 7-element ASHP bundle compliance evaluation.

    Each element result is stored as a JSONField containing
    {status, details, recommendation, data}.
    """
    case = models.ForeignKey(
        SurgicalCase, on_delete=models.CASCADE, related_name='evaluations'
    )
    evaluation_time = models.DateTimeField(default=timezone.now)

    # Element results (each is a dict with status/details/recommendation/data)
    indication_result = models.JSONField(default=dict)
    agent_result = models.JSONField(default=dict)
    timing_result = models.JSONField(default=dict)
    dosing_result = models.JSONField(default=dict)
    redosing_result = models.JSONField(default=dict)
    postop_result = models.JSONField(default=dict)
    discontinuation_result = models.JSONField(default=dict)

    # Summary
    bundle_compliant = models.BooleanField(default=False)
    compliance_score = models.FloatField(default=0.0)
    elements_met = models.IntegerField(default=0)
    elements_total = models.IntegerField(default=0)

    # Flags and recommendations
    flags = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)

    # Exclusion
    excluded = models.BooleanField(default=False)
    exclusion_reason = models.CharField(max_length=255, blank=True)

    # Link to generated alert
    alert = models.ForeignKey(
        Alert, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='prophylaxis_evaluations'
    )

    class Meta:
        db_table = 'prophylaxis_evaluations'
        verbose_name = 'Prophylaxis Evaluation'
        verbose_name_plural = 'Prophylaxis Evaluations'
        ordering = ['-evaluation_time']

    def __str__(self):
        status = "Compliant" if self.bundle_compliant else "Non-compliant"
        if self.excluded:
            status = "Excluded"
        return f"{self.case.patient_mrn} - {status} ({self.compliance_score:.0f}%)"

    @property
    def element_results_list(self):
        """Return all element results as a list of (name, result) tuples."""
        return [
            ('Indication', self.indication_result),
            ('Agent Selection', self.agent_result),
            ('Pre-op Timing', self.timing_result),
            ('Dosing', self.dosing_result),
            ('Redosing', self.redosing_result),
            ('Post-op Continuation', self.postop_result),
            ('Discontinuation', self.discontinuation_result),
        ]


class ProphylaxisMedication(TimeStampedModel):
    """
    Prophylaxis medication orders and administrations for a surgical case.
    """
    MEDICATION_TYPE_CHOICES = [
        ('order', 'Order'),
        ('administration', 'Administration'),
    ]

    case = models.ForeignKey(
        SurgicalCase, on_delete=models.CASCADE, related_name='medications'
    )
    medication_type = models.CharField(max_length=20, choices=MEDICATION_TYPE_CHOICES)
    medication_name = models.CharField(max_length=255)
    dose_mg = models.FloatField()
    route = models.CharField(max_length=50, default='IV')
    event_time = models.DateTimeField(help_text="Order time or administration time")

    frequency = models.CharField(max_length=50, blank=True)
    duration_hours = models.FloatField(null=True, blank=True)
    infusion_end_time = models.DateTimeField(null=True, blank=True)
    order_id = models.CharField(max_length=255, blank=True)
    fhir_id = models.CharField(max_length=255, null=True, blank=True, unique=True)

    class Meta:
        db_table = 'prophylaxis_medications'
        verbose_name = 'Prophylaxis Medication'
        verbose_name_plural = 'Prophylaxis Medications'
        ordering = ['event_time']

    def __str__(self):
        return f"{self.medication_name} {self.dose_mg}mg ({self.medication_type})"


class ComplianceMetric(models.Model):
    """Aggregated compliance rates for dashboards and reporting."""
    PERIOD_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ]

    period_start = models.DateField()
    period_end = models.DateField()
    period_type = models.CharField(max_length=10, choices=PERIOD_TYPE_CHOICES)

    # Optional grouping dimensions
    procedure_category = models.CharField(max_length=30, blank=True)
    surgeon_id = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=100, blank=True)

    # Counts
    total_cases = models.IntegerField(default=0)
    excluded_cases = models.IntegerField(default=0)
    bundle_compliant_count = models.IntegerField(default=0)
    bundle_compliance_rate = models.FloatField(default=0.0)

    # Per-element rates
    indication_rate = models.FloatField(default=0.0)
    agent_rate = models.FloatField(default=0.0)
    timing_rate = models.FloatField(default=0.0)
    dosing_rate = models.FloatField(default=0.0)
    redosing_rate = models.FloatField(default=0.0)
    postop_rate = models.FloatField(default=0.0)
    discontinuation_rate = models.FloatField(default=0.0)

    class Meta:
        db_table = 'prophylaxis_compliance_metrics'
        verbose_name = 'Compliance Metric'
        verbose_name_plural = 'Compliance Metrics'
        ordering = ['-period_start']

    def __str__(self):
        return f"{self.period_type} {self.period_start} - {self.bundle_compliance_rate:.1f}%"


# --- Real-time Models ---

class SurgicalJourney(UUIDModel, TimeStampedModel):
    """
    Patient's path through the surgical workflow (state machine).

    Tracks location transitions, prophylaxis status, and alert state
    for real-time monitoring via HL7 ADT messages.
    """
    journey_id = models.CharField(max_length=50, unique=True)
    case = models.ForeignKey(
        SurgicalCase, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='journeys'
    )
    patient_mrn = models.CharField(max_length=100, db_index=True)
    patient_name = models.CharField(max_length=255, blank=True)
    procedure_description = models.CharField(max_length=500, blank=True)
    procedure_cpt_codes = models.JSONField(default=list)
    scheduled_time = models.DateTimeField(null=True, blank=True)

    # Current state
    current_state = models.CharField(
        max_length=20, choices=LocationState.choices,
        default=LocationState.UNKNOWN
    )

    # Prophylaxis status
    prophylaxis_indicated = models.BooleanField(null=True, blank=True)
    order_exists = models.BooleanField(default=False)
    administered = models.BooleanField(default=False)

    # Alert tracking
    alert_t24_sent = models.BooleanField(default=False)
    alert_t24_time = models.DateTimeField(null=True, blank=True)
    alert_t2_sent = models.BooleanField(default=False)
    alert_t2_time = models.DateTimeField(null=True, blank=True)
    alert_t60_sent = models.BooleanField(default=False)
    alert_t60_time = models.DateTimeField(null=True, blank=True)
    alert_t0_sent = models.BooleanField(default=False)
    alert_t0_time = models.DateTimeField(null=True, blank=True)

    # Exclusion
    is_emergency = models.BooleanField(default=False)
    already_on_therapeutic_abx = models.BooleanField(default=False)
    excluded = models.BooleanField(default=False)
    exclusion_reason = models.CharField(max_length=255, blank=True)

    # Completion
    completed_at = models.DateTimeField(null=True, blank=True)

    # FHIR/HL7 references
    fhir_appointment_id = models.CharField(max_length=255, blank=True)
    fhir_encounter_id = models.CharField(max_length=255, blank=True)
    hl7_visit_number = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'surgical_journeys'
        verbose_name = 'Surgical Journey'
        verbose_name_plural = 'Surgical Journeys'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['patient_mrn']),
            models.Index(fields=['current_state']),
            models.Index(fields=['scheduled_time']),
        ]

    def __str__(self):
        return f"{self.patient_mrn} - {self.get_current_state_display()}"


class PatientLocation(TimeStampedModel):
    """Location history from ADT messages for a patient."""
    patient_mrn = models.CharField(max_length=100, db_index=True)
    journey = models.ForeignKey(
        SurgicalJourney, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='locations'
    )
    location_code = models.CharField(max_length=100)
    location_state = models.CharField(
        max_length=20, choices=LocationState.choices,
        default=LocationState.UNKNOWN
    )
    event_time = models.DateTimeField()
    message_time = models.DateTimeField(null=True, blank=True)
    hl7_message_id = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'patient_locations'
        verbose_name = 'Patient Location'
        verbose_name_plural = 'Patient Locations'
        ordering = ['-event_time']

    def __str__(self):
        return f"{self.patient_mrn} @ {self.location_code} ({self.get_location_state_display()})"


class PreOpCheck(TimeStampedModel):
    """Compliance check result at a trigger point."""
    journey = models.ForeignKey(
        SurgicalJourney, on_delete=models.CASCADE, related_name='checks'
    )
    trigger_type = models.CharField(max_length=20, choices=AlertTrigger.choices)
    trigger_time = models.DateTimeField()

    prophylaxis_indicated = models.BooleanField(default=False)
    order_exists = models.BooleanField(default=False)
    administered = models.BooleanField(default=False)
    minutes_to_or = models.IntegerField(null=True, blank=True)

    alert_required = models.BooleanField(default=False)
    alert_severity = models.CharField(max_length=20, blank=True)
    recommendation = models.TextField(blank=True)

    alert = models.ForeignKey(
        Alert, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='preop_checks'
    )
    check_details = models.JSONField(default=dict)

    class Meta:
        db_table = 'preop_checks'
        verbose_name = 'Pre-Op Check'
        verbose_name_plural = 'Pre-Op Checks'
        ordering = ['-trigger_time']

    def __str__(self):
        return f"{self.journey.patient_mrn} - {self.get_trigger_type_display()}"


class AlertEscalation(TimeStampedModel):
    """Multi-level escalation tracking for real-time alerts."""
    alert_ref = models.CharField(max_length=255, help_text="Reference to Alert UUID")
    journey = models.ForeignKey(
        SurgicalJourney, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='escalations'
    )
    escalation_level = models.IntegerField(default=1)
    trigger_type = models.CharField(max_length=20, choices=AlertTrigger.choices)
    recipient_role = models.CharField(max_length=50)
    recipient_id = models.CharField(max_length=255, blank=True)
    recipient_name = models.CharField(max_length=255, blank=True)
    delivery_channel = models.CharField(max_length=50)
    sent_at = models.DateTimeField()
    delivery_status = models.CharField(max_length=20, default='pending')
    response_at = models.DateTimeField(null=True, blank=True)
    response_action = models.CharField(max_length=100, blank=True)
    response_by = models.CharField(max_length=255, blank=True)
    next_escalation_at = models.DateTimeField(null=True, blank=True)
    escalated = models.BooleanField(default=False)

    class Meta:
        db_table = 'alert_escalations'
        verbose_name = 'Alert Escalation'
        verbose_name_plural = 'Alert Escalations'
        ordering = ['-sent_at']

    def __str__(self):
        return f"Level {self.escalation_level} -> {self.recipient_role} ({self.delivery_status})"
