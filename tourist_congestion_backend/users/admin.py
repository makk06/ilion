from django.contrib import admin
from .models import Inquiry


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = ['subject', 'user', 'status', 'created_at']
    readonly_fields = ['user', 'subject', 'text', 'created_at', 'updated_at', 'status']
    search_fields = ['subject', 'user__email']

    def save_model(self, request, obj, form, change):
        obj.status = 'answered' if obj.answer.strip() else 'received'
        super().save_model(request, obj, form, change)
