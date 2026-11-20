from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api_views import ConditionRecordViewSet, repair_guides

router = DefaultRouter()
router.register("records", ConditionRecordViewSet, basename="lifecycle-record")

urlpatterns = [
    path("guides/", repair_guides, name="lifecycle-guides"),
    path("", include(router.urls)),
]
