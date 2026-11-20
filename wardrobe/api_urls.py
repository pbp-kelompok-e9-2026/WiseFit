from django.urls import path
from . import api_views

app_name = 'wardrobe_api'

urlpatterns = [
    path('', api_views.wardrobe_list, name='wardrobe-list'),
    path('<uuid:item_id>/', api_views.wardrobe_detail, name='wardrobe-detail'),
    path('<uuid:item_id>/increment-wear/', api_views.wardrobe_increment_wear, name='wardrobe-increment-wear'),
    path('<uuid:item_id>/decrement-wear/', api_views.wardrobe_decrement_wear, name='wardrobe-decrement-wear'),
]