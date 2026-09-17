from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils import timezone
from django import forms
from .models import TourEvent, EventTargetLink


class EventForm(forms.ModelForm):
    class Meta:
        model = TourEvent
        fields = '__all__'
    def clean(self):
        data = super().clean()
        if data.get('source') not in ('manual', 'tour_api'):
            raise ValidationError('지원하지 않는 출처입니다.')
        if data.get('source') == 'manual' and not data.get('source_url'):
            raise ValidationError('공식 출처 URL이 필요합니다.')
        if data.get('source') == 'manual' and not data.get('external_id','').startswith('manual:'):
            raise ValidationError('수동 행사 ID는 manual: 접두사를 사용하세요.')
        start, end = data.get('starts_at'), data.get('ends_at')
        if bool(start) != bool(end) or (start and start >= end):
            raise ValidationError('시작·종료 시각을 함께 올바르게 입력하세요.')
        if bool(data.get('family')) != bool(data.get('edition')):
            raise ValidationError('반복 행사 식별자와 회차를 함께 입력하세요.')
        return data


@admin.register(TourEvent)
class TourEventAdmin(admin.ModelAdmin):
    form = EventForm
    list_display = ('name', 'source', 'status', 'start_date', 'end_date', 'time_quality')
    list_filter = ('source', 'status')
    search_fields = ('name', 'external_id')
    readonly_fields = ('first_seen_at', 'changed_at', 'fetched_at', 'content_hash', 'source_modified_at', 'raw_data', 'detail_pending')
    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (('source','external_id') if obj else ())
    def get_changeform_initial_data(self, request):
        return {'source': 'manual'}
    def save_model(self, request, obj, form, change):
        obj.fetched_at = timezone.now()
        obj.time_quality = 'verified_time' if obj.starts_at and obj.ends_at else 'date_only'
        obj.active = obj.status == 'scheduled'
        super().save_model(request, obj, form, change)
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EventTargetLink)
class EventTargetLinkAdmin(admin.ModelAdmin):
    list_display = ('event', 'target', 'verified', 'checked_at')
    readonly_fields = ('checked_at',)
    def has_delete_permission(self, request, obj=None):
        return False
