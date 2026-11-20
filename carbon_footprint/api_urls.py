from django.urls import path

from . import api_views as v

app_name = "carbon_api"

urlpatterns = [
    path("options/", v.OptionsView.as_view(), name="options"),
    path("numbers/", v.NumbersView.as_view(), name="numbers"),
    path("estimates/", v.EstimateListCreateView.as_view(), name="estimates"),
    path("estimates/preview/", v.EstimatePreviewView.as_view(), name="preview"),
    path("estimates/<int:pk>/", v.EstimateDetailView.as_view(), name="estimate-detail"),
    path("analyzer/analysis/", v.AnalysisView.as_view(), name="analysis"),
    path("analyzer/factors/", v.FactorsView.as_view(), name="factors"),
    path("analyzer/factors/reset/", v.FactorsResetView.as_view(), name="factors-reset"),
]