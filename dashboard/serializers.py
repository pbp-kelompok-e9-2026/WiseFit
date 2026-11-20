from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile

class ProfileSerializer(serializers.ModelSerializer):
    # Ambil data dari model User bawaan Django
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)
    email = serializers.EmailField(source='user.email', required=False)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Profile
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'address']

    def update(self, instance, validated_data):
        # Handle update untuk relasi ke model User
        user_data = validated_data.pop('user', {})
        user = instance.user
        
        if 'first_name' in user_data:
            user.first_name = user_data['first_name']
        if 'last_name' in user_data:
            user.last_name = user_data['last_name']
        if 'email' in user_data:
            user.email = user_data['email']
        user.save()
        
        return super().update(instance, validated_data)


class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})