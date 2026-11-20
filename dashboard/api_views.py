from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.auth import logout, authenticate

from .models import Profile
from .serializers import ProfileSerializer, DeleteAccountSerializer
from wardrobe.models import ClothingItem

# 1. API BUAT NGELIAT PROFIL & STATISTIK
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile_api_view(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    serializer = ProfileSerializer(profile)
    
    # Logic statistik dari views.py kamu tadi
    from django.db.models import Count, Sum
    TARGET_WEARS_PER_ITEM = 30
    totals = ClothingItem.objects.filter(user=request.user).aggregate(
        item_count=Count('id'),
        total_wears=Sum('wear_count'),
        total_spent=Sum('price'),
    )
    item_count = totals['item_count'] or 0
    wears = totals['total_wears'] or 0
    spent = float(totals['total_spent'] or 0)
    
    score = min(100, round(wears / item_count / TARGET_WEARS_PER_ITEM * 100)) if item_count else 0

    # Gabungin data profile + statistik
    data = serializer.data
    data['stats'] = {
        'wears_logged': wears,
        'avg_cost_per_wear': round(spent / wears) if wears else 0,
        'sustainability_score': score
    }
    return Response(data)


# 2. API BUAT EDIT PROFIL
@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def edit_profile_api_view(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    serializer = ProfileSerializer(profile, data=request.data, partial=True)
    
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Profile updated successfully", "data": serializer.data}, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 3. API BUAT HAPUS AKUN
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_account_api_view(request):
    serializer = DeleteAccountSerializer(data=request.data)
    
    if serializer.is_valid():
        password = serializer.validated_data['password']
        user = authenticate(username=request.user.username, password=password)
        
        if user is not None:
            logout(request)
            request.user.delete() # Hapus akun
            return Response({"message": "Account deleted successfully"}, status=status.HTTP_204_NO_CONTENT)
            
        return Response({"password": ["Password is incorrect."]}, status=status.HTTP_400_BAD_REQUEST)
        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)