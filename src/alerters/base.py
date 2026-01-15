"""Base alerter interface."""

from abc import ABC, abstractmethod
from ..models import CoverageAssessment


class BaseAlerter(ABC):
    """Abstract base class for alerters."""

    @abstractmethod
    def send_alert(self, assessment: CoverageAssessment) -> bool:
        """
        Send an alert for inadequate coverage.

        Args:
            assessment: The coverage assessment that triggered the alert

        Returns:
            True if alert was sent successfully, False otherwise
        """
        pass

    @abstractmethod
    def get_alert_count(self) -> int:
        """Return the number of alerts sent."""
        pass
