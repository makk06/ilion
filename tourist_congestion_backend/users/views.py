from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from rest_framework import status as http_status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken as SimpleJWTRefreshToken
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.utils import get_md5_hash_password

from places.models import Place

from .models import Favorite, Feedback, RefreshToken, User, WithdrawnEmailHash
from .serializers import (
    FavoriteCreateSerializer,
    FeedbackCreateSerializer,
    FeedbackSerializer,
    GoogleLoginSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    SignupSerializer,
    WithdrawSerializer,
)
from .utils import generate_random_nickname, hash_token, hash_email_for_withdrawal
from .withdrawal import WITHDRAWAL_GRACE_PERIOD

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


@transaction.atomic
def issue_tokens(user):
    # Serialize session creation against withdrawal/purge, including stale callers.
    user = User.objects.select_for_update().filter(pk=user.pk).first()
    if user is None or not user.is_active:
        raise AuthenticationFailed('로그인할 수 없는 계정입니다.')
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


def verify_google_identity(raw_id_token):
    """구글 id_token을 검증해 payload를 돌려준다. 실패하면 None."""
    try:
        return google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError:
        return None


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
            # authenticate()는 is_active가 False인 탈퇴 유예 계정도 거부한다.
            # 본인이 맞다면 일반 401 대신 복구 안내를 준다.
            pending = _pending_withdrawal_account(request.data)
            if pending is not None:
                return _withdrawal_pending_response(pending)
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

        payload = verify_google_identity(serializer.validated_data['id_token'])
        if payload is None:
            return error_response('구글 인증에 실패했습니다.', http_status.HTTP_401_UNAUTHORIZED)

        google_sub = payload['sub']
        email = payload.get('email')
        if not email:
            return error_response('구글 이메일을 확인할 수 없습니다.', http_status.HTTP_401_UNAUTHORIZED)

        user = User.objects.filter(
            provider=User.Provider.GOOGLE,
            provider_user_id=google_sub,
        ).first()
        created = False

        if user is None:
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                if WithdrawnEmailHash.objects.filter(
                    email_hash=hash_email_for_withdrawal(email),
                    expires_at__gte=timezone.now().date(),
                ).exists():
                    return error_response('지금은 이 이메일로 가입할 수 없습니다.')
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
                if not user.is_active:
                    return _withdrawal_pending_response(user)
                user.provider_user_id = google_sub
                user.save(update_fields=['provider_user_id'])

        if not user.is_active:
            return _withdrawal_pending_response(user)
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
            user__status=User.Status.ACTIVE,
        ).first()

        if stored is None or stored.expires_at <= timezone.now():
            return error_response(
                '만료되었거나 폐기된 refresh_token입니다.',
                http_status.HTTP_401_UNAUTHORIZED,
            )

        if jwt_settings.CHECK_REVOKE_TOKEN and jwt_refresh.get(
            jwt_settings.REVOKE_TOKEN_CLAIM
        ) != get_md5_hash_password(stored.user.password):
            return error_response('다시 로그인해 주세요.', http_status.HTTP_401_UNAUTHORIZED)
        access_token = jwt_refresh.access_token
        return success_response({'access_token': str(access_token)}, 'Access Token이 재발급되었습니다.')


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        RefreshToken.objects.filter(user=request.user).delete()
        return success_response(message='로그아웃되었습니다.')


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.provider != User.Provider.EMAIL:
            return error_response('소셜 계정은 비밀번호를 사용하지 않아요.')
        serializer = PasswordChangeSerializer(
            data=request.data, context={'user': request.user}
        )
        if not serializer.is_valid():
            return error_response(serializer.errors)

        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save(update_fields=['password', 'updated_at'])
        # Every stored session used the old credential; force a fresh sign-in.
        RefreshToken.objects.filter(user=request.user).delete()
        return success_response(message='비밀번호를 변경했어요. 다시 로그인해 주세요.')


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
        feedbacks = Feedback.objects.filter(user=request.user).order_by('-created_at', '-id')
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


def _identity_confirmed(user, data):
    """탈퇴·철회 직전 본인 확인. 가입 경로에 맞는 수단만 인정한다."""
    if user.provider == User.Provider.GOOGLE:
        raw_token = data.get('id_token')
        if not isinstance(raw_token, str) or not raw_token:
            return False
        payload = verify_google_identity(raw_token)
        return payload is not None and payload.get('sub') == user.provider_user_id
    password = data.get('password')
    return isinstance(password, str) and user.check_password(password)


def _withdrawal_pending_response(user):
    if (user.status != User.Status.WITHDRAWN or user.purge_at is None
            or user.purge_at <= timezone.now()):
        return error_response('로그인할 수 없는 계정입니다.', http_status.HTTP_403_FORBIDDEN)
    return Response({
        'success': False,
        'data': {'code': 'withdrawal_pending', 'purge_at': user.purge_at.isoformat()},
        'message': '탈퇴 예정 계정입니다. 기한 내 본인 확인 후 탈퇴를 취소할 수 있습니다.',
    }, status=http_status.HTTP_403_FORBIDDEN)


def _pending_withdrawal_account(data):
    """탈퇴 유예 중이면서 본인 확인에 성공한 계정을 돌려준다. 아니면 None.

    본인 확인이 끝난 뒤에만 탈퇴 사실을 알려 준다. 먼저 알려 주면 남의 이메일로
    탈퇴 여부를 캐낼 수 있다.
    """
    if not isinstance(data, dict):
        return None
    raw_email = data.get('email')
    if not isinstance(raw_email, str):
        return None
    email = raw_email.strip().lower()
    if not email:
        return None
    user = User.objects.filter(email__iexact=email, status=User.Status.WITHDRAWN).first()
    if user is None or not _identity_confirmed(user, data):
        return None
    return user


class WithdrawView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = WithdrawSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(serializer.errors)

        user = User.objects.select_for_update().filter(pk=request.user.pk).first()
        if user is None or not user.is_active:
            return error_response('로그인할 수 없는 계정입니다.', http_status.HTTP_401_UNAUTHORIZED)
        if not _identity_confirmed(user, serializer.validated_data):
            return error_response('본인 확인에 실패했습니다.', http_status.HTTP_401_UNAUTHORIZED)

        with transaction.atomic():
            user.status = User.Status.WITHDRAWN
            user.purge_at = timezone.now() + WITHDRAWAL_GRACE_PERIOD
            user.withdrawal_reason_code = serializer.validated_data.get('reason_code') or None
            user.save(update_fields=['status', 'purge_at', 'withdrawal_reason_code', 'updated_at'])
            # 모든 기기에서 즉시 로그아웃시킨다. 유예를 기다리지 않는다.
            RefreshToken.objects.filter(user=user).delete()

        return success_response(
            {'purge_at': user.purge_at.isoformat()},
            '탈퇴가 접수되었습니다. 7일 이내에 로그인하시면 취소할 수 있습니다.',
        )


class WithdrawCancelView(APIView):
    # 유예 중에는 로그인이 막혀 있어 인증 헤더를 받을 수 없다. 자격 증명을 직접 받는다.
    permission_classes = [AllowAny]
    authentication_classes = []

    @transaction.atomic
    def post(self, request):
        # Lock before checking credentials/deadline: never restore a stale snapshot.
        if not isinstance(request.data, dict):
            return error_response('이메일과 본인 확인 정보를 입력해 주세요.')
        email = str(request.data.get('email') or '').strip()
        user = User.objects.select_for_update().filter(
            email__iexact=email, status=User.Status.WITHDRAWN,
        ).first()
        if user is not None and not _identity_confirmed(user, request.data):
            user = None
        if user is None:
            return error_response(
                '이메일 또는 비밀번호가 올바르지 않습니다.',
                http_status.HTTP_401_UNAUTHORIZED,
            )
        if user.purge_at is None or user.purge_at <= timezone.now():
            # 배치 실행 시각에 따라 결과가 달라지지 않도록, 기한이 지나면 거부한다.
            return error_response(
                '이미 파기 절차가 시작되어 복구할 수 없습니다.',
                http_status.HTTP_409_CONFLICT,
            )

        user.status = User.Status.ACTIVE
        user.purge_at = None
        user.withdrawal_reason_code = None
        user.save(update_fields=['status', 'purge_at', 'withdrawal_reason_code', 'updated_at'])

        tokens = issue_tokens(user)
        return success_response(tokens, '탈퇴가 취소되었습니다.')
