from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),

    # Autentikasi JSON untuk aplikasi mobile dikelola oleh aplikasi main.
    path("api/auth/", include("main.api_auth_urls")),

    path("", include("main.urls")),
    path("wardrobe/", include("wardrobe.urls")),
    path("api/wardrobe/", include("wardrobe.api_urls")),
    path("worth-to-buy/", include("worth_to_buy_analyzer.urls")),
    path("api/worth-to-buy/", include("worth_to_buy_analyzer.api_urls")),
    path("carbon/", include("carbon_footprint.urls")),
    path("api/carbon/", include("carbon_footprint.api_urls")),
    path("lifecycle/", include("lifecycle.urls")),
    path("api/lifecycle/", include("lifecycle.api_urls")),
    path("dashboard/", include("dashboard.urls")),
    path("api/dashboard/", include("dashboard.api_urls")),
]
