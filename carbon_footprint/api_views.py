from decimal import Decimal

from django.conf import settings
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .analysis import SOURCE_CHOICES, build_analysis, clean_filters
from .permissions import ApiSessionAuthentication, IsAnalyzerOrSuperuser, IsRegularUser
from .constants import CATEGORY_CHOICES, MATERIAL_CHOICES, PRICE_CURRENCY_LABEL
from .forms import reset_factors
from .models import CarbonEstimate
from .serializers import (
    CarbonEstimateSerializer,
    EstimateRowSerializer,
    FactorsInputSerializer,
    PreviewInputSerializer,
    build_factors_payload,
)
from .views import SORT_CHOICES, _filtered_rows, build_stats


class UserApiMixin:
    """Halaman pribadi user: user biasa dan superuser. Akun Analyzer ditolak."""
    authentication_classes = [ApiSessionAuthentication]
    permission_classes = [IsRegularUser]


class AnalyzerApiMixin:
    """Ruang Analyzer: akun grup Analyzer atau superuser."""
    authentication_classes = [ApiSessionAuthentication]
    permission_classes = [IsAnalyzerOrSuperuser]


class OptionsView(APIView):
    """Pilihan dropdown dan berat default per kategori, supaya Flutter tidak menyalin konstanta."""
    authentication_classes = [ApiSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        weights = services.current_category_weights()
        return Response({
            "materials": [{"value": v, "label": l} for v, l in MATERIAL_CHOICES],
            "categories": [{"value": v, "label": l, "default_weight_kg": weights.get(v)} for v, l in CATEGORY_CHOICES],
            "sorts": [{"value": v, "label": l} for v, l in SORT_CHOICES],
            "sources": [{"value": v, "label": l} for v, l in SOURCE_CHOICES],
            "currency": PRICE_CURRENCY_LABEL,
        })


# ---------- Halaman pribadi user ----------

class NumbersView(UserApiMixin, APIView):
    """Halaman Numbers untuk satu item (default: terbaru, atau ?item=<id>)."""

    def get(self, request):
        estimates = CarbonEstimate.objects.filter(user=request.user)
        item_id = request.query_params.get("item", "")
        item = estimates.filter(pk=item_id).first() if item_id.isdigit() else None
        item = item or estimates.first()
        stats = None
        if item:
            stats = build_stats(
                wears=item.estimated_wears,
                cost_per_wear=item.cost_per_wear,
                carbon_kg=float(item.co2e_kg),
                score=item.score,
            )
        return Response({
            "item": CarbonEstimateSerializer(item).data if item else None,
            "stats": stats,
            "items": [{"id": e["pk"], "name": e["name"]} for e in estimates.values("pk", "name")],
            "currency": PRICE_CURRENCY_LABEL,
        })


class EstimateListCreateView(UserApiMixin, APIView):
    """GET: daftar dengan ?q=, ?material=, ?sort=. POST: tambah estimasi."""

    def get(self, request):
        data = _filtered_rows(request, request.query_params)
        return Response({
            "results": EstimateRowSerializer(data["estimates"], many=True).data,
            "filters": data["filters"],
            "filtered": data["filtered"],
        })

    def post(self, request):
        serializer = CarbonEstimateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class EstimateDetailView(UserApiMixin, generics.RetrieveUpdateDestroyAPIView):
    """Data milik user lain otomatis 404 karena queryset difilter per user."""
    serializer_class = CarbonEstimateSerializer

    def get_queryset(self):
        return CarbonEstimate.objects.filter(user=self.request.user)


class EstimatePreviewView(UserApiMixin, APIView):
    """Pratinjau tanpa menyimpan dan tanpa memanggil Climatiq."""

    def post(self, request):
        serializer = PreviewInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        weight = d.get("weight_kg") or Decimal(str(services.category_weight(d["category"])))
        price = d.get("price")
        wears = d["estimated_wears"]
        co2e, _source = services.compute_co2e(d["material"], weight, None)
        return Response({
            "co2e": float(co2e),
            "weight": float(weight),
            "wears": wears,
            "cost_per_wear": float(price) / wears if price else None,
            "score": services.sustainability_score(co2e, wears),
            "will_use_climatiq": bool(price) and bool(getattr(settings, "CLIMATIQ_API_KEY", "")),
            "currency": PRICE_CURRENCY_LABEL,
        })


# ---------- Ruang Analyzer ----------

class AnalysisView(AnalyzerApiMixin, APIView):
    """Analisis gabungan, anonim, dengan filter ?material=, ?category=, ?source=."""

    def get(self, request):
        filters = clean_filters(request.query_params)
        return Response({
            "analysis": build_analysis(**filters),
            "filters": filters,
            "filtered": any(filters.values()),
        })


class FactorsView(AnalyzerApiMixin, APIView):
    def get(self, request):
        return Response(build_factors_payload())

    def put(self, request):
        serializer = FactorsInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save(request.user)
        message = "Faktor berhasil disimpan."
        if serializer.validated_data["recalculate"]:
            message += f" {updated} estimasi offline dihitung ulang."
        return Response({**build_factors_payload(), "recalculated": updated, "message": message})


class FactorsResetView(AnalyzerApiMixin, APIView):
    def post(self, request):
        reset_factors()
        return Response({**build_factors_payload(), "message": "Faktor dikembalikan ke nilai bawaan."})