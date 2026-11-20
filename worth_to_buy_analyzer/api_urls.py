from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api_views import CatalogueViewSet, OptionsView, PurchaseAnalysisViewSet, ReferenceViewSet

app_name = "worth_to_buy_api"
router = DefaultRouter()
router.register("analyses", PurchaseAnalysisViewSet, basename="analysis")
router.register("references", ReferenceViewSet, basename="reference")
router.register("catalogue", CatalogueViewSet, basename="catalogue")

urlpatterns = [
    path("options/", OptionsView.as_view(), name="options"),
    path("", include(router.urls)),
]
