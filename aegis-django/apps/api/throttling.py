"""
DRF throttling classes for AEGIS API.

Separate read/write rates to allow higher read throughput
while protecting write endpoints from abuse.
"""

from rest_framework.throttling import UserRateThrottle


class ReadRateThrottle(UserRateThrottle):
    scope = 'read'


class WriteRateThrottle(UserRateThrottle):
    scope = 'write'
