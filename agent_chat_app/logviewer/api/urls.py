from django.urls import path, include
from rest_framework.routers import DefaultRouter
from agent_chat_app.logviewer.api.views import LogEntryViewSet

router = DefaultRouter()
router.register(r'logs', LogEntryViewSet, basename='logentry')

urlpatterns = [
    path('', include(router.urls)),
]