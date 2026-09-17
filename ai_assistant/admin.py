from django.contrib import admin
from .models import ChatMessage, TaskChangeLog, ClaudeUsageLog, EmployeeChangeLog, ChatFile


class EvidenceAdmin(admin.ModelAdmin):
    """Technical view only; business commands produce the original evidence."""
    actions = None

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(ChatMessage, EvidenceAdmin)
admin.site.register(TaskChangeLog, EvidenceAdmin)
admin.site.register(EmployeeChangeLog, EvidenceAdmin)


@admin.register(ChatFile)
class ChatFileAdmin(EvidenceAdmin):
    list_display = ['original_name', 'mime_type', 'size', 'uploaded_at', 'chat_message']
    list_filter = ['mime_type']


@admin.register(ClaudeUsageLog)
class ClaudeUsageLogAdmin(EvidenceAdmin):
    list_display = ['created_at', 'endpoint', 'model', 'input_tokens', 'output_tokens']
    list_filter = ['endpoint', 'model']
