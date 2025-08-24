import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class LogStreamConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Log connection attempt
        user = self.scope.get("user")
        logger.info(f"WebSocket connection attempt from user: {user}")

        # Check if user exists and is authenticated
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            logger.warning(f"WebSocket rejected: User not authenticated (user={user})")
            await self.close(code=4401)  # Custom close code for authentication failure
            return

        # Check if user is staff
        if not user.is_staff:
            logger.warning(
                f"WebSocket rejected: User {user.username} is not staff - "
                f"only staff members can access logs"
            )
            await self.close(code=4403)  # Custom close code for permission denied
            return

        # Accept the connection first
        await self.accept()

        self.room_group_name = "log_stream"

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        logger.info(f"User {user.username} connected to log stream")

    async def disconnect(self, close_code):
        # Leave room group
        try:
            if hasattr(self, "room_group_name"):
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name,
                )
        except Exception as e:
            logger.error(f"Error leaving group: {e}")

        if hasattr(self.scope["user"], "username"):
            logger.info(
                f"User {self.scope['user'].username} disconnected from log stream"
            )

    async def receive(self, text_data):
        # Handle any messages from WebSocket (if needed)
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get("type")

            if message_type == "ping":
                await self.send(text_data=json.dumps({
                    "type": "pong",
                    "timestamp": text_data_json.get("timestamp"),
                }))
        except json.JSONDecodeError:
            logger.warning("Invalid JSON received from WebSocket")

    async def log_entry(self, event):
        """Send log entry to WebSocket"""
        await self.send(text_data=json.dumps({
            "type": "log_entry",
            "log": event["log"],
        }))
