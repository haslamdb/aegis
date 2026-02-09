"""
Django models for ABX Indication Monitoring.

Three custom models for the indication extraction → review workflow:
1. IndicationCandidate - One per antibiotic order, tracks LLM extraction + guideline match
2. IndicationReview - Pharmacist review of syndrome + agent appropriateness
3. IndicationLLMAuditLog - LLM call audit trail
"""

from django.db import models
from django.conf import settings

from apps.core.models import TimeStampedModel, UUIDModel


class SyndromeConfidence(models.TextChoices):
    """Confidence level for extracted clinical syndrome."""
    DEFINITE = 'definite', 'Definite'
    PROBABLE = 'probable', 'Probable'
    UNCLEAR = 'unclear', 'Unclear'


class TherapyIntent(models.TextChoices):
    """Why the antibiotic was started."""
    EMPIRIC = 'empiric', 'Empiric'
    DIRECTED = 'directed', 'Directed'
    PROPHYLAXIS = 'prophylaxis', 'Prophylaxis'
    UNKNOWN = 'unknown', 'Unknown'


class AgentCategoryChoice(models.TextChoices):
    """Agent appropriateness relative to CCHMC guideline."""
    FIRST_LINE = 'first_line', 'First Line'
    ALTERNATIVE = 'alternative', 'Alternative'
    OFF_GUIDELINE = 'off_guideline', 'Off Guideline'
    NOT_ASSESSED = 'not_assessed', 'Not Assessed'


class CandidateStatus(models.TextChoices):
    """Workflow status for indication candidates."""
    PENDING = 'pending', 'Pending Review'
    ALERTED = 'alerted', 'Alert Created'
    REVIEWED = 'reviewed', 'Reviewed'
    AUTO_ACCEPTED = 'auto_accepted', 'Auto-Accepted'


class SyndromeDecision(models.TextChoices):
    """Pharmacist decision on extracted syndrome."""
    CONFIRM_SYNDROME = 'confirm_syndrome', 'Confirm Syndrome'
    CORRECT_SYNDROME = 'correct_syndrome', 'Correct Syndrome'
    NO_INDICATION = 'no_indication', 'No Indication'
    VIRAL_ILLNESS = 'viral_illness', 'Viral Illness'
    ASYMPTOMATIC_BACTERIURIA = 'asymptomatic_bacteriuria', 'Asymptomatic Bacteriuria'


class AgentDecision(models.TextChoices):
    """Pharmacist decision on agent appropriateness."""
    APPROPRIATE = 'appropriate', 'Appropriate'
    ACCEPTABLE = 'acceptable', 'Acceptable'
    INAPPROPRIATE = 'inappropriate', 'Inappropriate'
    SKIP = 'skip', 'Skip'


class IndicationCandidate(UUIDModel, TimeStampedModel):
    """
    One record per antibiotic order — tracks LLM extraction results,
    CCHMC guideline match, and review status.

    Replaces SQLite indication_candidates table.
    """

    # Patient information
    patient_id = models.CharField(max_length=255, db_index=True)
    patient_mrn = models.CharField(max_length=100, db_index=True)
    patient_name = models.CharField(max_length=255, blank=True, default='')
    patient_location = models.CharField(max_length=255, blank=True, default='')

    # Medication order (FHIR MedicationRequest)
    medication_request_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="FHIR MedicationRequest ID (dedup key)",
    )
    medication_name = models.CharField(max_length=255)
    rxnorm_code = models.CharField(max_length=50, blank=True, default='')
    order_date = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True, default='')
    service = models.CharField(max_length=255, blank=True, default='')

    # Taxonomy extraction results
    clinical_syndrome = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Taxonomy ID (e.g., 'cap', 'uti_simple')",
    )
    clinical_syndrome_display = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Human-readable syndrome name",
    )
    syndrome_category = models.CharField(
        max_length=50, blank=True, default='',
        help_text="Category (respiratory, urinary, etc.)",
    )
    syndrome_confidence = models.CharField(
        max_length=20,
        choices=SyndromeConfidence.choices,
        default=SyndromeConfidence.UNCLEAR,
    )
    therapy_intent = models.CharField(
        max_length=20,
        choices=TherapyIntent.choices,
        default=TherapyIntent.UNKNOWN,
    )
    supporting_evidence = models.JSONField(
        default=list, blank=True,
        help_text="List of clinical findings",
    )
    evidence_quotes = models.JSONField(
        default=list, blank=True,
        help_text="Direct quotes from notes",
    )
    guideline_disease_ids = models.JSONField(
        default=list, blank=True,
        help_text="CCHMC disease IDs from taxonomy mapping",
    )

    # Red flags
    indication_not_documented = models.BooleanField(default=False)
    likely_viral = models.BooleanField(default=False)
    asymptomatic_bacteriuria = models.BooleanField(default=False)
    never_appropriate = models.BooleanField(default=False)

    # CCHMC guideline match
    cchmc_disease_matched = models.CharField(
        max_length=255, blank=True, default='',
    )
    cchmc_agent_category = models.CharField(
        max_length=20,
        choices=AgentCategoryChoice.choices,
        blank=True,
        default='',
    )
    cchmc_first_line_agents = models.JSONField(
        null=True, blank=True,
    )
    cchmc_recommendation = models.TextField(blank=True, default='')

    # Workflow
    status = models.CharField(
        max_length=20,
        choices=CandidateStatus.choices,
        default=CandidateStatus.PENDING,
        db_index=True,
    )
    alert = models.ForeignKey(
        'alerts.Alert',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='indication_candidates',
    )

    class Meta:
        db_table = 'abx_indication_candidates'
        verbose_name = 'Indication Candidate'
        verbose_name_plural = 'Indication Candidates'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['patient_mrn', '-created_at']),
            models.Index(fields=['medication_name', '-created_at']),
            models.Index(fields=['clinical_syndrome']),
            models.Index(fields=['cchmc_agent_category']),
        ]

    def __str__(self):
        return (
            f"{self.medication_name} - {self.patient_mrn} - "
            f"{self.clinical_syndrome_display or 'Unknown'} ({self.get_status_display()})"
        )

    @property
    def has_red_flag(self):
        """Check if any red flag is set."""
        return (
            self.indication_not_documented
            or self.likely_viral
            or self.asymptomatic_bacteriuria
            or self.never_appropriate
        )

    @property
    def latest_review(self):
        """Get the most recent review."""
        return self.reviews.order_by('-reviewed_at').first()


class IndicationReview(UUIDModel):
    """
    Pharmacist review of an indication candidate.

    Tracks syndrome confirmation, agent appropriateness decision,
    and override tracking.
    """

    candidate = models.ForeignKey(
        IndicationCandidate,
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    # Syndrome review
    syndrome_decision = models.CharField(
        max_length=30,
        choices=SyndromeDecision.choices,
    )
    confirmed_syndrome = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Corrected syndrome ID (if decision is correct_syndrome)",
    )
    confirmed_syndrome_display = models.CharField(
        max_length=255, blank=True, default='',
    )

    # Agent review
    agent_decision = models.CharField(
        max_length=20,
        choices=AgentDecision.choices,
        blank=True,
        default='',
    )
    agent_notes = models.TextField(blank=True, default='')

    # Override tracking
    is_override = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')

    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'abx_indication_reviews'
        verbose_name = 'Indication Review'
        verbose_name_plural = 'Indication Reviews'
        ordering = ['-reviewed_at']
        indexes = [
            models.Index(fields=['candidate', '-reviewed_at']),
            models.Index(fields=['syndrome_decision']),
        ]

    def __str__(self):
        reviewer_name = self.reviewer.username if self.reviewer else 'System'
        return f"Review by {reviewer_name} - {self.get_syndrome_decision_display()}"


class IndicationLLMAuditLog(models.Model):
    """
    Audit log for LLM API calls during indication extraction.

    Tracks model usage, token counts, response times, and errors.
    Same pattern as HAI detection LLMAuditLog.
    """

    candidate = models.ForeignKey(
        IndicationCandidate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='llm_calls',
    )

    model = models.CharField(max_length=200)
    success = models.BooleanField()
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    response_time_ms = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'abx_indication_llm_audit'
        verbose_name = 'LLM Audit Log Entry'
        verbose_name_plural = 'LLM Audit Log Entries'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['candidate', '-created_at']),
            models.Index(fields=['model']),
        ]

    def __str__(self):
        status = 'OK' if self.success else 'ERROR'
        return f"{self.model} [{status}] {self.input_tokens}+{self.output_tokens} tokens"
