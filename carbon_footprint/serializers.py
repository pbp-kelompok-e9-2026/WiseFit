from decimal import Decimal

from django.contrib.auth import get_user_model, password_validation
from django.db import transaction
from rest_framework import serializers

from .constants import (
    CATEGORY_CHOICES,
    CATEGORY_WEIGHT_KG,
    FALLBACK_KG_CO2E_PER_KG,
    MATERIAL_CHOICES,
)
from .forms import FactorsForm, _dec
from .models import CarbonEstimate, CategoryWeight, MaterialFactor
from .services import (
    SOURCE_FALLBACK,
    category_weight,
    compute_co2e,
    current_category_weights,
    current_material_rates,
)


class RegisterSerializer(serializers.ModelSerializer):
    """Serializer registrasi untuk Django User; tidak menerima field hak akses."""
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )
    email = serializers.EmailField(required=False, allow_blank=True)

    class Meta:
        model = get_user_model()
        fields = ["username", "email", "password"]

    def validate(self, attrs):
        user_model = get_user_model()
        candidate_user = user_model(
            username=attrs.get("username", ""),
            email=attrs.get("email", ""),
        )
        password_validation.validate_password(
            attrs["password"],
            user=candidate_user,
        )
        return attrs

    def create(self, validated_data):
        # create_user() memastikan password di-hash oleh Django.
        # Field privilege/group tidak pernah diterima dari request.
        return get_user_model().objects.create_user(**validated_data)


# Field yang memengaruhi emisi. Kalau salah satunya berubah, emisi dihitung ulang.
EMISSION_INPUTS = ("material", "category", "weight_kg", "price")


class CarbonEstimateSerializer(serializers.ModelSerializer):
    weight_kg = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        allow_null=True,
        coerce_to_string=False,
        help_text="Kosongkan untuk memakai berat rata-rata kategori.",
    )
    price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
        coerce_to_string=False,
    )
    co2e_kg = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        read_only=True,
        coerce_to_string=False,
    )
    cost_per_wear = serializers.FloatField(read_only=True, allow_null=True)
    score = serializers.IntegerField(read_only=True)

    class Meta:
        model = CarbonEstimate
        fields = [
            "id", "name", "category", "material", "weight_kg", "price",
            "estimated_wears", "co2e_kg", "source", "cost_per_wear",
            "score", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "source", "created_at", "updated_at"]

    def validate(self, attrs):
        # Berat kosong (atau null) memakai berat default kategori.
        # Pada PATCH tanpa key weight_kg, nilai lama dibiarkan.
        if attrs.get("weight_kg") is None and (
            "weight_kg" in attrs or not self.partial
        ):
            category = attrs.get("category") or (
                self.instance.category if self.instance else None
            )
            default = category_weight(category)
            if default is None:
                raise serializers.ValidationError(
                    {"category": "Kategori tidak dikenal."}
                )
            attrs["weight_kg"] = Decimal(str(default))
        return attrs

    def create(self, validated_data):
        obj = CarbonEstimate(**validated_data)
        obj.co2e_kg, obj.source = compute_co2e(
            obj.material,
            obj.weight_kg,
            obj.price,
        )
        obj.save()
        return obj

    def update(self, instance, validated_data):
        # Hitung ulang hanya kalau input emisi benar-benar berubah, supaya edit nama
        # atau jumlah wears tidak memanggil Climatiq lagi.
        changed = any(
            field in validated_data and getattr(instance, field) != validated_data[field]
            for field in EMISSION_INPUTS
        )
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if changed:
            instance.co2e_kg, instance.source = compute_co2e(
                instance.material,
                instance.weight_kg,
                instance.price,
            )
        instance.save()
        return instance


class EstimateRowSerializer(CarbonEstimateSerializer):
    """Versi untuk daftar: ditambah panjang batang relatif terhadap item terbesar."""

    bar_pct = serializers.IntegerField(read_only=True)

    class Meta(CarbonEstimateSerializer.Meta):
        fields = CarbonEstimateSerializer.Meta.fields + ["bar_pct"]


class PreviewInputSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=CATEGORY_CHOICES)
    material = serializers.ChoiceField(choices=MATERIAL_CHOICES)
    weight_kg = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=Decimal("0.01"),
        max_value=Decimal("1000"),
        required=False,
        allow_null=True,
    )
    price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        allow_null=True,
    )
    estimated_wears = serializers.IntegerField(
        min_value=1,
        max_value=100000,
        default=30,
    )


# ---------- Analyzer: faktor emisi ----------

class FactorsInputSerializer(serializers.Serializer):
    """Hanya key yang dikirim yang diubah. Nilai yang sama dengan bawaan menghapus barisnya."""

    materials = serializers.DictField(
        child=serializers.DecimalField(
            max_digits=7,
            decimal_places=2,
            min_value=Decimal("0.01"),
        ),
        required=False,
    )
    categories = serializers.DictField(
        child=serializers.DecimalField(
            max_digits=6,
            decimal_places=2,
            min_value=Decimal("0.01"),
        ),
        required=False,
    )
    recalculate = serializers.BooleanField(default=False)

    @staticmethod
    def _check_keys(value, allowed, label):
        unknown = set(value) - set(allowed)
        if unknown:
            raise serializers.ValidationError(
                f"{label} tidak dikenal: {', '.join(sorted(unknown))}"
            )
        return value

    def validate_materials(self, value):
        return self._check_keys(value, FALLBACK_KG_CO2E_PER_KG, "Material")

    def validate_categories(self, value):
        return self._check_keys(value, CATEGORY_WEIGHT_KG, "Kategori")

    @staticmethod
    def _apply(model, key_field, key, value_field, value, default, user):
        if value == default:
            model.objects.filter(**{key_field: key}).delete()
        else:
            model.objects.update_or_create(
                **{key_field: key},
                defaults={value_field: value, "updated_by": user},
            )

    def save(self, user):
        data = self.validated_data
        with transaction.atomic():
            for key, value in data.get("materials", {}).items():
                self._apply(
                    MaterialFactor,
                    "material",
                    key,
                    "kg_co2e_per_kg",
                    value,
                    _dec(FALLBACK_KG_CO2E_PER_KG[key]),
                    user,
                )
            for key, value in data.get("categories", {}).items():
                self._apply(
                    CategoryWeight,
                    "category",
                    key,
                    "weight_kg",
                    value,
                    _dec(CATEGORY_WEIGHT_KG[key]),
                    user,
                )
            return FactorsForm._recalculate() if data["recalculate"] else 0


def _factor_rows(choices, current, defaults):
    rows = []
    for key, label in choices:
        default = _dec(defaults[key])
        value = _dec(current.get(key, defaults[key]))
        rows.append({
            "key": key,
            "label": label,
            "value": float(value),
            "default": float(default),
            "changed": value != default,
        })
    return rows


def build_factors_payload():
    return {
        "materials": _factor_rows(
            MATERIAL_CHOICES,
            current_material_rates(),
            FALLBACK_KG_CO2E_PER_KG,
        ),
        "categories": _factor_rows(
            CATEGORY_CHOICES,
            current_category_weights(),
            CATEGORY_WEIGHT_KG,
        ),
        "offline_count": CarbonEstimate.objects.filter(source=SOURCE_FALLBACK).count(),
    }
