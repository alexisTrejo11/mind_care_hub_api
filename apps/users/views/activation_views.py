from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema

from apps.users.serializers import EmailActivationSerializer, ActivationDataSerializer
from apps.core.decorators.error_handler import api_error_handler
from apps.core.responses.api_response import APIResponse
from apps.core.openapi import api_schema
from ..services.user_service import UserService
from apps.core.decorators.rate_limit import rate_limit


class EmailActivationView(APIView):
    """
    POST api/auth/activate/
    Activate user account via email token
    """

    permission_classes = [AllowAny]
    serializer_class = EmailActivationSerializer

    @extend_schema(
        **api_schema(
            tags=["Auth"],
            summary="Activate user account via email token",
            request=EmailActivationSerializer,
            data=ActivationDataSerializer,
            errors=(400, 429),
        )
    )
    @api_error_handler
    @rate_limit(profile="RESTRICTED", scope="email_activation")
    def post(self, request):
        """Activate user account via email token"""
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data["token"]

        userActivated = UserService.activate_user(token)
        userActivated.save(update_fields=["is_active"])

        return APIResponse.success(
            message="Account activated successfully! You can now log in.",
            data={"email": userActivated.email},
        )
