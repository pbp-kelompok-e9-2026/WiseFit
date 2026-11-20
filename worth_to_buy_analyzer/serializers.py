from dataclasses import asdict
from decimal import Decimal

from rest_framework import serializers

from .forms import ClothingReferenceForm, PurchaseAnalysisForm
from .models import ClothingReference, PurchaseAnalysis
from .services import analyze


class FormValidationMixin:
    form_class = None

    def validate(self, attrs):
        # Reuse the web form's cross-field rules, including material/weight and
        # PostgreSQL integer limits, without mutating the persisted instance.
        values = {
            name: getattr(self.instance, name)
            for name in self.form_class.Meta.fields
        } if self.instance else {}
        values.update(attrs)
        form = self.form_class(data=values)
        if not form.is_valid():
            raise serializers.ValidationError(form.errors)
        return attrs


class PurchaseAnalysisSerializer(FormValidationMixin, serializers.ModelSerializer):
    form_class = PurchaseAnalysisForm
    result = serializers.SerializerMethodField()
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    decision_label = serializers.CharField(source="get_decision_display", read_only=True)

    class Meta:
        model = PurchaseAnalysis
        fields = (
            "id", "clothing_name", "category", "category_label", "brand", "product_url",
            "material", "weight_kg", "existing_clothing", "purpose", "price", "budget",
            "expected_wears", "target_cpw", "wears_per_month", "decision", "decision_label",
            "decision_note", "decided_at", "carbon_kg_co2e", "carbon_reference",
            "carbon_source", "carbon_scope", "carbon_estimated_at", "rule_version",
            "created_at", "updated_at", "result",
        )
        read_only_fields = (
            "decision", "decision_note", "decided_at", "carbon_kg_co2e", "carbon_reference",
            "carbon_source", "carbon_scope", "carbon_estimated_at", "rule_version",
            "created_at", "updated_at",
        )

    def get_result(self, obj):
        result = asdict(analyze(obj))
        for key, value in result.items():
            if isinstance(value, Decimal):
                result[key] = str(value)
            elif isinstance(value, dict):
                result[key] = {name: str(amount) for name, amount in value.items()}
        return result


class DecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseAnalysis
        fields = ("decision", "decision_note")
        extra_kwargs = {"decision": {"required": True}}


class ClothingReferenceSerializer(FormValidationMixin, serializers.ModelSerializer):
    form_class = ClothingReferenceForm
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = ClothingReference
        fields = (
            "id", "clothing_name", "category", "category_label", "brand", "product_url",
            "price", "material", "weight_kg", "source_name", "notes", "is_published",
            "created_by", "updated_by", "created_at", "updated_at",
        )
        read_only_fields = ("created_by", "updated_by", "created_at", "updated_at")


class PublicationSerializer(serializers.Serializer):
    is_published = serializers.BooleanField(required=True)
