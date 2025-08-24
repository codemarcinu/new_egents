import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class LogStreamConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Check if user is authenticated and is staff
        if (self.scope["user"] == AnonymousUser or 
            not self.scope["user"].is_authenticated or 
            not self.scope["user"].is_staff):
            await self.close()
            return

        self.room_group_name = 'log_stream'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"User {self.scope['user'].username} connected to log stream")

    async def disconnect(self, close_code):
        # Leave room group
        try:
            if hasattr(self, 'room_group_name'):
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
        except Exception as e:
            logger.error(f"Error leaving group: {e}")
        
        if hasattr(self.scope["user"], "username"):
            logger.info(f"User {self.scope['user'].username} disconnected from log stream")

    async def receive(self, text_data):
        # Handle any messages from WebSocket (if needed)
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': text_data_json.get('timestamp')
                }))
        except json.JSONDecodeError:
            logger.warning("Invalid JSON received from WebSocket")

    async def log_entry(self, event):
        """Send log entry to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'log_entry',
            'log': event['log']
        }))