"""OpenAPI response payload shapes for auth endpoints (not used for validation)."""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer

from .profile_serializers import UserProfileSerializer


@extend_schema_serializer(component_name="JWTTokens")
class JWTTokensSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="JWT access token")
    refresh = serializers.CharField(help_text="JWT refresh token")


@extend_schema_serializer(component_name="LoginData")
class LoginDataSerializer(serializers.Serializer):
    user = UserProfileSerializer()
    tokens = JWTTokensSerializer()


@extend_schema_serializer(component_name="RegistrationData")
class RegistrationDataSerializer(serializers.Serializer):
    email = serializers.EmailField()
    user_id = serializers.IntegerField()
    user_type = serializers.CharField()


@extend_schema_serializer(component_name="ActivationData")
class ActivationDataSerializer(serializers.Serializer):
    email = serializers.EmailField()


@extend_schema_serializer(component_name="TokenRefreshData")
class TokenRefreshDataSerializer(serializers.Serializer):
    access_token = serializers.CharField()


@extend_schema_serializer(component_name="LogoutRequest")
class LogoutRequestSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(help_text="JWT refresh token to blacklist")
