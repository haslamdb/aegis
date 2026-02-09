"""Serializers for the Auth API."""

from rest_framework import serializers

from apps.authentication.models import User


class UserProfileSerializer(serializers.ModelSerializer):
    """Current user profile serializer (read)."""

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'department', 'job_title', 'location',
            'email_notifications_enabled', 'teams_notifications_enabled',
        ]
        read_only_fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'department', 'job_title', 'location',
        ]


class UserPreferencesSerializer(serializers.Serializer):
    """Input for updating notification preferences."""
    email_notifications_enabled = serializers.BooleanField(required=False)
    teams_notifications_enabled = serializers.BooleanField(required=False)
