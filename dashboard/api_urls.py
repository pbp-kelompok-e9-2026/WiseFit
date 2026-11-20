from django.urls import path
from . import api_views

app_name = 'dashboard_api'

urlpatterns = [
    path('profile/', api_views.profile_api_view, name='profile_api'),
    path('profile/edit/', api_views.edit_profile_api_view, name='edit_profile_api'),
    path('profile/delete/', api_views.delete_account_api_view, name='delete_account_api'),
]