from django.urls import path
from .views import ChatView, ChatHistoryView, MeetingProtocolView, DictateProcessView, chat_with_file

urlpatterns = [
    # POST /api/chat/         — send a message, get AI reply
    path('chat/', ChatView.as_view()),
    # POST /api/chat/file/    — send a message WITH an attached file (PDF/DOCX/XLSX)
    path('chat/file/', chat_with_file),
    # GET  /api/chat/history/ — fetch the full conversation log
    path('chat/history/', ChatHistoryView.as_view()),
    # POST /api/meeting/protocol/ — transcribed meeting text → formatted protocol + assignments
    path('meeting/protocol/', MeetingProtocolView.as_view()),
    # POST /api/dictate/process/ — raw dictation text → styled, translated result
    path('dictate/process/', DictateProcessView.as_view()),
]
