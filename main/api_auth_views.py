from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .api_auth_serializers import RegisterSerializer


class RegisterView(generics.CreateAPIView):
    """POST username/email/password; akun baru selalu user biasa."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []


class LogoutView(APIView):
    """Cabut refresh token yang dimiliki user yang sedang login."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        raw_refresh_token = request.data.get("refresh")
        if not raw_refresh_token:
            return Response(
                {"detail": "Refresh token diperlukan."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh_token = RefreshToken(raw_refresh_token)
            token_user_id = refresh_token.get("user_id")

            # User tidak boleh mencabut refresh token milik akun lain.
            if str(token_user_id) != str(request.user.pk):
                return Response(
                    {"detail": "Refresh token bukan milik user ini."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            refresh_token.blacklist()
        except TokenError:
            return Response(
                {"detail": "Refresh token tidak valid atau sudah dicabut."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(status=status.HTTP_205_RESET_CONTENT)
