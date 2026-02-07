"""Data models for unified metrics and activity tracking."""

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any
import json


class ActivityType(Enum):
    """Types of provider activities tracked."""
    REVIEW = "review"                    # Reviewing a candidate/alert
    ACKNOWLEDGMENT = "acknowledgment"    # Acknowledging an alert
    RESOLUTION = "resolution"            # Resolving/closing an alert
    INTERVENTION = "intervention"        # Direct intervention with care team
    EDUCATION = "education"              # Educational activity
    OVERRIDE = "override"                # Overriding an automated decision


class ModuleSource(Enum):
    """Source modules for activity tracking."""
    HAI = "hai"                          # HAI detection module
    ASP_ALERTS = "asp_alerts"            # Alert store / ASP alerts
    GUIDELINE_ADHERENCE = "guideline_adherence"  # Guideline adherence module
    ABX_INDICATIONS = "abx_indications"  # Antibiotic indications module
    DRUG_BUG = "drug_bug"                # Drug-bug mismatch module
    SURGICAL_PROPHYLAXIS = "surgical_prophylaxis"  # Surgical prophylaxis module
    ABX_APPROVALS = "abx_approvals"      # Antibiotic approvals module
    MDRO_SURVEILLANCE = "mdro_surveillance"  # MDRO surveillance module
    OUTBREAK_DETECTION = "outbreak_detection"  # Outbreak detection module
    NHSN_REPORTING = "nhsn_reporting"    # NHSN reporting module


class InterventionType(Enum):
    """Types of intervention sessions."""
    UNIT_ROUNDING = "unit_rounding"           # Regular unit rounds
    SERVICE_EDUCATION = "service_education"   # Education to a service team
    INDIVIDUAL_FEEDBACK = "individual_feedback"  # 1:1 provider feedback
    COMMITTEE = "committee"                   # Committee or meeting
    POLICY_UPDATE = "policy_update"           # Policy/protocol change
    ESCALATION = "escalation"                 # Escalation to leadership


class TargetType(Enum):
    """Types of intervention targets."""
    UNIT = "unit"              # Hospital unit/ward
    SERVICE = "service"        # Medical service
    PROVIDER = "provider"      # Individual provider
    DEPARTMENT = "department"  # Department


class TargetStatus(Enum):
    """Status workflow for intervention targets."""
    IDENTIFIED = "identified"    # Issue identified, not yet planned
    PLANNED = "planned"          # Intervention planned
    IN_PROGRESS = "in_progress"  # Intervention ongoing
    COMPLETED = "completed"      # Intervention completed
    DISMISSED = "dismissed"      # Issue dismissed (false positive, resolved itself)


class IssueType(Enum):
    """Types of issues that can trigger intervention targeting."""
    HIGH_INAPPROPRIATE_ABX = "high_inappropriate_abx"
    LOW_BUNDLE_ADHERENCE = "low_bundle_adherence"
    HIGH_HAI_RATE = "high_hai_rate"
    SLOW_ALERT_RESPONSE = "slow_alert_response"
    LOW_THERAPY_CHANGE_RATE = "low_therapy_change_rate"
    HIGH_BROAD_SPECTRUM_USAGE = "high_broad_spectrum_usage"
    HIGH_OVERRIDE_RATE = "high_override_rate"


@dataclass
class ProviderActivity:
    """A single provider activity record."""
    id: int | None = None
    provider_id: str | None = None
    provider_name: str | None = None
    provider_role: str | None = None

    activity_type: ActivityType | str = ActivityType.REVIEW
    module: ModuleSource | str = ModuleSource.ASP_ALERTS
    entity_id: str | None = None
    entity_type: str | None = None
    action_taken: str | None = None
    outcome: str | None = None

    patient_mrn: str | None = None
    location_code: str | None = None
    service: str | None = None

    duration_minutes: int | None = None
    performed_at: datetime = field(default_factory=datetime.now)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "provider_role": self.provider_role,
            "activity_type": self.activity_type.value if isinstance(self.activity_type, ActivityType) else self.activity_type,
            "module": self.module.value if isinstance(self.module, ModuleSource) else self.module,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "action_taken": self.action_taken,
            "outcome": self.outcome,
            "patient_mrn": self.patient_mrn,
            "location_code": self.location_code,
            "service": self.service,
            "duration_minutes": self.duration_minutes,
            "performed_at": self.performed_at.isoformat() if self.performed_at else None,
            "details": self.details,
        }

    @classmethod
    def from_row(cls, row) -> "ProviderActivity":
        """Create from database row."""
        details = {}
        if row["details"]:
            try:
                details = json.loads(row["details"])
            except (json.JSONDecodeError, TypeError):
                pass

        performed_at = row["performed_at"]
        if isinstance(performed_at, str):
            performed_at = datetime.fromisoformat(performed_at)

        return cls(
            id=row["id"],
            provider_id=row["provider_id"],
            provider_name=row["provider_name"],
            provider_role=row["provider_role"],
            activity_type=row["activity_type"],
            module=row["module"],
            entity_id=row["entity_id"],
            entity_type=row["entity_type"],
            action_taken=row["action_taken"],
            outcome=row["outcome"],
            patient_mrn=row["patient_mrn"],
            location_code=row["location_code"],
            service=row["service"],
            duration_minutes=row["duration_minutes"],
            performed_at=performed_at,
            details=details,
        )


@dataclass
class InterventionSession:
    """An education/outreach intervention session."""
    id: int | None = None
    session_type: InterventionType | str = InterventionType.UNIT_ROUNDING
    session_date: date = field(default_factory=date.today)

    target_type: TargetType | str = TargetType.UNIT
    target_id: str | None = None
    target_name: str | None = None

    topic: str | None = None
    attendees: list[str] = field(default_factory=list)
    notes: str | None = None

    related_alerts: list[str] = field(default_factory=list)
    related_targets: list[int] = field(default_factory=list)

    conducted_by: str | None = None

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "session_type": self.session_type.value if isinstance(self.session_type, InterventionType) else self.session_type,
            "session_date": self.session_date.isoformat() if self.session_date else None,
            "target_type": self.target_type.value if isinstance(self.target_type, TargetType) else self.target_type,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "topic": self.topic,
            "attendees": self.attendees,
            "notes": self.notes,
            "related_alerts": self.related_alerts,
            "related_targets": self.related_targets,
            "conducted_by": self.conducted_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_row(cls, row) -> "InterventionSession":
        """Create from database row."""
        attendees = []
        if row["attendees"]:
            try:
                attendees = json.loads(row["attendees"])
            except (json.JSONDecodeError, TypeError):
                pass

        related_alerts = []
        if row["related_alerts"]:
            try:
                related_alerts = json.loads(row["related_alerts"])
            except (json.JSONDecodeError, TypeError):
                pass

        related_targets = []
        if row["related_targets"]:
            try:
                related_targets = json.loads(row["related_targets"])
            except (json.JSONDecodeError, TypeError):
                pass

        session_date = row["session_date"]
        if isinstance(session_date, str):
            session_date = date.fromisoformat(session_date)

        created_at = row["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        updated_at = row["updated_at"]
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return cls(
            id=row["id"],
            session_type=row["session_type"],
            session_date=session_date,
            target_type=row["target_type"],
            target_id=row["target_id"],
            target_name=row["target_name"],
            topic=row["topic"],
            attendees=attendees,
            notes=row["notes"],
            related_alerts=related_alerts,
            related_targets=related_targets,
            conducted_by=row["conducted_by"],
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass
class DailySnapshot:
    """Daily aggregated metrics snapshot."""
    id: int | None = None
    snapshot_date: date = field(default_factory=date.today)

    # Alert metrics
    alerts_created: int = 0
    alerts_resolved: int = 0
    alerts_acknowledged: int = 0
    avg_time_to_ack_minutes: float | None = None
    avg_time_to_resolve_minutes: float | None = None

    # HAI metrics
    hai_candidates_created: int = 0
    hai_candidates_reviewed: int = 0
    hai_confirmed: int = 0
    hai_override_count: int = 0

    # Guideline adherence metrics
    bundle_episodes_active: int = 0
    bundle_alerts_created: int = 0
    bundle_adherence_rate: float | None = None

    # ABX indication metrics
    indication_reviews: int = 0
    appropriate_count: int = 0
    inappropriate_count: int = 0
    inappropriate_rate: float | None = None

    # Drug-Bug mismatch metrics
    drug_bug_alerts_created: int = 0
    drug_bug_alerts_resolved: int = 0
    drug_bug_therapy_changed_count: int = 0

    # MDRO surveillance metrics
    mdro_cases_identified: int = 0
    mdro_cases_reviewed: int = 0
    mdro_confirmed: int = 0

    # Outbreak detection metrics
    outbreak_clusters_active: int = 0
    outbreak_alerts_triggered: int = 0

    # Surgical prophylaxis metrics
    surgical_prophylaxis_cases: int = 0
    surgical_prophylaxis_compliant: int = 0
    surgical_prophylaxis_compliance_rate: float | None = None

    # LLM extraction accuracy metrics
    llm_extractions_total: int = 0
    llm_accepted_count: int = 0
    llm_modified_count: int = 0
    llm_overridden_count: int = 0
    llm_acceptance_rate: float | None = None
    llm_override_rate: float | None = None
    llm_avg_confidence: float | None = None

    # Human activity metrics
    total_reviews: int = 0
    unique_reviewers: int = 0
    total_interventions: int = 0

    # Breakdowns
    by_location: dict = field(default_factory=dict)
    by_service: dict = field(default_factory=dict)

    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "snapshot_date": self.snapshot_date.isoformat() if self.snapshot_date else None,
            "alerts_created": self.alerts_created,
            "alerts_resolved": self.alerts_resolved,
            "alerts_acknowledged": self.alerts_acknowledged,
            "avg_time_to_ack_minutes": self.avg_time_to_ack_minutes,
            "avg_time_to_resolve_minutes": self.avg_time_to_resolve_minutes,
            "hai_candidates_created": self.hai_candidates_created,
            "hai_candidates_reviewed": self.hai_candidates_reviewed,
            "hai_confirmed": self.hai_confirmed,
            "hai_override_count": self.hai_override_count,
            "bundle_episodes_active": self.bundle_episodes_active,
            "bundle_alerts_created": self.bundle_alerts_created,
            "bundle_adherence_rate": self.bundle_adherence_rate,
            "indication_reviews": self.indication_reviews,
            "appropriate_count": self.appropriate_count,
            "inappropriate_count": self.inappropriate_count,
            "inappropriate_rate": self.inappropriate_rate,
            "drug_bug_alerts_created": self.drug_bug_alerts_created,
            "drug_bug_alerts_resolved": self.drug_bug_alerts_resolved,
            "drug_bug_therapy_changed_count": self.drug_bug_therapy_changed_count,
            "mdro_cases_identified": self.mdro_cases_identified,
            "mdro_cases_reviewed": self.mdro_cases_reviewed,
            "mdro_confirmed": self.mdro_confirmed,
            "outbreak_clusters_active": self.outbreak_clusters_active,
            "outbreak_alerts_triggered": self.outbreak_alerts_triggered,
            "surgical_prophylaxis_cases": self.surgical_prophylaxis_cases,
            "surgical_prophylaxis_compliant": self.surgical_prophylaxis_compliant,
            "surgical_prophylaxis_compliance_rate": self.surgical_prophylaxis_compliance_rate,
            "llm_extractions_total": self.llm_extractions_total,
            "llm_accepted_count": self.llm_accepted_count,
            "llm_modified_count": self.llm_modified_count,
            "llm_overridden_count": self.llm_overridden_count,
            "llm_acceptance_rate": self.llm_acceptance_rate,
            "llm_override_rate": self.llm_override_rate,
            "llm_avg_confidence": self.llm_avg_confidence,
            "total_reviews": self.total_reviews,
            "unique_reviewers": self.unique_reviewers,
            "total_interventions": self.total_interventions,
            "by_location": self.by_location,
            "by_service": self.by_service,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_row(cls, row) -> "DailySnapshot":
        """Create from database row."""
        by_location = {}
        if row["by_location"]:
            try:
                by_location = json.loads(row["by_location"])
            except (json.JSONDecodeError, TypeError):
                pass

        by_service = {}
        if row["by_service"]:
            try:
                by_service = json.loads(row["by_service"])
            except (json.JSONDecodeError, TypeError):
                pass

        snapshot_date = row["snapshot_date"]
        if isinstance(snapshot_date, str):
            snapshot_date = date.fromisoformat(snapshot_date)

        created_at = row["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        def safe_get(key, default=0):
            """Safely get a column value, returning default if column doesn't exist."""
            try:
                val = row[key]
                return val if val is not None else default
            except (IndexError, KeyError):
                return default

        return cls(
            id=row["id"],
            snapshot_date=snapshot_date,
            alerts_created=row["alerts_created"] or 0,
            alerts_resolved=row["alerts_resolved"] or 0,
            alerts_acknowledged=row["alerts_acknowledged"] or 0,
            avg_time_to_ack_minutes=row["avg_time_to_ack_minutes"],
            avg_time_to_resolve_minutes=row["avg_time_to_resolve_minutes"],
            hai_candidates_created=row["hai_candidates_created"] or 0,
            hai_candidates_reviewed=row["hai_candidates_reviewed"] or 0,
            hai_confirmed=row["hai_confirmed"] or 0,
            hai_override_count=row["hai_override_count"] or 0,
            bundle_episodes_active=row["bundle_episodes_active"] or 0,
            bundle_alerts_created=row["bundle_alerts_created"] or 0,
            bundle_adherence_rate=row["bundle_adherence_rate"],
            indication_reviews=row["indication_reviews"] or 0,
            appropriate_count=row["appropriate_count"] or 0,
            inappropriate_count=row["inappropriate_count"] or 0,
            inappropriate_rate=row["inappropriate_rate"],
            drug_bug_alerts_created=safe_get("drug_bug_alerts_created"),
            drug_bug_alerts_resolved=safe_get("drug_bug_alerts_resolved"),
            drug_bug_therapy_changed_count=safe_get("drug_bug_therapy_changed_count"),
            mdro_cases_identified=safe_get("mdro_cases_identified"),
            mdro_cases_reviewed=safe_get("mdro_cases_reviewed"),
            mdro_confirmed=safe_get("mdro_confirmed"),
            outbreak_clusters_active=safe_get("outbreak_clusters_active"),
            outbreak_alerts_triggered=safe_get("outbreak_alerts_triggered"),
            surgical_prophylaxis_cases=safe_get("surgical_prophylaxis_cases"),
            surgical_prophylaxis_compliant=safe_get("surgical_prophylaxis_compliant"),
            surgical_prophylaxis_compliance_rate=safe_get("surgical_prophylaxis_compliance_rate", None),
            llm_extractions_total=safe_get("llm_extractions_total", 0),
            llm_accepted_count=safe_get("llm_accepted_count", 0),
            llm_modified_count=safe_get("llm_modified_count", 0),
            llm_overridden_count=safe_get("llm_overridden_count", 0),
            llm_acceptance_rate=safe_get("llm_acceptance_rate", None),
            llm_override_rate=safe_get("llm_override_rate", None),
            llm_avg_confidence=safe_get("llm_avg_confidence", None),
            total_reviews=row["total_reviews"] or 0,
            unique_reviewers=row["unique_reviewers"] or 0,
            total_interventions=row["total_interventions"] or 0,
            by_location=by_location,
            by_service=by_service,
            created_at=created_at,
        )


@dataclass
class InterventionTarget:
    """A unit/service/provider identified as needing intervention."""
    id: int | None = None

    target_type: TargetType | str = TargetType.UNIT
    target_id: str | None = None
    target_name: str | None = None

    issue_type: IssueType | str = IssueType.HIGH_INAPPROPRIATE_ABX
    issue_description: str | None = None

    priority_score: float | None = None
    priority_reason: str | None = None

    baseline_value: float | None = None
    target_value: float | None = None
    current_value: float | None = None

    metric_name: str | None = None
    metric_unit: str | None = None

    status: TargetStatus | str = TargetStatus.IDENTIFIED
    assigned_to: str | None = None

    identified_date: date = field(default_factory=date.today)
    planned_date: date | None = None
    started_date: date | None = None
    completed_date: date | None = None

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "target_type": self.target_type.value if isinstance(self.target_type, TargetType) else self.target_type,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "issue_type": self.issue_type.value if isinstance(self.issue_type, IssueType) else self.issue_type,
            "issue_description": self.issue_description,
            "priority_score": self.priority_score,
            "priority_reason": self.priority_reason,
            "baseline_value": self.baseline_value,
            "target_value": self.target_value,
            "current_value": self.current_value,
            "metric_name": self.metric_name,
            "metric_unit": self.metric_unit,
            "status": self.status.value if isinstance(self.status, TargetStatus) else self.status,
            "assigned_to": self.assigned_to,
            "identified_date": self.identified_date.isoformat() if self.identified_date else None,
            "planned_date": self.planned_date.isoformat() if self.planned_date else None,
            "started_date": self.started_date.isoformat() if self.started_date else None,
            "completed_date": self.completed_date.isoformat() if self.completed_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_row(cls, row) -> "InterventionTarget":
        """Create from database row."""

        def parse_date(val):
            if val is None:
                return None
            if isinstance(val, date):
                return val
            return date.fromisoformat(val)

        def parse_datetime(val):
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(val)

        return cls(
            id=row["id"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            target_name=row["target_name"],
            issue_type=row["issue_type"],
            issue_description=row["issue_description"],
            priority_score=row["priority_score"],
            priority_reason=row["priority_reason"],
            baseline_value=row["baseline_value"],
            target_value=row["target_value"],
            current_value=row["current_value"],
            metric_name=row["metric_name"],
            metric_unit=row["metric_unit"],
            status=row["status"],
            assigned_to=row["assigned_to"],
            identified_date=parse_date(row["identified_date"]),
            planned_date=parse_date(row["planned_date"]),
            started_date=parse_date(row["started_date"]),
            completed_date=parse_date(row["completed_date"]),
            created_at=parse_datetime(row["created_at"]),
            updated_at=parse_datetime(row["updated_at"]),
        )


@dataclass
class InterventionOutcome:
    """Pre/post comparison data for an intervention."""
    id: int | None = None
    target_id: int | None = None
    session_id: int | None = None

    pre_period_start: date | None = None
    pre_period_end: date | None = None
    pre_value: float | None = None
    pre_sample_size: int | None = None

    post_period_start: date | None = None
    post_period_end: date | None = None
    post_value: float | None = None
    post_sample_size: int | None = None

    absolute_change: float | None = None
    percent_change: float | None = None
    is_improvement: bool | None = None

    day_30_value: float | None = None
    day_60_value: float | None = None
    day_90_value: float | None = None
    sustained_improvement: bool | None = None

    p_value: float | None = None
    confidence_interval: dict | None = None

    notes: str | None = None

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "target_id": self.target_id,
            "session_id": self.session_id,
            "pre_period_start": self.pre_period_start.isoformat() if self.pre_period_start else None,
            "pre_period_end": self.pre_period_end.isoformat() if self.pre_period_end else None,
            "pre_value": self.pre_value,
            "pre_sample_size": self.pre_sample_size,
            "post_period_start": self.post_period_start.isoformat() if self.post_period_start else None,
            "post_period_end": self.post_period_end.isoformat() if self.post_period_end else None,
            "post_value": self.post_value,
            "post_sample_size": self.post_sample_size,
            "absolute_change": self.absolute_change,
            "percent_change": self.percent_change,
            "is_improvement": self.is_improvement,
            "day_30_value": self.day_30_value,
            "day_60_value": self.day_60_value,
            "day_90_value": self.day_90_value,
            "sustained_improvement": self.sustained_improvement,
            "p_value": self.p_value,
            "confidence_interval": self.confidence_interval,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_row(cls, row) -> "InterventionOutcome":
        """Create from database row."""

        def parse_date(val):
            if val is None:
                return None
            if isinstance(val, date):
                return val
            return date.fromisoformat(val)

        def parse_datetime(val):
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(val)

        confidence_interval = None
        if row["confidence_interval"]:
            try:
                confidence_interval = json.loads(row["confidence_interval"])
            except (json.JSONDecodeError, TypeError):
                pass

        return cls(
            id=row["id"],
            target_id=row["target_id"],
            session_id=row["session_id"],
            pre_period_start=parse_date(row["pre_period_start"]),
            pre_period_end=parse_date(row["pre_period_end"]),
            pre_value=row["pre_value"],
            pre_sample_size=row["pre_sample_size"],
            post_period_start=parse_date(row["post_period_start"]),
            post_period_end=parse_date(row["post_period_end"]),
            post_value=row["post_value"],
            post_sample_size=row["post_sample_size"],
            absolute_change=row["absolute_change"],
            percent_change=row["percent_change"],
            is_improvement=bool(row["is_improvement"]) if row["is_improvement"] is not None else None,
            day_30_value=row["day_30_value"],
            day_60_value=row["day_60_value"],
            day_90_value=row["day_90_value"],
            sustained_improvement=bool(row["sustained_improvement"]) if row["sustained_improvement"] is not None else None,
            p_value=row["p_value"],
            confidence_interval=confidence_interval,
            notes=row["notes"],
            created_at=parse_datetime(row["created_at"]),
            updated_at=parse_datetime(row["updated_at"]),
        )


@dataclass
class ProviderSession:
    """Tracks a provider's review session."""
    id: int | None = None
    session_id: str = ""
    provider_id: str | None = None
    provider_name: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_minutes: float | None = None
    alerts_reviewed: int = 0
    alerts_acknowledged: int = 0
    alerts_resolved: int = 0
    cases_reviewed: int = 0
    total_actions: int = 0
    module_breakdown: dict = field(default_factory=dict)
    modules_accessed: list[str] = field(default_factory=list)
    locations_covered: list[str] = field(default_factory=list)
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_minutes": self.duration_minutes,
            "alerts_reviewed": self.alerts_reviewed,
            "alerts_acknowledged": self.alerts_acknowledged,
            "alerts_resolved": self.alerts_resolved,
            "cases_reviewed": self.cases_reviewed,
            "total_actions": self.total_actions,
            "module_breakdown": self.module_breakdown,
            "modules_accessed": self.modules_accessed,
            "locations_covered": self.locations_covered,
            "status": self.status,
        }
