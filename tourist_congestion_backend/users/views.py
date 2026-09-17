from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from rest_framework import status as http_status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken as SimpleJWTRefreshToken

from places.models import Place

from .models import Favorite, Feedback, RefreshToken, User
from .serializers import (
    FavoriteCreateSerializer,
    FeedbackCreateSerializer,
    FeedbackSerializer,
    GoogleLoginSerializer,
    LoginSerializer,
    SignupSerializer,
)
from .utils import generate_random_nickname, hash_token

# 같은 사용자가 같은 장소에 같은 유형의 피드백을 다시 남길 수 있게 되기까지의 대기 시간.
# 정책 변경(3일, 일주일 등) 시 이 값만 조정한다.
FEEDBACK_COOLDOWN = timedelta(days=1)


def success_response(data=None, message='', status_code=http_status.HTTP_200_OK):
    return Response(
        {'success': True, 'data': data or {}, 'message': message},
        status=status_code,
    )


def error_response(message, status_code=http_status.HTTP_400_BAD_REQUEST):
    return Response(
        {'success': False, 'data': {}, 'message': message},
        status=status_code,
    )


def _unique_random_nickname():
    nickname = generate_random_nickname()
    while User.objects.filter(nickname=nickname).exists():
        nickname = generate_random_nickname()
    return nickname


def issue_tokens(user):
    # 계정당 세션 1개 정책: 새로 로그인하면 기존 refresh token은 모두 폐기한다.
    RefreshToken.objects.filter(user=user).delete()

    jwt_refresh = SimpleJWTRefreshToken.for_user(user)
    jwt_access = jwt_refresh.access_token

    RefreshToken.objects.create(
        user=user,
        token_hash=hash_token(str(jwt_refresh)),
        expires_at=timezone.now() + jwt_refresh.lifetime,
    )

    return {'access_token': str(jwt_access), 'refresh_token': str(jwt_refresh)}


class SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(serializer.errors)

        user = serializer.save()
        tokens = issue_tokens(user)
        return success_response(tokens, '회원가입이 완료되었습니다.', http_status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                '이메일 또는 비밀번호가 올바르지 않습니다.',
                http_status.HTTP_401_UNAUTHORIZED,
            )

        user = serializer.validated_data['user']
        tokens = issue_tokens(user)
        return success_response(tokens, '로그인되었습니다.')


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(serializer.errors)

        try:
            payload = google_id_token.verify_oauth2_token(
                serializer.validated_data['id_token'],
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )
        except ValueError:
            return error_response('구글 인증에 실패했습니다.', http_status.HTTP_401_UNAUTHORIZED)

        google_sub = payload['sub']
        email = payload.get('email')

        user = User.objects.filter(
            provider=User.Provider.GOOGLE,
            provider_user_id=google_sub,
        ).first()
        created = False

        if user is None:
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User(
                    email=email,
                    nickname=_unique_random_nickname(),
                    provider=User.Provider.GOOGLE,
                    provider_user_id=google_sub,
                    profile_image_url=payload.get('picture'),
                )
                user.set_unusable_password()
                user.save()
                created = True
            else:
                user.provider_user_id = google_sub
                user.save(update_fields=['provider_user_id'])

        tokens = issue_tokens(user)
        message = '회원가입이 완료되었습니다.' if created else '로그인되었습니다.'
        response_status = http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK
        return success_response(tokens, message, response_status)


class RefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        raw_refresh_token = request.data.get('refresh_token')
        if not raw_refresh_token:
            return error_response('refresh_token이 필요합니다.')

        try:
            jwt_refresh = SimpleJWTRefreshToken(raw_refresh_token)
        except TokenError:
            return error_response('유효하지 않은 refresh_token입니다.', http_status.HTTP_401_UNAUTHORIZED)

        stored = RefreshToken.objects.filter(
            token_hash=hash_token(raw_refresh_token),
            user_id=jwt_refresh['user_id'],
        ).first()

        if stored is None or stored.expires_at <= timezone.now():
            return error_response(
                '만료되었거나 폐기된 refresh_token입니다.',
                http_status.HTTP_401_UNAUTHORIZED,
            )

        access_token = jwt_refresh.access_token
        return success_response({'access_token': str(access_token)}, 'Access Token이 재발급되었습니다.')


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        RefreshToken.objects.filter(user=request.user).delete()
        return success_response(message='로그아웃되었습니다.')


class RandomNicknameView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return success_response({'nickname': _unique_random_nickname()})


class FavoriteListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        place_ids = list(
            Favorite.objects.filter(user=request.user)
            .order_by('-created_at')
            .values_list('place_id', flat=True)
        )
        return success_response({'place_ids': place_ids})

    def post(self, request):
        serializer = FavoriteCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(serializer.errors)

        place = Place.objects.get(id=serializer.validated_data['place_id'])
        favorite, created = Favorite.objects.get_or_create(user=request.user, place=place)

        message = '즐겨찾기에 추가되었습니다.' if created else '이미 즐겨찾기에 추가된 장소입니다.'
        status_code = http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK
        return success_response({'place_id': favorite.place_id}, message, status_code)


class FavoriteDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, place_id):
        favorite = Favorite.objects.filter(user=request.user, place_id=place_id).first()
        if favorite is None:
            return error_response('즐겨찾기 내역이 없습니다.', http_status.HTTP_404_NOT_FOUND)

        favorite.delete()
        return success_response(message='즐겨찾기가 삭제되었습니다.')


class FeedbackListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        feedbacks = Feedback.objects.filter(user=request.user).order_by('-created_at')
        return success_response({'feedbacks': FeedbackSerializer(feedbacks, many=True).data})

    def post(self, request):
        serializer = FeedbackCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(serializer.errors)

        data = serializer.validated_data
        already_submitted = Feedback.objects.filter(
            user=request.user,
            place_id=data['place_id'],
            feedback_type=data['feedback_type'],
            created_at__gt=timezone.now() - FEEDBACK_COOLDOWN,
        ).exists()
        if already_submitted:
            return error_response(
                '같은 장소에 같은 유형의 피드백은 하루에 한 번만 남길 수 있습니다.',
                http_status.HTTP_429_TOO_MANY_REQUESTS,
            )

        feedback = Feedback.objects.create(
            user=request.user,
            place_id=data['place_id'],
            feedback_type=data['feedback_type'],
            value=data.get('value'),
            memo=data.get('memo'),
        )
        return success_response(
            FeedbackSerializer(feedback).data,
            '피드백이 등록되었습니다.',
            http_status.HTTP_201_CREATED,
        )
