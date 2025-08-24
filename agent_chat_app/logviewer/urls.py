from django.urls import path
from agent_chat_app.logviewer.views import LogViewerView

app_name = 'logviewer'

urlpatterns = [
    path('logs/', LogViewerView.as_view(), name='logs'),
]