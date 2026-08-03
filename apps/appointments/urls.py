from .views import AppointmentViewSet
from django.urls import path, include
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r"appointments", AppointmentViewSet, basename="appointment")

urlpatterns = [
    path("api/v2/", include(router.urls)),
]
