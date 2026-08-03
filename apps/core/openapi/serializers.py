"""OpenAPI-only serializers describing the APIResponse envelope contract."""

from rest_framework import serializers


class PaginationSerializer(serializers.Serializer):
    total = serializers.IntegerField(help_text="Total number of items")
    page = serializers.IntegerField(help_text="Current page number (1-based)")
    page_size = serializers.IntegerField(help_text="Number of items in this page")
    total_pages = serializers.IntegerField(help_text="Total number of pages")
    has_next = serializers.BooleanField()
    has_previous = serializers.BooleanField()


class ErrorResponseSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["error"])
    message = serializers.CharField()
    timestamp = serializers.DateTimeField()
    code = serializers.CharField(required=False, allow_null=True)
    errors = serializers.JSONField(required=False, allow_null=True)
    metadata = serializers.DictField(required=False, allow_null=True)
