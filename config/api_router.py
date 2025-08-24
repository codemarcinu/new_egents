from django.conf import settings
from django.urls import path, include
from rest_framework.routers import DefaultRouter, SimpleRouter

from agent_chat_app.chat.api.views import (
    ConversationViewSet,
    MessageViewSet,
    DocumentViewSet,
    UserSettingsViewSet,
)
from agent_chat_app.logviewer.api.views import LogEntryViewSet

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

# Chat API endpoints
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("messages", MessageViewSet, basename="message")
router.register("documents", DocumentViewSet, basename="document")
router.register("user-settings", UserSettingsViewSet, basename="usersettings")
# Log Viewer API endpoints
router.register("logs", LogEntryViewSet, basename="logentry")

app_name = "api"
urlpatterns = [
    # DRF router URLs
    *router.urls,
    # Receipts API
    path("receipts/", include("agent_chat_app.receipts.api.urls")),
]