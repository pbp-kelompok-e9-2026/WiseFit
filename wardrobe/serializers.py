from rest_framework import serializers
from .models import ClothingItem

class ClothingItemSerializer(serializers.ModelSerializer):
    cost_per_wear = serializers.SerializerMethodField()

    class Meta:
        model = ClothingItem
        fields = [
            'id',
            'name',
            'category',
            'material',
            'price',
            'purchase_date',
            'image_url',
            'wear_count',
            'cost_per_wear',
            'created_at',
        ]
        read_only_fields = ['id', 'wear_count', 'cost_per_wear', 'created_at']

    def get_cost_per_wear(self, obj):
        return obj.calculate_cost_per_wear()