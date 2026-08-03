"""Thin wrapper around extend_schema that injects the APIResponse envelope."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from .responses import (
    error_responses,
    message_response,
    paginated_response,
    success_response,
)

DEFAULT_ERRORS = (400, 401, 403, 404, 429)


def api_schema(
    *,
    tags: Sequence[str],
    summary: str,
    request: Any = None,
    data: Any = None,
    many: bool = False,
    paginated: bool = False,
    status_code: int = 200,
    errors: Optional[Sequence[int]] = DEFAULT_ERRORS,
    description: Optional[str] = None,
    message_only: bool = False,
    responses: Optional[Dict[int, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Build kwargs for @extend_schema / extend_schema_view entries.

    Usage:
        @extend_schema(**api_schema(tags=["Auth"], summary="Login", request=..., data=...))
    """
    if responses is None:
        if message_only:
            success = message_response(name=kwargs.pop("response_name", "MessageOnly"))
        elif paginated:
            if data is None:
                raise ValueError("paginated=True requires data=...")
            success = paginated_response(data, name=kwargs.pop("response_name", None))
        else:
            success = success_response(
                data,
                many=many,
                name=kwargs.pop("response_name", None),
            )
        responses = {status_code: success}
        if errors:
            responses.update(error_responses(*errors))

    schema: Dict[str, Any] = {
        "tags": list(tags),
        "summary": summary,
        "responses": responses,
        **kwargs,
    }
    if request is not None:
        schema["request"] = request
    if description is not None:
        schema["description"] = description
    return schema
