from django.contrib.auth import get_user_model, password_validation
from rest_framework import serializers


class RegisterSerializer(serializers.ModelSerializer):
    """Serializer registrasi publik; hanya membuat akun user biasa."""

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
        password_validation.validate_password(attrs["password"], user=candidate_user)
        return attrs

    def create(self, validated_data):
        # create_user() meng-hash password. Field role/privilege tidak diterima.
        return get_user_model().objects.create_user(**validated_data)
