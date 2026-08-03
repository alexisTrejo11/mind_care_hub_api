from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db import connection


class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                if result is None:
                    return Response({"status": "error"}, status=500)
                return Response({"status": "ok"}, status=200)
        except Exception as e:
            return Response({"status": "error"}, status=500)


class ApplicationDocumentationSchemaView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "name": "Mind Care Hub API",
                "version": "2.0.0",
                "description": "A comprehensive mental health support platform offering personalized",
            },
            status=200,
        )
