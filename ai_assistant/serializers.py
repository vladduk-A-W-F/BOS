from rest_framework import serializers
from .models import ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    # Если у сообщения есть прикреплённый файл — возвращаем его имя (иначе null).
    # Фронту нужно чтоб рисовать бейдж "📎 name.pdf" в истории чата.
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'created_at', 'file_name']

    def get_file_name(self, obj):
        return obj.attached_file.original_name if hasattr(obj, 'attached_file') else None
