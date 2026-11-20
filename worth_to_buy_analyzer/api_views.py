from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from carbon_footprint.constants import MATERIAL_CHOICES

from .models import ClothingReference, PurchaseAnalysis
from .roles import is_analyzer
from .serializers import (
    ClothingReferenceSerializer, DecisionSerializer, PublicationSerializer,
    PurchaseAnalysisSerializer,
)
from .services import RULE_VERSION, refresh_carbon_snapshot


class PurchaseUserPermission(BasePermission):
    message = "Gunakan ruang Analyzer untuk mengelola referensi pakaian."

    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.user.is_superuser or not is_analyzer(request.user))


class AnalyzerPermission(BasePermission):
    message = "Fitur ini khusus akun Analyzer."

    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.user.is_superuser or is_analyzer(request.user))


class ModulePagination(PageNumberPagination):
    page_size = 12


class ModuleViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    pagination_class = ModulePagination
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]


class PurchaseAnalysisViewSet(ModuleViewSet):
    serializer_class = PurchaseAnalysisSerializer
    permission_classes = [IsAuthenticated, PurchaseUserPermission]

    def get_queryset(self):
        return PurchaseAnalysis.objects.filter(owner=self.request.user).order_by("-created_at", "-pk")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = PurchaseAnalysis(owner=request.user, rule_version=RULE_VERSION, **serializer.validated_data)
        notice = refresh_carbon_snapshot(item)
        item.save()
        return Response({**self.get_serializer(item).data, "notice": notice}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        item = self.get_object()
        serializer = self.get_serializer(item, data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        changed = {name for name, value in serializer.validated_data.items() if getattr(item, name) != value}
        for name, value in serializer.validated_data.items():
            setattr(item, name, value)
        notice = ""
        if {"material", "weight_kg", "price"} & changed:
            notice = refresh_carbon_snapshot(item)
        if changed:
            item.decision = PurchaseAnalysis.Decision.UNDECIDED
            item.decided_at = None
        item.rule_version = RULE_VERSION
        item.save()
        return Response({**self.get_serializer(item).data, "notice": notice})

    @action(detail=True, methods=["post"])
    def decision(self, request, pk=None):
        item = self.get_object()
        previous = item.decision
        serializer = DecisionSerializer(item, data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data["decision"]
        decided_at = item.decided_at
        if decision == PurchaseAnalysis.Decision.UNDECIDED:
            decided_at = None
        elif decision != previous or decided_at is None:
            decided_at = timezone.now()
        item = serializer.save(decided_at=decided_at)
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"], url_path="refresh-carbon")
    def refresh_carbon(self, request, pk=None):
        item = self.get_object()
        notice = refresh_carbon_snapshot(item)
        item.save(update_fields=[
            "carbon_kg_co2e", "carbon_reference", "carbon_source", "carbon_scope",
            "carbon_estimated_at", "updated_at",
        ])
        return Response({**self.get_serializer(item).data, "notice": notice})


def filter_references(queryset, params):
    query = params.get("q", "").strip()[:100]
    category = params.get("category", "")
    if query:
        queryset = queryset.filter(
            Q(clothing_name__icontains=query) | Q(brand__icontains=query) | Q(source_name__icontains=query)
        )
    if category:
        if category not in PurchaseAnalysis.Category.values:
            raise serializers.ValidationError({"category": ["Kategori tidak valid."]})
        queryset = queryset.filter(category=category)
    return queryset


class ReferenceViewSet(ModuleViewSet):
    serializer_class = ClothingReferenceSerializer
    permission_classes = [IsAuthenticated, AnalyzerPermission]

    def get_queryset(self):
        items = ClothingReference.objects.select_related("created_by", "updated_by").all()
        # Search and status are list filters, never a way to hide an object
        # from an update or a publication request.
        if self.action == "list":
            items = filter_references(items, self.request.query_params)
            publication = self.request.query_params.get("status", "")
            if publication in ("published", "draft"):
                items = items.filter(is_published=publication == "published")
        return items

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["post"])
    def publication(self, request, pk=None):
        serializer = PublicationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = self.get_object()
        item.is_published = serializer.validated_data["is_published"]
        item.updated_by = request.user
        item.save(update_fields=["is_published", "updated_by", "updated_at"])
        return Response(self.get_serializer(item).data)


class CatalogueViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    serializer_class = ClothingReferenceSerializer
    permission_classes = [IsAuthenticated, PurchaseUserPermission]
    pagination_class = ModulePagination

    def get_queryset(self):
        items = ClothingReference.objects.filter(is_published=True)
        return filter_references(items, self.request.query_params) if self.action == "list" else items


class OptionsView(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        choices = {
            "categories": PurchaseAnalysis.Category.choices,
            "existing_clothing": PurchaseAnalysis.ExistingClothing.choices,
            "purposes": PurchaseAnalysis.Purpose.choices,
            "decisions": PurchaseAnalysis.Decision.choices,
            "materials": MATERIAL_CHOICES,
        }
        return Response({name: [{"value": value, "label": label} for value, label in values]
                         for name, values in choices.items()})
