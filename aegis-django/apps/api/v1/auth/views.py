"""Views for the Auth API."""

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.permissions import IsPhysicianOrHigher
from apps.api.throttling import WriteRateThrottle

from .serializers import UserProfileSerializer, UserPreferencesSerializer


class CurrentUserView(APIView):
    """
    GET  /api/v1/auth/me/  — Current user profile
    PATCH /api/v1/auth/me/ — Update notification preferences
    """

    permission_classes = [IsPhysicianOrHigher]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserPreferencesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        updated_fields = []
        for field, value in serializer.validated_data.items():
            setattr(user, field, value)
            updated_fields.append(field)

        if updated_fields:
            user.save(update_fields=updated_fields)

        return Response(UserProfileSerializer(user).data)


class ObtainTokenView(APIView):
    """
    POST /api/v1/auth/token/ — Obtain or rotate API token.

    Expects username + password in request body.
    Deletes any existing token and issues a new one.
    """

    permission_classes = []  # Allow unauthenticated (login endpoint)
    throttle_classes = [WriteRateThrottle]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response(
                {'detail': 'username and password are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.contrib.auth import authenticate
        user = authenticate(request=request, username=username, password=password)

        if user is None:
            return Response(
                {'detail': 'Invalid credentials.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Rotate: delete old token, create new one
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)

        return Response({
            'token': token.key,
            'user_id': user.pk,
            'username': user.username,
            'role': user.role,
        })
