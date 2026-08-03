"""Factories that wrap payload serializers in the APIResponse envelope for OpenAPI."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Type, Union

from drf_spectacular.utils import OpenApiResponse, inline_serializer
from rest_framework import serializers

from .serializers import ErrorResponseSerializer, PaginationSerializer

SerializerType = Union[Type[serializers.Serializer], serializers.Serializer, serializers.Field]

_ERROR_DESCRIPTIONS = {
    400: "Bad request / validation error",
    401: "Authentication required or failed",
    403: "Permission denied",
    404: "Resource not found",
    429: "Rate limit exceeded",
    500: "Internal server error",
}

# Cache envelope serializers by component name so spectacular does not warn
# about identical names with different identities.
_COMPONENT_CACHE: Dict[str, Type[serializers.Serializer]] = {}


def _serializer_base_name(data: Optional[SerializerType], *, many: bool = False) -> str:
    if data is None:
        return "Empty"
    cls = data if isinstance(data, type) else data.__class__
    name = getattr(cls, "__name__", "Data").replace("Serializer", "")
    if name.endswith("Field"):
        name = name[: -len("Field")] or "Data"
    return f"{name}List" if many else name


def _resolve_data_field(
    data: Optional[SerializerType], *, many: bool
) -> serializers.Field:
    if data is None:
        return serializers.JSONField(required=False, allow_null=True)
    if isinstance(data, type):
        if issubclass(data, serializers.Serializer):
            return data(many=many)
        # Field subclass passed as type
        return data()
    if isinstance(data, serializers.BaseSerializer):
        return data
    # Already a Field instance (ListField, DictField, ...)
    return data


def _cached_inline(name: str, fields: Dict[str, Any]) -> Type[serializers.Serializer]:
    if name not in _COMPONENT_CACHE:
        _COMPONENT_CACHE[name] = inline_serializer(name=name, fields=fields)
    return _COMPONENT_CACHE[name]


def success_response(
    data: Optional[SerializerType] = None,
    *,
    many: bool = False,
    name: Optional[str] = None,
    description: str = "Successful response",
) -> OpenApiResponse:
    """Envelope: { status, message, data?, metadata? }."""
    base = name or _serializer_base_name(data, many=many)
    component_name = f"{base}Success"

    fields: Dict[str, Any] = {
        "status": serializers.ChoiceField(choices=["success"]),
        "message": serializers.CharField(),
        "data": _resolve_data_field(data, many=many),
        "metadata": serializers.DictField(required=False, allow_null=True),
    }

    return OpenApiResponse(
        response=_cached_inline(component_name, fields),
        description=description,
    )


def paginated_response(
    data: SerializerType,
    *,
    name: Optional[str] = None,
    description: str = "Paginated successful response",
) -> OpenApiResponse:
    """Envelope: { status, message, data[], pagination, metadata? }."""
    base = name or _serializer_base_name(data, many=True)
    component_name = f"{base}Paginated"

    fields: Dict[str, Any] = {
        "status": serializers.ChoiceField(choices=["success"]),
        "message": serializers.CharField(),
        "data": _resolve_data_field(data, many=True),
        "pagination": PaginationSerializer(),
        "metadata": serializers.DictField(required=False, allow_null=True),
    }

    return OpenApiResponse(
        response=_cached_inline(component_name, fields),
        description=description,
    )


def message_response(
    *,
    name: str = "MessageOnly",
    description: str = "Successful response with message only",
) -> OpenApiResponse:
    """Envelope without data payload (logout, delete, etc.)."""
    component_name = f"{name}Success"
    fields: Dict[str, Any] = {
        "status": serializers.ChoiceField(choices=["success"]),
        "message": serializers.CharField(),
        "metadata": serializers.DictField(required=False, allow_null=True),
    }
    return OpenApiResponse(
        response=_cached_inline(component_name, fields),
        description=description,
    )


def error_responses(
    *status_codes: int,
) -> Dict[int, OpenApiResponse]:
    """Map of standard error status codes to ErrorResponseSerializer."""
    codes: Sequence[int] = status_codes or (400, 401, 403, 404, 429)
    return {
        code: OpenApiResponse(
            response=ErrorResponseSerializer,
            description=_ERROR_DESCRIPTIONS.get(code, "Error"),
        )
        for code in codes
    }
