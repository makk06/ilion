from rest_framework import serializers
import re


class RecommendationRequestSerializer(serializers.Serializer):
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    radius_km = serializers.FloatField(min_value=0.1, max_value=100, default=10)
    category = serializers.CharField(max_length=100, required=False, allow_blank=True)
    required_categories = serializers.ListField(child=serializers.CharField(max_length=100), required=False)
    crowd_level = serializers.ChoiceField(choices=['relaxed', 'normal', 'busy', 'crowded', 'any'], default='any')
    quiet_required = serializers.BooleanField(default=False)
    indoor_outdoor = serializers.ChoiceField(choices=['indoor', 'outdoor', 'mixed'], required=False)
    required_indoor_outdoor = serializers.ChoiceField(choices=['indoor', 'outdoor', 'mixed'], required=False)
    weather_aware = serializers.BooleanField(default=True)
    weather_evidence_required = serializers.BooleanField(default=False)
    visit_at = serializers.DateTimeField(required=False)
    limit = serializers.IntegerField(min_value=1, max_value=10, default=10)

    def validate_visit_at(self, value):
        raw = self.initial_data.get('visit_at')
        if not isinstance(raw, str) or not re.search(r'(Z|[+-]\d{2}:\d{2})$', raw):
            raise serializers.ValidationError('visit_at must include a UTC offset')
        return value

    def validate(self, attrs):
        if attrs.get('quiet_required') and attrs['crowd_level'] not in ('relaxed', 'any'):
            raise serializers.ValidationError('quiet_required requires relaxed or any crowd_level')
        return attrs
