from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

from agent_chat_app.chat.api.views import (
    ConversationViewSet,
    MessageViewSet,
    DocumentViewSet,
    UserSettingsViewSet,
)

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

# Chat API endpoints
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("messages", MessageViewSet, basename="message")
router.register("documents", DocumentViewSet, basename="document")
router.register("user-settings", UserSettingsViewSet, basename="usersettings")

app_name = "api"
urlpatterns = router.urls