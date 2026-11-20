"""Izin akses API. Aturannya sama dengan versi web (access.py), hanya dalam bentuk permission class DRF.

- IsRegularUser: user biasa dan superuser. Akun Analyzer ditolak (403), seperti `user_pages_only`.
- IsAnalyzerOrSuperuser: akun di grup Analyzer atau superuser, seperti `analyzer_required`.
- Yang belum login mendapat 401 (bukan 403), supaya Flutter bisa membedakan "belum login" dan "tidak boleh".
"""
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission

from .access import can_open_analyzer, is_analyzer


class ApiSessionAuthentication(SessionAuthentication):
    """Login lewat session/cookie Django, sama seperti situs web.

    Pengecekan CSRF dimatikan untuk API ini karena aplikasi mobile tidak memakai form Django.
    authenticate_header() membuat DRF membalas 401 untuk permintaan tanpa login.
    """

    def enforce_csrf(self, request):
        return None

    def authenticate_header(self, request):
        return "Session"


class IsRegularUser(BasePermission):
    message = "Akun Analyzer memakai ruang Analyzer, bukan halaman pribadi."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and not is_analyzer(user))


class IsAnalyzerOrSuperuser(BasePermission):
    message = "Hanya akun Analyzer atau superuser yang boleh membuka ini."

    def has_permission(self, request, view):
        return can_open_analyzer(request.user)