from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from places.models import Place

from .models import Feedback, User


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ['email', 'password', 'nickname']

    def validate_nickname(self, value):
        if User.objects.filter(nickname=value).exists():
            raise serializers.ValidationError('이미 사용 중인 닉네임입니다.')
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(provider=User.Provider.EMAIL, **validated_data)
        user.set_password(password)
        user.save()
        return user


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
