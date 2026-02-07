"""
Utility functions for AEGIS Django apps.

Common helper functions used across modules.
"""

from datetime import datetime, timedelta
from typing import Optional
from django.utils import timezone


def format_mrn(mrn: str) -> str:
    """
    Format MRN consistently (remove leading zeros, standardize format).

    Args:
        mrn: Medical record number

    Returns:
        Formatted MRN string
    """
    if not mrn:
        return ""
    # Remove leading zeros
    return str(int(mrn)) if mrn.isdigit() else mrn


def calculate_age_in_days(birth_date: datetime, reference_date: Optional[datetime] = None) -> int:
    """
    Calculate age in days from birth date.

    Args:
        birth_date: Patient's date of birth
        reference_date: Reference date (defaults to now)

    Returns:
        Age in days
    """
    if reference_date is None:
        reference_date = timezone.now()

    delta = reference_date - birth_date
    return delta.days


def calculate_age_display(birth_date: datetime, reference_date: Optional[datetime] = None) -> str:
    """
    Calculate age and return human-readable string (e.g., "3 days", "5 months", "2 years").

    Args:
        birth_date: Patient's date of birth
        reference_date: Reference date (defaults to now)

    Returns:
        Human-readable age string
    """
    days = calculate_age_in_days(birth_date, reference_date)

    if days < 1:
        return "< 1 day"
    elif days == 1:
        return "1 day"
    elif days < 30:
        return f"{days} days"
    elif days < 365:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''}"
    else:
        years = days // 365
        return f"{years} year{'s' if years != 1 else ''}"


def days_between(start_date: datetime, end_date: datetime) -> int:
    """
    Calculate days between two dates.

    Args:
        start_date: Start datetime
        end_date: End datetime

    Returns:
        Number of days between dates
    """
    delta = end_date - start_date
    return abs(delta.days)


def sanitize_patient_name(name: str) -> str:
    """
    Sanitize patient name (remove special characters, normalize).

    Args:
        name: Patient name

    Returns:
        Sanitized name
    """
    if not name:
        return ""
    # Remove extra whitespace
    name = " ".join(name.split())
    # Title case
    return name.title()


def get_current_user():
    """
    Get the current user from the request context.

    Used by audit logging middleware to track who performed actions.
    This is set by the AuditMiddleware.

    Returns:
        User object or None
    """
    # This will be implemented in authentication app
    # For now, return None
    return None


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate string to max length with suffix.

    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated string
    """
    if not text or len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
