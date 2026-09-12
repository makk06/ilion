from django.utils import timezone
from rest_framework import serializers
from places.models import Place
from .models import User, Review, Companion, Plan, Inquiry


class ProfileSerializer(serializers.ModelSerializer):
    preferred_categories = serializers.ListField(child=serializers.CharField(max_length=100), max_length=30, required=False, allow_null=True)
    preferences = serializers.DictField(required=False)

    class Meta:
        model = User
        fields = ['id', 'email', 'nickname', 'profile_image_url', 'preferred_categories', 'preferences']
        read_only_fields = ['id', 'email', 'profile_image_url']


class ReviewSerializer(serializers.ModelSerializer):
    place_id = serializers.PrimaryKeyRelatedField(source='place', queryset=Place.objects.all())
    rating = serializers.IntegerField(min_value=1, max_value=5, default=5)
    photo = serializers.ImageField(required=False)

    class Meta:
        model = Review
        fields = ['place_id', 'text', 'rating', 'photo']

    def validate_photo(self, photo):
        if photo.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('사진은 10MB 이하여야 합니다.')
        if photo.image.format not in ('JPEG', 'PNG', 'WEBP'):
            raise serializers.ValidationError('JPEG, PNG, WEBP 사진만 지원합니다.')
        return photo


class CompanionSerializer(serializers.ModelSerializer):
    place_id = serializers.PrimaryKeyRelatedField(source='place', queryset=Place.objects.all())
    capacity = serializers.IntegerField(min_value=2, max_value=30)

    class Meta:
        model = Companion
        fields = ['place_id', 'title', 'text', 'date', 'time', 'capacity']

    def validate_date(self, value):
        if value is not None and value < timezone.localdate():
            raise serializers.ValidationError('오늘 이후 날짜를 선택해 주세요.')
        return value

    def validate_capacity(self, value):
        if self.instance and value < self.instance.member_count:
            raise serializers.ValidationError('현재 참여 인원보다 적게 설정할 수 없습니다.')
        return value


class StopSerializer(serializers.Serializer):
    time = serializers.TimeField(format='%H:%M', input_formats=['%H:%M'])
    place = serializers.CharField(max_length=255)


class PlanSerializer(serializers.ModelSerializer):
    stops = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=30)

    class Meta:
        model = Plan
        fields = ['id', 'title', 'date', 'stops', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_stops(self, value):
        result = []
        for item in value:
            serializer = StopSerializer(data=item)
            serializer.is_valid(raise_exception=True)
            result.append(dict(serializer.data))
        return result


class InquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = Inquiry
        fields = ['id', 'subject', 'text', 'status', 'answer', 'created_at', 'updated_at']
        read_only_fields = ['id', 'status', 'answer', 'created_at', 'updated_at']
