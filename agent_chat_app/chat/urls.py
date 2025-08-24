from django.urls import path
from .views import ChatView, DocumentUploadView, DocumentDeleteView, UserSettingsView, ConversationDeleteView

app_name = 'chat'

urlpatterns = [
    path('', ChatView.as_view(), name='chat_start'),
    path('latest/', ChatView.as_view(), {'redirect_to_latest': True}, name='chat_latest'),
    path('<int:conversation_id>/', ChatView.as_view(), name='chat_view'),
    path('<int:conversation_id>/delete/', ConversationDeleteView.as_view(), name='conversation_delete'),
    path('documents/', DocumentUploadView.as_view(), name='document_upload'),
    path('documents/<int:document_id>/delete/', DocumentDeleteView.as_view(), name='document_delete'),
    path('settings/', UserSettingsView.as_view(), name='user_settings'),
]