"""
Alerts models for AEGIS Django.

Unified alert system for all AEGIS modules:
- HAI Detection (CLABSI, SSI, CAUTI, VAE, CDI)
- Dosing Verification
- Drug-Bug Mismatch
- ABX Approvals
- Guideline Adherence
- Surgical Prophylaxis
- MDRO Surveillance
- Outbreak Detection
"""

from django.db import models
from django.utils import timezone
from django.conf import settings

from apps.core.models import TimeStampedModel, UUIDModel, SoftDeletableModel


class AlertType(models.TextChoices):
    """
    Alert types for all AEGIS modules.
    """
    # HAI Detection
    CLABSI = 'clabsi', 'CLABSI Detection'
    SSI = 'ssi', 'SSI Detection'
    CAUTI = 'cauti', 'CAUTI Detection'
    VAE = 'vae', 'VAE Detection'
    CDI = 'cdi', 'CDI Detection'

    # Dosing Verification
    DOSING_ALLERGY = 'dosing_allergy', 'Dosing: Allergy Alert'
    DOSING_RENAL = 'dosing_renal', 'Dosing: Renal Adjustment Needed'
    DOSING_AGE = 'dosing_age', 'Dosing: Age-Based Alert'
    DOSING_WEIGHT = 'dosing_weight', 'Dosing: Weight-Based Alert'
    DOSING_INTERACTION = 'dosing_interaction', 'Dosing: Drug Interaction'
    DOSING_ROUTE = 'dosing_route', 'Dosing: Route Alert'
    DOSING_INDICATION = 'dosing_indication', 'Dosing: Indication Mismatch'
    DOSING_DURATION = 'dosing_duration', 'Dosing: Duration Alert'
    DOSING_EXTENDED_INFUSION = 'dosing_extended_infusion', 'Dosing: Extended Infusion Recommended'

    # Drug-Bug Mismatch
    DRUG_BUG_MISMATCH = 'drug_bug_mismatch', 'Drug-Bug Mismatch'
    CULTURE_NO_THERAPY = 'culture_no_therapy', 'Culture Without Therapy'

    # ABX Approvals
    ABX_APPROVAL_NEEDED = 'abx_approval_needed', 'ABX Approval Needed'
    ABX_REAPPROVAL_NEEDED = 'abx_reapproval_needed', 'ABX Re-approval Needed'

    # Guideline Adherence
    GUIDELINE_ADHERENCE = 'guideline_adherence', 'Guideline Adherence Alert'
    BUNDLE_INCOMPLETE = 'bundle_incomplete', 'Bundle Incomplete'

    # Surgical Prophylaxis
    SURGICAL_PROPHYLAXIS = 'surgical_prophylaxis', 'Surgical Prophylaxis Alert'

    # MDRO Surveillance
    MDRO_DETECTION = 'mdro_detection', 'MDRO Detection'

    # Outbreak Detection
    OUTBREAK_CLUSTER = 'outbreak_cluster', 'Outbreak Cluster Detected'

    # Bacteremia
    BACTEREMIA = 'bacteremia', 'Bacteremia Alert'

    # General
    BROAD_SPECTRUM_USAGE = 'broad_spectrum_usage', 'Broad Spectrum Usage'
    DUPLICATE_THERAPY = 'duplicate_therapy', 'Duplicate Therapy'
    OTHER = 'other', 'Other Alert'


class AlertStatus(models.TextChoices):
    """Alert status workflow."""
    PENDING = 'pending', 'Pending Review'
    SENT = 'sent', 'Sent to Provider'
    ACKNOWLEDGED = 'acknowledged', 'Acknowledged'
    IN_PROGRESS = 'in_progress', 'In Progress'
    SNOOZED = 'snoozed', 'Snoozed'
    RESOLVED = 'resolved', 'Resolved'
    EXPIRED = 'expired', 'Expired'


class AlertSeverity(models.TextChoices):
    """Alert severity levels."""
    INFO = 'info', 'Informational'
    LOW = 'low', 'Low Priority'
    MEDIUM = 'medium', 'Medium Priority'
    HIGH = 'high', 'High Priority'
    CRITICAL = 'critical', 'Critical'


class ResolutionReason(models.TextChoices):
    """Reasons for resolving alerts."""
    ACCEPTED = 'accepted', 'Recommendation Accepted'
    ALREADY_ADDRESSED = 'already_addressed', 'Already Addressed'
    CLINICALLY_INAPPROPRIATE = 'clinically_inappropriate', 'Clinically Inappropriate'
    PATIENT_DISCHARGED = 'patient_discharged', 'Patient Discharged'
    PATIENT_EXPIRED = 'patient_expired', 'Patient Expired'
    FALSE_POSITIVE = 'false_positive', 'False Positive'
    DUPLICATE = 'duplicate', 'Duplicate Alert'
    AUTO_RESOLVED = 'auto_resolved', 'Auto-Resolved'
    MESSAGED_TEAM = 'messaged_team', 'Messaged Team'
    DISCUSSED_WITH_TEAM = 'discussed_with_team', 'Discussed with Team'
    THERAPY_CHANGED = 'therapy_changed', 'Therapy Changed'
    THERAPY_STOPPED = 'therapy_stopped', 'Therapy Stopped'
    SUGGESTED_ALTERNATIVE = 'suggested_alternative', 'Suggested Alternative'
    CULTURE_PENDING = 'culture_pending', 'Culture Pending'
    OTHER = 'other', 'Other Reason'


class AlertManager(models.Manager):
    """Custom manager for Alert model with filtering methods."""

    def active(self):
        """Get all active (non-resolved, non-expired) alerts."""
        return self.filter(
            status__in=[
                AlertStatus.PENDING,
                AlertStatus.SENT,
                AlertStatus.ACKNOWLEDGED,
                AlertStatus.IN_PROGRESS,
                AlertStatus.SNOOZED
            ]
        )

    def actionable(self):
        """Get alerts that need action (not snoozed, not resolved)."""
        now = timezone.now()
        return self.filter(
            models.Q(status__in=[
                AlertStatus.PENDING,
                AlertStatus.SENT,
                AlertStatus.ACKNOWLEDGED,
                AlertStatus.IN_PROGRESS
            ]) |
            models.Q(status=AlertStatus.SNOOZED, snoozed_until__lte=now)
        )

    def by_type(self, alert_type):
        """Filter by alert type."""
        return self.filter(alert_type=alert_type)

    def by_severity(self, severity):
        """Filter by severity."""
        return self.filter(severity=severity)

    def by_patient(self, patient_mrn):
        """Filter by patient MRN."""
        return self.filter(patient_mrn=patient_mrn)

    def critical(self):
        """Get critical alerts."""
        return self.filter(severity=AlertSeverity.CRITICAL)

    def high_priority(self):
        """Get high priority or critical alerts."""
        return self.filter(severity__in=[AlertSeverity.HIGH, AlertSeverity.CRITICAL])


class Alert(UUIDModel, TimeStampedModel, SoftDeletableModel):
    """
    Unified alert model for all AEGIS modules.

    Stores alerts for:
    - HAI detection (CLABSI, SSI, CAUTI, VAE, CDI)
    - Dosing verification (allergy, renal, age, weight, etc.)
    - Drug-bug mismatch
    - ABX approvals
    - Guideline adherence
    - Surgical prophylaxis
    - MDRO surveillance
    - Outbreak detection
    """

    # Alert metadata
    alert_type = models.CharField(
        max_length=50,
        choices=AlertType.choices,
        db_index=True,
        help_text="Type of alert"
    )

    source_module = models.CharField(
        max_length=100,
        help_text="AEGIS module that generated this alert (e.g., 'hai_detection', 'dosing_verification')"
    )

    source_id = models.CharField(
        max_length=255,
        help_text="ID from source module (e.g., CLABSI candidate ID, dose alert ID)"
    )

    # Alert content
    title = models.CharField(
        max_length=500,
        help_text="Alert title (short summary)"
    )

    summary = models.TextField(
        help_text="Brief summary of the alert"
    )

    details = models.JSONField(
        default=dict,
        help_text="Full alert details (structure varies by alert type)"
    )

    # Patient information
    patient_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Patient ID from EHR"
    )

    patient_mrn = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Patient MRN"
    )

    patient_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Patient name (for display only)"
    )

    patient_location = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Patient location/unit"
    )

    # Severity and priority
    severity = models.CharField(
        max_length=20,
        choices=AlertSeverity.choices,
        default=AlertSeverity.MEDIUM,
        db_index=True,
        help_text="Alert severity"
    )

    priority_score = models.IntegerField(
        default=50,
        help_text="Priority score (0-100, higher = more urgent)"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=AlertStatus.choices,
        default=AlertStatus.PENDING,
        db_index=True,
        help_text="Current alert status"
    )

    # Timestamps
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When alert was sent to provider"
    )

    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When alert was acknowledged"
    )

    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='acknowledged_alerts',
        help_text="User who acknowledged the alert"
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When alert was resolved"
    )

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='resolved_alerts',
        help_text="User who resolved the alert"
    )

    resolution_reason = models.CharField(
        max_length=50,
        choices=ResolutionReason.choices,
        null=True,
        blank=True,
        help_text="Reason for resolution"
    )

    resolution_notes = models.TextField(
        null=True,
        blank=True,
        help_text="Notes about resolution"
    )

    # Snooze functionality
    snoozed_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Alert snoozed until this time"
    )

    snoozed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='snoozed_alerts',
        help_text="User who snoozed the alert"
    )

    # Notes and comments
    notes = models.TextField(
        null=True,
        blank=True,
        help_text="Internal notes about the alert"
    )

    # Expiration
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Alert expires at this time (auto-resolve)"
    )

    # Notification tracking
    notification_sent = models.BooleanField(
        default=False,
        help_text="Whether notification was sent"
    )

    notification_channels = models.JSONField(
        default=list,
        help_text="Channels where notification was sent (email, teams, sms)"
    )

    objects = AlertManager()

    class Meta:
        db_table = 'alerts'
        verbose_name = 'Alert'
        verbose_name_plural = 'Alerts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['alert_type', 'status']),
            models.Index(fields=['patient_mrn', 'status']),
            models.Index(fields=['severity', '-created_at']),
            models.Index(fields=['source_module', 'source_id']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.patient_mrn or 'No MRN'} - {self.get_status_display()}"

    @property
    def recommendations(self):
        """Get recommendations from details JSON."""
        if self.details and isinstance(self.details, dict):
            return self.details.get('recommendations')
        return None

    def create_audit_entry(self, action, user=None, old_status=None, new_status=None, ip_address=None, extra_details=None):
        """Create an audit log entry for this alert."""
        details = extra_details or {}
        return AlertAudit.objects.create(
            alert=self,
            action=action,
            performed_by=user,
            old_status=old_status,
            new_status=new_status,
            ip_address=ip_address,
            details=details,
        )

    def is_snoozed(self):
        """Check if alert is currently snoozed."""
        if self.status != AlertStatus.SNOOZED:
            return False
        if not self.snoozed_until:
            return False
        return timezone.now() < self.snoozed_until

    def is_actionable(self):
        """Check if alert needs action."""
        if self.status == AlertStatus.RESOLVED:
            return False
        if self.status == AlertStatus.EXPIRED:
            return False
        return not self.is_snoozed()

    def is_expired(self):
        """Check if alert has expired."""
        if not self.expires_at:
            return False
        return timezone.now() >= self.expires_at

    def acknowledge(self, user, ip_address=None):
        """Mark alert as acknowledged."""
        old_status = self.status
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = timezone.now()
        self.acknowledged_by = user
        self.save(update_fields=['status', 'acknowledged_at', 'acknowledged_by'])
        self.create_audit_entry(
            action='acknowledged',
            user=user,
            old_status=old_status,
            new_status=self.status,
            ip_address=ip_address,
        )

    def resolve(self, user, reason, notes=None, ip_address=None):
        """Mark alert as resolved."""
        old_status = self.status
        self.status = AlertStatus.RESOLVED
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.resolution_reason = reason
        if notes:
            self.resolution_notes = notes
        self.save(update_fields=['status', 'resolved_at', 'resolved_by', 'resolution_reason', 'resolution_notes'])
        self.create_audit_entry(
            action='resolved',
            user=user,
            old_status=old_status,
            new_status=self.status,
            ip_address=ip_address,
            extra_details={'reason': reason, 'notes': notes},
        )

    def snooze(self, user, until, ip_address=None):
        """Snooze alert until specified time."""
        old_status = self.status
        self.status = AlertStatus.SNOOZED
        self.snoozed_until = until
        self.snoozed_by = user
        self.save(update_fields=['status', 'snoozed_until', 'snoozed_by'])
        self.create_audit_entry(
            action='snoozed',
            user=user,
            old_status=old_status,
            new_status=self.status,
            ip_address=ip_address,
            extra_details={'snoozed_until': until.isoformat()},
        )

    def unsnooze(self):
        """Remove snooze status."""
        if self.status == AlertStatus.SNOOZED:
            self.status = AlertStatus.PENDING
            self.snoozed_until = None
            self.save(update_fields=['status', 'snoozed_until'])


class AlertAudit(TimeStampedModel):
    """
    Audit log for alert actions.

    Tracks all changes to alerts for HIPAA compliance.
    """

    alert = models.ForeignKey(
        Alert,
        on_delete=models.CASCADE,
        related_name='audit_log',
        help_text="Alert this audit entry belongs to"
    )

    action = models.CharField(
        max_length=50,
        help_text="Action performed (created, acknowledged, resolved, snoozed, etc.)"
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="User who performed the action"
    )

    performed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the action was performed"
    )

    old_status = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Status before action"
    )

    new_status = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Status after action"
    )

    details = models.JSONField(
        default=dict,
        help_text="Additional details about the action"
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of user who performed action"
    )

    class Meta:
        db_table = 'alert_audit'
        verbose_name = 'Alert Audit Entry'
        verbose_name_plural = 'Alert Audit Entries'
        ordering = ['-performed_at']
        indexes = [
            models.Index(fields=['alert', '-performed_at']),
            models.Index(fields=['performed_by', '-performed_at']),
            models.Index(fields=['action', '-performed_at']),
        ]

    def __str__(self):
        user_str = self.performed_by.username if self.performed_by else 'System'
        return f"{self.action} by {user_str} at {self.performed_at.strftime('%Y-%m-%d %H:%M:%S')}"
