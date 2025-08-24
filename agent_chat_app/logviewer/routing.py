from django.urls import path
from agent_chat_app.logviewer.consumers import LogStreamConsumer

websocket_urlpatterns = [
    path('ws/logs/', LogStreamConsumer.as_asgi()),
]