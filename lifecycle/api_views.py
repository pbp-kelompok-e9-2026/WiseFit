from rest_framework import permissions, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import ConditionRecord
from .serializers import ConditionRecordSerializer
from .services import REPAIR_GUIDES, recommend


class ConditionRecordViewSet(viewsets.ModelViewSet):
    """CRUD catatan kondisi pakaian milik user yang login."""

    serializer_class = ConditionRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        records = ConditionRecord.objects.filter(user=self.request.user).select_related("item")

        # Filter opsional: ?recommendation=repair&status=pending
        recommendation = self.request.query_params.get("recommendation")
        status = self.request.query_params.get("status")
        if recommendation:
            records = records.filter(recommendation=recommendation)
        if status:
            records = records.filter(status=status)
        return records

    def perform_create(self, serializer):
        condition = serializer.validated_data["condition"]
        serializer.save(user=self.request.user, recommendation=recommend(condition))

    def perform_update(self, serializer):
        condition = serializer.validated_data.get("condition", serializer.instance.condition)
        serializer.save(recommendation=recommend(condition))


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def repair_guides(request):
    """Daftar panduan repair / reuse / recycle."""
    return Response(REPAIR_GUIDES)
