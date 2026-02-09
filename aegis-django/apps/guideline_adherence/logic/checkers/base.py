"""Base element checker for guideline adherence."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    """Result of checking a single bundle element."""

    element_id: str
    element_name: str
    status: str  # met, not_met, pending, na, unable
    value: str = ''
    notes: str = ''
    completed_at: Optional[datetime] = None
    deadline: Optional[datetime] = None


class ElementChecker(ABC):
    """Abstract base class for element checkers.

    All bundle element checkers inherit from this class and implement
    the check() method to evaluate whether a specific bundle element
    has been completed for a patient.
    """

    def __init__(self, fhir_client=None):
        """Initialize with optional FHIR client.

        Args:
            fhir_client: Client for FHIR data queries.
        """
        self.fhir_client = fhir_client

    @abstractmethod
    def check(self, element, patient_id: str, trigger_time: datetime, **kwargs) -> CheckResult:
        """Check whether an element has been completed.

        Args:
            element: BundleElement dataclass from bundles.py.
            patient_id: FHIR Patient resource ID.
            trigger_time: When the bundle was triggered.
            **kwargs: Additional context (age_days, episode_id, etc.).

        Returns:
            CheckResult with status and details.
        """
        pass

    def _calculate_deadline(
        self,
        trigger_time: datetime,
        time_window_hours: float | None,
    ) -> datetime | None:
        """Calculate the deadline for an element.

        Args:
            trigger_time: When the bundle was triggered.
            time_window_hours: Time window in hours.

        Returns:
            Deadline datetime or None if no window.
        """
        if time_window_hours is None:
            return None
        return trigger_time + timedelta(hours=time_window_hours)

    def _is_within_window(
        self,
        trigger_time: datetime,
        time_window_hours: float | None,
    ) -> bool:
        """Check if we are still within the time window.

        Args:
            trigger_time: When the bundle was triggered.
            time_window_hours: Time window in hours.

        Returns:
            True if still within window or no window defined.
        """
        if time_window_hours is None:
            return True
        from django.utils import timezone
        deadline = self._calculate_deadline(trigger_time, time_window_hours)
        return timezone.now() <= deadline

    def _create_result(
        self,
        element,
        status: str,
        trigger_time: datetime,
        value: str = '',
        notes: str = '',
        completed_at: datetime | None = None,
    ) -> CheckResult:
        """Create a CheckResult from element and status.

        Args:
            element: BundleElement dataclass.
            status: One of met, not_met, pending, na, unable.
            trigger_time: When the bundle was triggered.
            value: Value found (lab result, medication name, etc.).
            notes: Additional context notes.
            completed_at: When the element was completed.

        Returns:
            CheckResult instance.
        """
        return CheckResult(
            element_id=element.element_id,
            element_name=element.name,
            status=status,
            value=str(value) if value else '',
            notes=notes,
            completed_at=completed_at,
            deadline=self._calculate_deadline(trigger_time, element.time_window_hours),
        )
