"""
WebSocket Authentication Tests

Tests for validating authentication and authorization for WebSocket consumers.
Covers LogStreamConsumer, ChatConsumer, and ReceiptProgressConsumer authentication.
"""
import pytest
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import AsyncMock, patch

from agent_chat_app.logviewer.consumers import LogStreamConsumer
from agent_chat_app.chat.consumers import ChatConsumer
from agent_chat_app.receipts.consumers import ReceiptProgressConsumer
from agent_chat_app.chat.models import Conversation
from agent_chat_app.receipts.models import Receipt

User = get_user_model()


class WebSocketAuthTestCase(TestCase):
    """Base test case for WebSocket authentication tests"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.staff_user = User.objects.create_user(
            username='staffuser',
            email='staff@example.com',
            password='staffpass123',
            is_staff=True
        )
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='admin123'
        )


class LogStreamConsumerAuthTests(WebSocketAuthTestCase):
    """Test authentication for LogStreamConsumer"""

    async def test_anonymous_user_rejection(self):
        """Test that anonymous users are rejected with code 4401"""
        communicator = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")
        
        connected, subprotocol = await communicator.connect()
        
        assert connected is False
        assert communicator.output_queue.qsize() == 0
        
        # Check close code
        close_data = await communicator.receive_output()
        assert close_data['type'] == 'websocket.close'
        assert close_data['code'] == 4401

    async def test_authenticated_non_staff_user_rejection(self):
        """Test that authenticated non-staff users are rejected with code 4403"""
        communicator = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")
        communicator.scope["user"] = self.user
        
        connected, subprotocol = await communicator.connect()
        
        assert connected is False
        
        # Check close code
        close_data = await communicator.receive_output()
        assert close_data['type'] == 'websocket.close'
        assert close_data['code'] == 4403

    async def test_staff_user_connection_success(self):
        """Test that staff users can successfully connect"""
        communicator = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")
        communicator.scope["user"] = self.staff_user
        
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            
            connected, subprotocol = await communicator.connect()
            
            assert connected is True
            mock_channel_layer.group_add.assert_called_once()

        await communicator.disconnect()

    async def test_superuser_connection_success(self):
        """Test that superusers can successfully connect"""
        communicator = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")
        communicator.scope["user"] = self.superuser
        
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            
            connected, subprotocol = await communicator.connect()
            
            assert connected is True
            mock_channel_layer.group_add.assert_called_once()

        await communicator.disconnect()

    async def test_ping_pong_functionality(self):
        """Test ping-pong message handling for staff users"""
        communicator = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")
        communicator.scope["user"] = self.staff_user
        
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            
            connected, subprotocol = await communicator.connect()
            assert connected is True
            
            # Send ping message
            await communicator.send_json_to({
                "type": "ping",
                "timestamp": "2024-01-01T00:00:00Z"
            })
            
            # Receive pong response
            response = await communicator.receive_json_from()
            
            assert response["type"] == "pong"
            assert response["timestamp"] == "2024-01-01T00:00:00Z"

        await communicator.disconnect()


class ChatConsumerAuthTests(WebSocketAuthTestCase):
    """Test authentication for ChatConsumer"""

    def setUp(self):
        super().setUp()
        self.conversation = Conversation.objects.create(
            title="Test Conversation",
            user=self.user
        )

    async def test_anonymous_user_rejection(self):
        """Test that anonymous users are rejected from chat"""
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(), 
            f"/ws/chat/{self.conversation.id}/"
        )
        
        connected, subprotocol = await communicator.connect()
        
        # Chat consumer should reject anonymous users
        assert connected is False

    @database_sync_to_async
    def get_conversation(self):
        return Conversation.objects.get(id=self.conversation.id)

    async def test_authenticated_user_with_access_success(self):
        """Test that authenticated users with access can connect to their conversations"""
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(), 
            f"/ws/chat/{self.conversation.id}/"
        )
        communicator.scope["user"] = self.user
        
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            
            connected, subprotocol = await communicator.connect()
            
            # Should succeed for conversation owner
            assert connected is True

        await communicator.disconnect()

    async def test_authenticated_user_without_access_rejection(self):
        """Test that authenticated users without access are rejected"""
        other_user = await database_sync_to_async(User.objects.create_user)(
            username='otheruser',
            email='other@example.com',
            password='otherpass123'
        )
        
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(), 
            f"/ws/chat/{self.conversation.id}/"
        )
        communicator.scope["user"] = other_user
        
        connected, subprotocol = await communicator.connect()
        
        # Should fail for non-owner
        assert connected is False


class ReceiptProgressConsumerAuthTests(WebSocketAuthTestCase):
    """Test authentication for ReceiptProgressConsumer"""

    def setUp(self):
        super().setUp()
        self.receipt = Receipt.objects.create(
            user=self.user,
            file_name="test_receipt.jpg",
            status="uploaded"
        )

    async def test_anonymous_user_rejection(self):
        """Test that anonymous users are rejected from receipt progress"""
        communicator = WebsocketCommunicator(
            ReceiptProgressConsumer.as_asgi(), 
            f"/ws/receipt/{self.receipt.id}/"
        )
        
        connected, subprotocol = await communicator.connect()
        
        assert connected is False

    async def test_authenticated_user_with_receipt_access_success(self):
        """Test that authenticated users can connect to their receipt progress"""
        communicator = WebsocketCommunicator(
            ReceiptProgressConsumer.as_asgi(), 
            f"/ws/receipt/{self.receipt.id}/"
        )
        communicator.scope["user"] = self.user
        
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            
            connected, subprotocol = await communicator.connect()
            
            assert connected is True

        await communicator.disconnect()

    async def test_authenticated_user_without_receipt_access_rejection(self):
        """Test that authenticated users without receipt access are rejected"""
        other_user = await database_sync_to_async(User.objects.create_user)(
            username='otheruser',
            email='other@example.com',
            password='otherpass123'
        )
        
        communicator = WebsocketCommunicator(
            ReceiptProgressConsumer.as_asgi(), 
            f"/ws/receipt/{self.receipt.id}/"
        )
        communicator.scope["user"] = other_user
        
        connected, subprotocol = await communicator.connect()
        
        assert connected is False


class SessionMiddlewareTests(WebSocketAuthTestCase):
    """Test session middleware functionality"""

    async def test_session_data_validation(self):
        """Test that session data is properly transmitted through middleware"""
        communicator = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")
        
        # Mock session data
        communicator.scope["user"] = self.staff_user
        communicator.scope["session"] = {
            "_auth_user_id": str(self.staff_user.id),
            "_auth_user_backend": "django.contrib.auth.backends.ModelBackend"
        }
        
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            
            connected, subprotocol = await communicator.connect()
            
            assert connected is True
            assert communicator.scope["user"] == self.staff_user

        await communicator.disconnect()

    async def test_missing_session_data_rejection(self):
        """Test rejection when session data is missing"""
        communicator = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")
        
        # No user or session data
        connected, subprotocol = await communicator.connect()
        
        assert connected is False
        
        close_data = await communicator.receive_output()
        assert close_data['type'] == 'websocket.close'
        assert close_data['code'] == 4401


# Pytest versions of the tests for better integration
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestWebSocketAuthPytest:
    """Pytest-based WebSocket authentication tests"""

    async def test_log_stream_anonymous_rejection(self, db):
        """Test LogStreamConsumer rejects anonymous users"""
        communicator = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")
        
        connected, subprotocol = await communicator.connect()
        
        assert not connected
        
        close_data = await communicator.receive_output()
        assert close_data['code'] == 4401

    async def test_log_stream_staff_success(self, staff_user):
        """Test LogStreamConsumer accepts staff users"""
        communicator = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")
        communicator.scope["user"] = staff_user
        
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            
            connected, subprotocol = await communicator.connect()
            
            assert connected
            mock_channel_layer.group_add.assert_called_once_with(
                "log_stream",
                communicator.channel_name
            )

        await communicator.disconnect()

    async def test_middleware_stack_validation(self, staff_user):
        """Test that AuthMiddlewareStack properly validates users"""
        from config.asgi import application
        
        # Ensure the application uses AuthMiddlewareStack
        assert hasattr(application, 'application_mapping')
        websocket_app = application.application_mapping['websocket']
        
        # Should be AllowedHostsOriginValidator wrapping AuthMiddlewareStack
        assert websocket_app.__class__.__name__ == 'AllowedHostsOriginValidator'