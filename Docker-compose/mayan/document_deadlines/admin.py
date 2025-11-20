from django.contrib import admin
from .models import DocumentDeadline

@admin.register(DocumentDeadline)
class DocumentDeadlineAdmin(admin.ModelAdmin):
    list_display = ('document', 'user', 'deadline', 'completed', 'completed_at')