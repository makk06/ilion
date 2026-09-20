from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from django.utils import timezone

from places.models import Place

from .models import WithdrawnEmailHash
from .utils import hash_email_for_withdrawal

from .models import Feedback, User


class SignupSerializer(serializers.ModelSerializer):
    # ModelSerializer would build its own UniqueValidator whose message comes
    # from the model field ("user의 email은/는 이미 존재합니다."). Declaring the
    # validator here is what actually replaces that text for the signup form;
    # error_messages alone does not reach it.
    email = serializers.EmailField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message='이미 가입된 이메일이에요. 로그인해 주세요.',
            )
        ],
        error_messages={
            'invalid': '이메일 주소 형식이 올바르지 않아요.',
            'blank': '이메일 주소를 입력해 주세요.',
            'required': '이메일 주소를 입력해 주세요.',
        },
    )
    nickname = serializers.CharField(
        max_length=30,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message='이미 사용 중인 닉네임이에요. 다른 닉네임을 써주세요.',
            )
        ],
        error_messages={
            'blank': '닉네임을 입력해 주세요.',
            'required': '닉네임을 입력해 주세요.',
            'max_length': '닉네임은 30자까지 쓸 수 있어요.',
        },
    )
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ['email', 'password', 'nickname']

    def validate_email(self, value):
        blocked = WithdrawnEmailHash.objects.filter(
            email_hash=hash_email_for_withdrawal(value),
            expires_at__gte=timezone.now().date(),
        ).exists()
        if blocked:
            # 탈퇴 사실을 밝히지 않는다. 밝히면 남의 이메일로 탈퇴 여부를 캐낼 수 있다.
            raise serializers.ValidationError('지금은 이 이메일로 가입할 수 없습니다.')
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(provider=User.Provider.EMAIL, **validated_data)
        user.set_password(password)
        user.save()
        return user


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        if not self.context['user'].check_password(value):
            raise serializers.ValidationError('현재 비밀번호가 올바르지 않아요.')
        return value

    def validate_new_password(self, value):
        validate_password(value, self.context['user'])
        return value

    def validate(self, attrs):
        if attrs['current_password'] == attrs['new_password']:
            raise serializers.ValidationError('현재 비밀번호와 다른 비밀번호를 입력해 주세요.')
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(email=attrs['email'], password=attrs['password'])
        if user is None:
            raise serializers.ValidationError('이메일 또는 비밀번호가 올바르지 않습니다.')
        attrs['user'] = user
        return attrs


class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField()


class FavoriteCreateSerializer(serializers.Serializer):
    place_id = serializers.IntegerField()

    def validate_place_id(self, value):
        if not Place.objects.filter(id=value).exists():
            raise serializers.ValidationError('존재하지 않는 장소입니다.')
        return value


class FeedbackCreateSerializer(serializers.Serializer):
    place_id = serializers.IntegerField()
    feedback_type = serializers.ChoiceField(choices=Feedback.FeedbackType.choices)
    value = serializers.IntegerField(min_value=0, max_value=100, required=False, allow_null=True)
    memo = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def validate_place_id(self, value):
        if not Place.objects.filter(id=value).exists():
            raise serializers.ValidationError('존재하지 않는 장소입니다.')
        return value


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ['id', 'place_id', 'feedback_type', 'value', 'memo', 'created_at']


# 탈퇴 사유는 앱이 제시하는 선택지에서만 고른다. 자유 입력을 허용하면 본인을
# 식별할 수 있는 내용이 들어와 집계의 익명성이 깨진다.
WITHDRAWAL_REASON_CODES = (
    'no_longer_needed',
    'few_places',
    'inaccurate_crowd',
    'privacy_concern',
    'switched_service',
    'etc',
)


class WithdrawSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    id_token = serializers.CharField(required=False, allow_blank=True)
    reason_code = serializers.ChoiceField(choices=WITHDRAWAL_REASON_CODES, required=False)
