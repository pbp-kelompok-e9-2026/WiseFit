from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ClothingItem
from .serializers import ClothingItemSerializer

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def wardrobe_list(request):
    if request.method == 'GET':
        items = ClothingItem.objects.filter(user=request.user).order_by('-created_at')
        category = request.query_params.get('category', '').strip()
        if category:
            items = items.filter(category=category.upper())
        serializer = ClothingItemSerializer(items, many=True)
        return Response(serializer.data)

    serializer = ClothingItemSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def wardrobe_detail(request, item_id):
    item = get_object_or_404(ClothingItem, id=item_id, user=request.user)

    if request.method == 'GET':
        serializer = ClothingItemSerializer(item)
        return Response(serializer.data)

    if request.method == 'PATCH':
        serializer = ClothingItemSerializer(item, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    item.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def wardrobe_increment_wear(request, item_id):
    item = get_object_or_404(ClothingItem, id=item_id, user=request.user)
    item.wear_count += 1
    item.save()
    serializer = ClothingItemSerializer(item)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def wardrobe_decrement_wear(request, item_id):
    item = get_object_or_404(ClothingItem, id=item_id, user=request.user)
    if item.wear_count > 0:
        item.wear_count -= 1
        item.save()
    serializer = ClothingItemSerializer(item)
    return Response(serializer.data)