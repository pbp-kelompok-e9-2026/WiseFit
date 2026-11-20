from rest_framework import serializers

from .models import ConditionRecord


class ConditionRecordSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    condition_display = serializers.CharField(source="get_condition_display", read_only=True)
    recommendation_display = serializers.CharField(source="get_recommendation_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ConditionRecord
        fields = [
            "id",
            "item",
            "item_name",
            "condition",
            "condition_display",
            "damage_description",
            "notes",
            "recommendation",
            "recommendation_display",
            "status",
            "status_display",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "recommendation", "created_at", "updated_at"]

    def validate_item(self, item):
        request = self.context.get("request")
        if request and item.user_id != request.user.id:
            raise serializers.ValidationError("Pakaian ini bukan milikmu.")
        return item
