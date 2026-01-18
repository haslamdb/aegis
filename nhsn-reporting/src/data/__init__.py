"""Data access abstraction layer for clinical data sources."""

from .base import BaseNoteSource, BaseDeviceSource
from .factory import get_note_source, get_device_source

__all__ = ["BaseNoteSource", "BaseDeviceSource", "get_note_source", "get_device_source"]
