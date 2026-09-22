from django.shortcuts import render

# Create your views here.
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import make_password
import requests
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .models import UserProfile
from django.conf import settings


from .serializers import UserSerializer, UserProfileSerializer, UserProfileSerializerForUpdate
from .request_serializers import SignUpRequestSerializer, SignInRequestSerializer, TokenRefreshRequestSerializer, UserProfileUpdateRequestSerializer

def set_token_on_response_cookie(user, status_code) -> Response:
    token = RefreshToken.for_user(user)
    user_profile = UserProfile.objects.get(user=user)
    serialized_data = UserProfileSerializer(user_profile).data
    res = Response(serialized_data, status=status_code)
    res.set_cookie("refresh_token", value=str(token), httponly=False, samesite="Lax", secure=False)
    res.set_cookie("access_token", value=str(token.access_token), httponly=False, samesite="Lax", secure=False)
    return res


class SignUpView(APIView):
    @swagger_auto_schema(
        operation_id="회원가입",
        operation_description="회원가입을 진행합니다.",
        request_body=SignUpRequestSerializer,
        responses={201: UserProfileSerializer, 400: "Bad Request"},
    )
    def post(self, request):
        user_serializer = UserSerializer(data=request.data)
        if user_serializer.is_valid(raise_exception=True):
            user_serializer.validated_data["password"] = make_password(
                user_serializer.validated_data["password"]
            )
            user = user_serializer.save()
            user.save()

        UserProfile.objects.create(
            user=user
        )

        return set_token_on_response_cookie(user, status_code=status.HTTP_201_CREATED)

class SignInView(APIView):
    @swagger_auto_schema(
        operation_id="로그인",
        operation_description="로그인을 진행합니다.",
        request_body=SignInRequestSerializer,
        responses={200: UserProfileSerializer, 404: "Not Found", 400: "Bad Request"},
    )
    def post(self, request):
        user = User.objects.filter(username=request.data["username"]).first()
        if user is None:
            return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        if not user.check_password(request.data["password"]):
            return Response({"message": "Invalid password"}, status=status.HTTP_401_UNAUTHORIZED)

        return set_token_on_response_cookie(user, status_code=status.HTTP_200_OK)
    
class TokenRefreshView(APIView):
    @swagger_auto_schema(
        operation_id="토큰 재발급",
        operation_description="access 토큰을 재발급 받습니다.",
        request_body=TokenRefreshRequestSerializer,
        responses={200: UserSerializer, 400: "Bad Request", 401: "Unauthorized"},
        manual_parameters=[openapi.Parameter("Authorization", openapi.IN_HEADER, description="access token", type=openapi.TYPE_STRING)]
    )
    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "no refresh token"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            RefreshToken(refresh_token).verify()
        except:
            return Response(
                {"detail": "please signin again."}, status=status.HTTP_401_UNAUTHORIZED
            )
        new_access_token = str(RefreshToken(refresh_token).access_token)
        response = Response({"detail": "token refreshed"}, status=status.HTTP_200_OK)
        response.set_cookie("access_token", value=str(new_access_token), httponly=False, samesite="Lax", secure=False)
        return response


class SignOutView(APIView):
    @swagger_auto_schema(
        operation_id="로그아웃",
        operation_description="로그아웃을 진행합니다.",
        responses={204: "No Content", 400: "Bad Request", 401: "Unauthorized"},
        manual_parameters=[openapi.Parameter("Authorization", openapi.IN_HEADER, description="access token", type=openapi.TYPE_STRING)]
    )
    def post(self, request):

        if not request.user.is_authenticated:
            return Response(
                {"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED
            )

        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "no refresh token"}, status=status.HTTP_400_BAD_REQUEST
            )
        RefreshToken(refresh_token).blacklist()

        return Response(status=status.HTTP_204_NO_CONTENT)

class UserProfileListView(APIView):
    @swagger_auto_schema(
        operation_id="유저 정보 확인",
        operation_description="등록된 모든 유저 정보를 가져옵니다",
        request_body=None,
        responses={200: UserProfileSerializer(many=True), 401: "please signin"},
        manual_parameters=[openapi.Parameter("Authorization", openapi.IN_HEADER, description="access token", type=openapi.TYPE_STRING)]
    )
    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)
        user_profile = UserProfile.objects.all()
        serializer = UserProfileSerializer(user_profile, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class UserProfileDetailView(APIView):
    @swagger_auto_schema(
        operation_id="유저 정보 확인",
        operation_description="토큰을 기반으로, 유저 세부 정보를 가져옵니다.",
        request_body=None,
        responses={200: UserProfileSerializer, 404: "UserProfile Not found.", 401: "please signin"},
        manual_parameters=[openapi.Parameter("Authorization", openapi.IN_HEADER, description="access token", type=openapi.TYPE_STRING)]
    )
    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            user_profile = UserProfile.objects.get(user=user)
            serializer = UserProfileSerializer(user_profile)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            return Response({"detail": "UserProfile Not found."}, status=status.HTTP_404_NOT_FOUND)
    
    @swagger_auto_schema(
        operation_id="유저 정보 수정",
        operation_description="유저 개인 프로필 정보(닉네임, 프로필 사진)를 수정합니다.",
        request_body=UserProfileUpdateRequestSerializer,
        responses={200: UserProfileSerializer, 400: "[profilepic_id, nickname] fields missing.", 401: "please signin", 404: "UserProfile Not found."},
        manual_parameters=[openapi.Parameter("Authorization", openapi.IN_HEADER, description="access token", type=openapi.TYPE_STRING)]
    )
    def put(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            user_profile = UserProfile.objects.get(user=user)
            profilepic_id = request.data.get("profilepic_id")
            nickname = request.data.get("nickname")
            if not nickname:
                return Response({"detail": "nickname field missing."}, status=status.HTTP_400_BAD_REQUEST)
            if profilepic_id is not None and profilepic_id not in range(1, 7):
                return Response({"detail": "profilepic_id must be between 1 and 6 or null."}, status=status.HTTP_400_BAD_REQUEST)
            user_profile.profilepic_id = profilepic_id
            user_profile.nickname = nickname
            user_profile.save()
            serializer = UserProfileSerializerForUpdate(user_profile)
            # if serializer.is_valid(raise_exception=True):
            #     serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            return Response({"detail": "UserProfile Not found."}, status=status.HTTP_404_NOT_FOUND)
        
class RemainingPointDeductView(APIView):
    @swagger_auto_schema(
        operation_id="포인트 차감",
        operation_description="유저가 경매 상품을 구매할 때, 보유 포인트를 차감합니다.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "point_to_deduct": openapi.Schema(
                    type=openapi.TYPE_INTEGER,
                    description="차감할 포인트",
                )
            },
        ),
        responses={200: UserProfileSerializer, 400: "point_to_deduct field missing.", 401: "please signin", 404: "UserProfile Not found."},
        manual_parameters=[openapi.Parameter("Authorization", openapi.IN_HEADER, description="access token", type=openapi.TYPE_STRING)]
    )
    def put(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "please signin"}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            user_profile = UserProfile.objects.get(user=user)
            remaining_points = user_profile.remaining_points
            point_to_deduct = request.data.get("point_to_deduct")
            if not point_to_deduct:
                return Response({"detail": "point_to_deduct field missing."}, status=status.HTTP_400_BAD_REQUEST)
            if remaining_points < point_to_deduct:
                return Response({"detail": "Not enough points."}, status=status.HTTP_400_BAD_REQUEST)
            user_profile.remaining_points -= point_to_deduct
            user_profile.save()
            serializer = UserProfileSerializerForUpdate(user_profile)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            return Response({"detail": "UserProfile Not found."}, status=status.HTTP_404_NOT_FOUND)


class CheckUsernameView(APIView):
    @swagger_auto_schema(
        operation_id="유저명 중복 확인",
        operation_description="유저명이 이미 존재하는지 확인합니다.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "username": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="중복을 확인할 유저명",
                )
            },
        ),
        responses={200: "Username is available", 400: "Username already exists"},
    )
    def post(self, request):
        username = request.data.get("username")
        if User.objects.filter(username=username).exists():
            return Response({"message": "Username already exists"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": "Username is available"}, status=status.HTTP_200_OK)

class KakaoSignInCallbackView(APIView):
    def get(self, request):
        return self._process_kakao_login(request)

    def post(self, request):
        return self._process_kakao_login(request)

    def _process_kakao_login(self, request):
        code = request.query_params.get("code")
        if not code:
            return Response(
                {"detail": "카카오 인가 코드가 없습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token_response = requests.post(
            "https://kauth.kakao.com/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.KAKAO_SECRET_KEY,
                "client_secret": settings.KAKAO_CLIENT_SECRET,
                "redirect_uri": settings.KAKAO_REDIRECT_URI,
                "code": code,
            },
            timeout=10,
        )

        if token_response.status_code != status.HTTP_200_OK:
            return Response(
                {"detail": "카카오 토큰 발급에 실패했습니다."},
                status=token_response.status_code,
            )

        access_token = token_response.json().get("access_token")
        if not access_token:
            return Response(
                {"detail": "카카오 access token이 없습니다."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        user_info_response = requests.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if user_info_response.status_code != status.HTTP_200_OK:
            return Response(
                {"detail": "카카오 사용자 정보를 가져오지 못했습니다."},
                status=user_info_response.status_code,
            )

        kakao_user_id = user_info_response.json().get("id")
        if not kakao_user_id:
            return Response(
                {"detail": "카카오 사용자 식별자가 없습니다."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        username = f"kakao_{kakao_user_id}"
        user = User.objects.filter(username=username).first()

        if user is None:
            user = User(username=username)
            user.set_unusable_password()
            user.save()
            UserProfile.objects.create(user=user, is_social_login=True)
        else:
            UserProfile.objects.get_or_create(
                user=user,
                defaults={"is_social_login": True},
            )

        return set_token_on_response_cookie(user, status.HTTP_200_OK)
