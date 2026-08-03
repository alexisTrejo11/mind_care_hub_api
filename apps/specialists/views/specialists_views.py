from django.http import Http404
from datetime import datetime
from rest_framework import viewsets, serializers
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema_view, extend_schema

from apps.core.decorators.error_handler import api_error_handler
from apps.core.decorators.rate_limit import rate_limit
from apps.core.exceptions.base_exceptions import (
    NotFoundError,
    PrivacyError,
    ValidationError,
)
from apps.core.responses.api_response import APIResponse
from apps.core.openapi import api_schema
from apps.specialists.services.specialist_availability import (
    SpecialistAvailabilityUseCases,
)
from ..serializers import (
    SpecialistSerializer,
    SpecialistDetailSerializer,
    SpecialistCreateSerializer,
    SpecialistUpdateSerializer,
    SpecialistServiceSerializer,
)
from ..services import SpecialistsUseCases
from ..filters import SpecialistFilter
from apps.core.permissions import IsAdminOrStaff, IsSpecialistOrStaff


@extend_schema_view(
    list=extend_schema(
        **api_schema(
            tags=["Specialists"],
            summary="List specialists",
            description=(
                "Paginated list of healthcare specialists with filtering, "
                "search, and ordering via query string."
            ),
            data=SpecialistSerializer,
            paginated=True,
            errors=(400, 429),
        )
    ),
    retrieve=extend_schema(
        **api_schema(
            tags=["Specialists"],
            summary="Get specialist details",
            description=(
                "Detailed specialist profile including services and availability."
            ),
            data=SpecialistDetailSerializer,
            errors=(404, 429),
        )
    ),
    specialist_services=extend_schema(
        **api_schema(
            tags=["Specialists"],
            summary="List services offered by a specialist",
            data=SpecialistServiceSerializer,
            many=True,
            errors=(404, 429),
        )
    ),
    available_slots=extend_schema(
        **api_schema(
            tags=["Specialists"],
            summary="Available appointment slots for a date",
            data=serializers.ListField(child=serializers.DictField()),
            response_name="AvailableSlots",
            errors=(400, 404, 429),
        )
    ),
    by_specialization=extend_schema(
        **api_schema(
            tags=["Specialists"],
            summary="Specialists grouped by specialization",
            data=serializers.DictField(),
            response_name="SpecialistsBySpecialization",
            errors=(429,),
        )
    ),
)
class SpecialistPublicViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public read-only ViewSet for healthcare specialist profiles.

    Provides public access to specialist information including:
    - List specialists with advanced filtering and search
    - Retrieve specialist details
    - Get services offered by a specialist
    - Get available appointment slots
    - Get specialists grouped by specialization

    **Authentication:** Not required (AllowAny)
    **Rate Limiting:** Applied based on action type
    **Filtering:** All available filters are auto-documented in Swagger
    """

    queryset = SpecialistsUseCases.get_base_queryset_for_list()

    serializer_class = SpecialistSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = SpecialistFilter
    ordering_fields = [
        "rating",
        "consultation_fee",
        "years_experience",
    ]
    ordering = ["-rating"]

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == "retrieve":
            return SpecialistDetailSerializer
        return SpecialistSerializer

    @api_error_handler
    @rate_limit(profile="PUBLIC", scope="specialist_list")
    def list(self, request, *args, **kwargs):
        """List all active specialists with filtering, searching, and sorting"""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return APIResponse.from_paginated_response(
                self.paginator,
                serializer.data,
                message="Specialists retrieved successfully",
            )

        serializer = self.get_serializer(queryset, many=True)
        return APIResponse.success(
            message="Specialists retrieved successfully",
            data=serializer.data,
        )

    @api_error_handler
    @rate_limit(profile="PUBLIC", scope="specialist_detail")
    def retrieve(self, request, *args, **kwargs):
        """Retrieve detailed information about a specific specialist"""
        instance = self.get_object()

        detail_result = SpecialistsUseCases.get_specialist_detail(instance)
        specialist_data = detail_result["specialist"]
        stats = detail_result["stats"]

        serializer = self.get_serializer(specialist_data)
        data = serializer.data
        data["stats"] = stats

        return APIResponse.success(message="Specialist details retrieved", data=data)

    @api_error_handler
    @rate_limit(profile="PUBLIC", scope="specialist_services")
    @action(detail=True, methods=["get"], url_path="services")
    def specialist_services(self, request, pk=None):
        """Get all services offered by a specialist"""
        get_specialist_services = self.get_object()

        specialist_services = SpecialistsUseCases.get_specialist_services(
            get_specialist_services
        )
        serializer = SpecialistServiceSerializer(specialist_services, many=True)

        return APIResponse.success(
            message="Specialist services retrieved", data=serializer.data
        )

    @api_error_handler
    @rate_limit(profile="PUBLIC", scope="specialist_availability")
    @action(detail=True, methods=["get"], url_path="available-slots/(?P<date>[^/.]+)")
    def available_slots(self, request, pk=None, date=None):
        """Get available appointment time slots for a specialist on a specific date"""
        specialist = self.get_object()
        try:
            if not date:
                raise ValidationError(detail="Date parameter is required")
            date_obj = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise ValidationError(detail="Invalid date format. Use YYYY-MM-DD.")

        slots = SpecialistAvailabilityUseCases.get_specialist_availability_slots(
            specialist=specialist, date=date_obj
        )

        return APIResponse.success(message=f"Available slots for {date}", data=slots)

    @api_error_handler
    @rate_limit(profile="PUBLIC", scope="specialist_by_specialization")
    @action(detail=False, methods=["get"], url_path="summary/by-specialization")
    def by_specialization(self, request):
        """Get specialists grouped and ranked by their specialization"""
        result = SpecialistsUseCases.get_specialists_by_specialization()

        for specialization, data in result.items():
            if "top_specialists" in data:
                serializer = SpecialistSerializer(data["top_specialists"], many=True)
                data["top_specialists"] = serializer.data

        return APIResponse.success(
            message="Specialists summary grouped by specialization", data=result
        )


@extend_schema_view(
    create=extend_schema(
        **api_schema(
            tags=["Specialists", "Admin"],
            summary="Create specialist profile",
            description="Admin/staff only. User must exist and not already have a profile.",
            request=SpecialistCreateSerializer,
            data=SpecialistSerializer,
            status_code=201,
            errors=(400, 403, 429),
        )
    ),
    update=extend_schema(
        **api_schema(
            tags=["Specialists", "Admin"],
            summary="Update specialist profile",
            request=SpecialistUpdateSerializer,
            data=SpecialistSerializer,
            errors=(400, 403, 404, 429),
        )
    ),
    partial_update=extend_schema(
        **api_schema(
            tags=["Specialists", "Admin"],
            summary="Partially update specialist profile",
            request=SpecialistUpdateSerializer,
            data=SpecialistSerializer,
            errors=(400, 403, 404, 429),
        )
    ),
    destroy=extend_schema(
        **api_schema(
            tags=["Specialists", "Admin"],
            summary="Delete specialist profile",
            message_only=True,
            response_name="SpecialistDelete",
            errors=(403, 404, 429),
        )
    ),
    activate=extend_schema(
        **api_schema(
            tags=["Specialists", "Admin"],
            summary="Activate specialist",
            data=SpecialistSerializer,
            errors=(403, 404, 429),
        )
    ),
    deactivate=extend_schema(
        **api_schema(
            tags=["Specialists", "Admin"],
            summary="Deactivate specialist",
            data=SpecialistSerializer,
            errors=(403, 404, 429),
        )
    ),
    add_service=extend_schema(
        **api_schema(
            tags=["Specialists"],
            summary="Add service to specialist offerings",
            data=SpecialistServiceSerializer,
            status_code=201,
            errors=(400, 403, 404, 429),
        )
    ),
    remove_service=extend_schema(
        **api_schema(
            tags=["Specialists"],
            summary="Remove service from specialist offerings",
            message_only=True,
            response_name="SpecialistRemoveService",
            errors=(403, 404, 429),
        )
    ),
)
class SpecialistManagementViewSet(viewsets.ModelViewSet):
    """
    Admin/Management ViewSet for healthcare specialist profiles.

    Provides comprehensive management of specialist profiles including:
    - CRUD operations for specialist profiles
    - Service management (add/remove services)
    - Specialist activation and deactivation
    - Administrative oversight of all specialist accounts

    **Authentication:** Required - Admin, Staff, or Specialist ownership
    **Permissions:** IsAdminOrStaff for most operations, IsSpecialistOrStaff for updates
    **Rate Limiting:** Applied based on action type
    **Filtering:** All available filters are auto-documented in Swagger
    """

    queryset = SpecialistsUseCases.get_base_queryset_for_list()
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = SpecialistFilter
    ordering_fields = [
        "rating",
        "consultation_fee",
        "years_experience",
        "created_at",
    ]
    ordering = ["-created_at"]

    def get_permissions(self):
        """
        Set appropriate permission classes based on action.
        """
        if self.action in ["create", "destroy", "activate", "deactivate"]:
            return [IsAdminOrStaff()]
        elif self.action in ["update", "partial_update"]:
            return [IsSpecialistOrStaff()]
        elif self.action in ["add_service", "remove_service"]:
            return [IsSpecialistOrStaff()]
        return super().get_permissions()

    def get_queryset(self):
        """
        Filter queryset based on user permissions.
        Admins/staff see all specialists. Specialists see only their own.
        """
        queryset = super().get_queryset()

        if self.request.user.is_anonymous:
            return queryset.none()

        is_specialist = self.request.user.user_type == "specialist"
        is_activation_action = self.action in ["activate", "deactivate"]

        if is_specialist and not is_activation_action:
            if hasattr(self.request.user, "specialist_profile"):
                queryset = queryset.filter(id=self.request.user.specialist_profile.id)
            else:
                queryset = queryset.none()

        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == "create":
            return SpecialistCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return SpecialistUpdateSerializer
        return SpecialistSerializer

    def _check_ownership_permission(self, specialist):
        """
        Check if user has permission to modify specialist profile.
        Specialists can only modify their own, admins/staff can modify any.
        """
        if self.request.user.user_type == "specialist":
            if not hasattr(self.request.user, "specialist_profile"):
                raise PrivacyError("User is not an associated specialist")
            if self.request.user.specialist_profile.id != specialist.id:
                raise PrivacyError("Cannot modify another specialist's profile")

    @api_error_handler
    @rate_limit(profile="WRITE_OPERATION", scope="specialist_create")
    def create(self, request, *args, **kwargs):
        """Create a new specialist profile (admin/staff only)"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        specialist = SpecialistsUseCases.create_specialist(**serializer.validated_data)

        return APIResponse.created(
            message="Specialist profile created successfully",
            data=SpecialistSerializer(specialist).data,
        )

    @api_error_handler
    @rate_limit(profile="WRITE_OPERATION", scope="specialist_update")
    def update(self, request, *args, **kwargs):
        """Update a specialist's profile completely"""
        instance = self.get_object()

        self._check_ownership_permission(instance)

        serializer = self.get_serializer(instance, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)

        specialist = SpecialistsUseCases.update_specialist(
            specialist=instance, **serializer.validated_data
        )

        return APIResponse.success(
            message="Specialist profile updated successfully",
            data=SpecialistSerializer(specialist).data,
        )

    @api_error_handler
    @rate_limit(profile="WRITE_OPERATION", scope="specialist_update")
    def partial_update(self, request, *args, **kwargs):
        """Partially update a specialist's profile"""
        spcecialist = self.get_object()

        self._check_ownership_permission(spcecialist)

        serializer = self.get_serializer(spcecialist, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        specialist = SpecialistsUseCases.update_specialist(
            specialist=spcecialist, **serializer.validated_data
        )

        return APIResponse.success(
            message="Specialist profile updated successfully",
            data=SpecialistSerializer(specialist).data,
        )

    @api_error_handler
    @rate_limit(profile="WRITE_OPERATION", scope="specialist_delete")
    def destroy(self, request, *args, **kwargs):
        """Permanently delete a specialist profile (admin/staff only)"""
        try:
            instance = self.get_object()
        except Http404:
            raise NotFoundError("Specialist not found")

        SpecialistsUseCases.delete_specialist(
            specialist=instance, deleted_by=request.user
        )

        return APIResponse.success(message="Specialist profile deleted successfully")

    @api_error_handler
    @rate_limit(profile="WRITE_OPERATION", scope="specialist_activate")
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        """Activate a deactivated specialist (admin/staff only)"""
        specialist = self.get_object()

        specialist = SpecialistsUseCases.update_specialist(
            specialist=specialist,
            is_active=True,
            is_accepting_new_patients=True,
        )

        return APIResponse.success(
            message="Specialist activated successfully",
            data=SpecialistSerializer(specialist).data,
        )

    @api_error_handler
    @rate_limit(profile="WRITE_OPERATION", scope="specialist_deactivate")
    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        """Deactivate a specialist (soft delete - admin/staff only)"""
        specialist = self.get_object()

        specialist = SpecialistsUseCases.delete_specialist(
            specialist=specialist, deleted_by=request.user
        )

        return APIResponse.success(
            message="Specialist deactivated successfully",
            data=SpecialistSerializer(specialist).data,
        )

    @api_error_handler
    @rate_limit(profile="WRITE_OPERATION", scope="specialist_add_service")
    @action(detail=True, methods=["post"], url_path="add-service")
    def add_service(self, request, pk=None):
        """Add a service to specialist's offerings"""
        specialist = self.get_object()

        self._check_ownership_permission(specialist)

        service_id = request.data.get("service_id")
        price_override = request.data.get("price_override")

        if not service_id:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(detail="service_id is required")

        specialist_service = SpecialistsUseCases.add_service_to_specialist(
            specialist=specialist,
            service_id=service_id,
            price_override=price_override,
        )

        serializer = SpecialistServiceSerializer(specialist_service)

        return APIResponse.created(
            message="Service added to specialist successfully",
            data=serializer.data,
        )

    @api_error_handler
    @rate_limit(profile="WRITE_OPERATION", scope="specialist_remove_service")
    @action(
        detail=True, methods=["delete"], url_path=r"remove-service/(?P<service_id>\d+)"
    )
    def remove_service(self, request, pk=None, service_id=None):
        """Remove a service from specialist's offerings"""
        specialist = self.get_object()

        if self.request.user.is_specialist():
            self._check_ownership_permission(specialist)

        SpecialistsUseCases.remove_service_from_specialist(
            specialist=specialist, service_id=service_id
        )

        return APIResponse.success(
            message="Service removed from specialist's offerings successfully"
        )
