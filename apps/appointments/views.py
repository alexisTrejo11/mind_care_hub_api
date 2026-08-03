from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework import filters

from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view

from apps.core.decorators.error_handler import api_error_handler
from apps.core.decorators.rate_limit import rate_limit
from apps.core.permissions import IsSpecialistOrStaff
from apps.core.responses.api_response import APIResponse
from apps.core.openapi import api_schema

from .services import AppointmentService
from .models import Appointment
from .filters import AppointmentFilter
from .serializers import (
    AppointmentSerializer,
    AppointmentCreateSerializer,
    AppointmentUpdateSerializer,
    AppointmentRescheduleSerializer,
    AppointmentStatsSerializer,
)


@extend_schema_view(
    list=extend_schema(
        **api_schema(
            tags=["Appointments"],
            summary="List appointments",
            data=AppointmentSerializer,
            paginated=True,
            errors=(401, 429),
        )
    ),
    retrieve=extend_schema(
        **api_schema(
            tags=["Appointments"],
            summary="Get appointment details",
            data=AppointmentSerializer,
            errors=(401, 404, 429),
        )
    ),
    create=extend_schema(
        **api_schema(
            tags=["Appointments"],
            summary="Create appointment",
            request=AppointmentCreateSerializer,
            data=AppointmentSerializer,
            status_code=201,
            errors=(400, 401, 429),
        )
    ),
    update=extend_schema(
        **api_schema(
            tags=["Appointments", "Admin"],
            summary="Update appointment (specialist/staff)",
            request=AppointmentUpdateSerializer,
            data=AppointmentSerializer,
            errors=(400, 401, 403, 404, 429),
        )
    ),
    partial_update=extend_schema(
        **api_schema(
            tags=["Appointments", "Admin"],
            summary="Partial update appointment (specialist/staff)",
            request=AppointmentUpdateSerializer,
            data=AppointmentSerializer,
            errors=(400, 401, 403, 404, 429),
        )
    ),
    cancel=extend_schema(
        **api_schema(
            tags=["Appointments"],
            summary="Cancel appointment",
            data=AppointmentSerializer,
            errors=(400, 401, 404, 429),
        )
    ),
    reschedule=extend_schema(
        **api_schema(
            tags=["Appointments"],
            summary="Reschedule appointment",
            request=AppointmentRescheduleSerializer,
            data=AppointmentSerializer,
            errors=(400, 401, 404, 429),
        )
    ),
    stats=extend_schema(
        **api_schema(
            tags=["Appointments", "Stats"],
            summary="Get appointment statistics (specialist/staff)",
            data=AppointmentStatsSerializer,
            errors=(401, 403, 429),
        )
    ),
    today_appointments=extend_schema(
        **api_schema(
            tags=["Appointments", "Stats"],
            summary="Get today's appointments (specialist/staff)",
            data=AppointmentSerializer,
            many=True,
            errors=(401, 403, 429),
        )
    ),
)
class AppointmentViewSet(viewsets.ModelViewSet):
    """
    Unified ViewSet to handle all appointment operations.

    Provides comprehensive appointment management including:
    - Creating and scheduling appointments
    - Filtering appointments by date, status, specialist, and patient
    - Searching appointments by participant names or notes
    - Cancelling and rescheduling appointments
    - Retrieving appointment statistics and today's schedule
    """

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = AppointmentFilter

    search_fields = [
        "patient__first_name",
        "patient__last_name",
        "specialist__user__first_name",
        "specialist__user__last_name",
        "notes",
        "symptoms",
    ]

    ordering_fields = [
        "appointment_date",
        "start_time",
        "created_at",
        "duration_minutes",
    ]
    ordering = ["-appointment_date", "start_time"]

    def get_permissions(self):
        if self.action in ["stats", "today_appointments"]:
            return [IsAuthenticated(), IsSpecialistOrStaff()]
        elif self.action == "create":
            return [IsAuthenticated()]  # Any authenticated user can create
        elif self.action in ["update", "partial_update", "cancel", "reschedule"]:
            return [IsAuthenticated(), IsSpecialistOrStaff()]
        return [IsAuthenticated()]

    def get_queryset(self):
        """Get queryset with user-specific filtering"""
        queryset = AppointmentService.get_base_queryset()

        if getattr(self, "swagger_fake_view", False):
            return queryset.none()

        user = self.request.user

        if user.is_patient():
            queryset = queryset.filter(patient=user)
        elif user.is_specialist():
            if hasattr(user, "specialist_profile"):
                queryset = queryset.filter(specialist=user.specialist_profile)

        return queryset

    def get_serializer_class(self):
        """Return the appropriate serializer based on the action"""
        if self.action == "create":
            return AppointmentCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return AppointmentUpdateSerializer
        return AppointmentSerializer

    @api_error_handler
    @rate_limit(profile="READ_OPERATION", scope="appointment_list")
    def list(self, request, *args, **kwargs):
        """List appointments with filters"""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return APIResponse.from_paginated_response(
                self.paginator,
                serializer.data,
                message="Appointments retrieved successfully",
            )

        serializer = self.get_serializer(queryset, many=True)
        return APIResponse.success(
            message="Appointments retrieved successfully", data=serializer.data
        )

    @api_error_handler
    @rate_limit(profile="READ_OPERATION", scope="appointment_detail")
    def retrieve(self, request, *args, **kwargs):
        """Get appointment details"""
        instance = self.get_object()

        serializer = self.get_serializer(instance)
        return APIResponse.success(
            message="Appointment details retrieved", data=serializer.data
        )

    @api_error_handler
    @rate_limit(profile="WRITE_OPERATION", scope="appointment_create")
    def create(self, request, *args, **kwargs):
        """Create new appointment"""
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        appointment = AppointmentService.create_appointment(**serializer.validated_data)

        # AppointmentNotificationService.send_confirmation(appointment)

        return APIResponse.created(
            message="Appointment scheduled successfully",
            data=AppointmentSerializer(appointment).data,
        )

    @api_error_handler
    @rate_limit(profile="WRITE_OPERATION", scope="appointment_cancel")
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancel an appointment"""
        appointment = self.get_object()
        # Queryset filtering already ensures patients can only access their own appointments

        appointment = AppointmentService.cancel_appointment(
            appointment=appointment, cancelled_by=request.user
        )

        return APIResponse.success(
            message="Appointment cancelled successfully",
            data=AppointmentSerializer(appointment).data,
        )

    @api_error_handler
    @rate_limit(profile="WRITE_OPERATION", scope="appointment_reschedule")
    @action(detail=True, methods=["post"], url_path="reschedule")
    def reschedule(self, request, pk=None):
        """Reschedule an appointment"""
        appointment = self.get_object()

        serializer = AppointmentRescheduleSerializer(
            data=request.data, context={"request": request, "appointment": appointment}
        )
        serializer.is_valid(raise_exception=True)

        appointment = AppointmentService.reschedule_appointment(
            appointment=appointment, **serializer.validated_data
        )

        return APIResponse.success(
            message="Appointment rescheduled successfully",
            data=AppointmentSerializer(appointment).data,
        )

    @api_error_handler
    @rate_limit(profile="STANDARD", scope="appointment_stats")
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """Get appointment statistics"""
        stats_serializer = AppointmentStatsSerializer(data=request.query_params)
        stats_serializer.is_valid(raise_exception=True)

        specialist_id = None
        if request.user.is_specialist():
            if hasattr(request.user, "specialist_profile"):
                specialist_id = request.user.specialist_profile.id

        stats = AppointmentService.get_appointment_statistics(
            period=stats_serializer.validated_data["period"],
            specialist_id=specialist_id,
        )

        return APIResponse.success(
            message="Appointment statistics retrieved", data=stats
        )

    @api_error_handler
    @rate_limit(profile="STANDARD", scope="appointment_today")
    @action(detail=False, methods=["get"], url_path="today")
    def today_appointments(self, request):
        """Get today's appointments"""
        today = timezone.now().date()
        queryset = self.get_queryset().filter(appointment_date=today)

        # Group by status
        appointments_by_status = {
            "scheduled": [],
            "confirmed": [],
            "in_progress": [],
            "completed": [],
        }

        for appointment in queryset.order_by("start_time"):
            if appointment.status in appointments_by_status:
                serializer = AppointmentSerializer(appointment)
                appointments_by_status[appointment.status].append(serializer.data)

        return APIResponse.success(
            message=f"Today's appointments ({today})",
            data={
                "date": today.isoformat(),
                "appointments_by_status": appointments_by_status,
                "total_appointments": queryset.count(),
            },
        )
