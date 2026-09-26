from django.db import models
from django.conf import settings
from boss_project.archive import ArchiveModel


class ChatMessage(ArchiveModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    visibility_role = models.CharField(max_length=20, blank=True, default='')
    command_fields = (*ArchiveModel.command_fields, 'user', 'visibility_role')
    ROLE_CHOICES = [
        ('user',      'User'),
        ('assistant', 'Assistant'),
    ]

    # Who wrote this message — either the human ('user') or AI ('assistant')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)

    # The actual text of the message — no length limit (TextField, not CharField)
    content = models.TextField()

    # Set automatically when the message is saved — used to sort history
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        # Always return messages oldest-first — correct order for a chat timeline
        ordering = ['created_at']

    def __str__(self):
        # Show first 50 chars so admin/shell stays readable
        return f"{self.role}: {self.content[:50]}"


class TaskChangeLog(models.Model):
    """Audit log: every create/update/delete of Task is recorded here.
    Enables real undo — restoring previous state by reading 'before' field."""

    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
    ]

    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    task_id = models.IntegerField(db_index=True)  # NOT a ForeignKey — task may be deleted
    task_title = models.CharField(max_length=200)
    before = models.JSONField(null=True, blank=True)  # task state BEFORE change (None for create)
    after = models.JSONField(null=True, blank=True)   # task state AFTER change (None for delete)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']  # newest first — undo reads top entry

    def __str__(self):
        return f"{self.action} task #{self.task_id} ({self.task_title}) at {self.changed_at}"


class ClaudeUsageLog(models.Model):
    """Tracks token usage for every Claude API call so we can monitor costs.
    For the chat endpoint, records summed totals across a full multi-step tool-use loop
    (not per individual API call inside the loop)."""

    ENDPOINT_CHOICES = [
        ('chat',    'Chat'),     # /api/chat/ — main AI conversation
        ('meeting', 'Meeting'),  # /api/meeting/protocol/ — AudioMeeting
        ('dictate', 'Dictate'),  # /api/dictate/process/ — Dictaphone
    ]

    endpoint = models.CharField(max_length=10, choices=ENDPOINT_CHOICES, db_index=True)
    model = models.CharField(max_length=50)    # e.g. 'claude-sonnet-4-5'
    input_tokens = models.IntegerField()
    output_tokens = models.IntegerField()
    # Optional back-link to the assistant reply this call produced (chat only)
    # SET_NULL: deleting a ChatMessage keeps the usage record intact for cost tracking
    chat_message = models.ForeignKey(
        'ChatMessage', null=True, blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return (
            f"{self.endpoint} {self.model}: "
            f"{self.input_tokens}in+{self.output_tokens}out tokens @ {self.created_at}"
        )


class EmployeeChangeLog(models.Model):
    """Audit log for Employee changes — parallel to TaskChangeLog.
    Enables real undo for employee operations."""

    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
    ]

    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    employee_id = models.IntegerField(db_index=True)  # NOT FK — employee may be deleted
    employee_name = models.CharField(max_length=200)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    undone_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.action} employee #{self.employee_id} ({self.employee_name}) at {self.changed_at}"


class ChatFile(models.Model):
    """Файл прикреплённый к user-сообщению чата.
    OneToOne с ChatMessage — один файл на одно сообщение.
    При удалении ChatMessage файл каскадно удаляется из БД, НО физический файл на диске
    не чистится автоматически — это известный долг (нужен cleanup-скрипт).
    """
    # Связь с сообщением — CASCADE потому что файл без сообщения бессмыслен
    chat_message = models.OneToOneField(
        'ChatMessage', on_delete=models.CASCADE, related_name='attached_file'
    )
    # Оригинальное имя файла как оно называется у пользователя ("Договір №12.pdf")
    original_name = models.CharField(max_length=255)
    # Реальный файл на диске в media/chat_files/YYYY/MM/
    file = models.FileField(upload_to='chat_files/%Y/%m/')
    mime_type = models.CharField(max_length=100)   # application/pdf, application/vnd...
    size = models.IntegerField()                    # в байтах
    checksum = models.CharField(max_length=64, null=True, blank=True)
    # Для DOCX/XLSX — сразу распарсенный markdown-текст (избегаем повторного парсинга)
    # Для PDF — пусто (Claude читает PDF нативно через base64)
    parsed_text = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.original_name} → msg #{self.chat_message_id}"
