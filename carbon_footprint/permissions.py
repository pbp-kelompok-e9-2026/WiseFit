"""Permission DRF untuk area user dan Analyzer.

IsRegularUser: user biasa dan superuser. Akun Analyzer ditolak.
IsAnalyzerOrSuperuser: akun di grup Analyzer atau superuser.
"""
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission

from .access import can_open_analyzer, is_analyzer


class ApiSessionAuthentication(SessionAuthentication):
    """Legacy session authentication untuk API yang memang masih memakainya.

    Jangan gunakan class ini untuk endpoint Flutter. API carbon footprint
    menggunakan JWTAuthentication. Jangan menonaktifkan CSRF pada endpoint
    browser yang mengandalkan cookie session.
    """

    def authenticate_header(self, request):
        return "Session"


class IsRegularUser(BasePermission):
    message = "Akun Analyzer memakai ruang Analyzer, bukan halaman pribadi."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_superuser or not is_analyzer(user))
        )


class IsAnalyzerOrSuperuser(BasePermission):
    message = "Hanya akun Analyzer atau superuser yang boleh membuka ini."

    def has_permission(self, request, view):
        return can_open_analyzer(request.user)
