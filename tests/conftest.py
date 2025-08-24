"""
Test fixtures for WebSocket authentication and session testing.
"""
import pytest
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from unittest.mock import AsyncMock, patch

from agent_chat_app.logviewer.consumers import LogStreamConsumer
from agent_chat_app.chat.consumers import ChatConsumer
from agent_chat_app.receipts.consumers import ReceiptProgressConsumer
from agent_chat_app.chat.models import Conversation
from agent_chat_app.receipts.models import Receipt

User = get_user_model()


@pytest.fixture
def authenticated_client(client, user):
    """Client with authenticated user session"""
    client.force_login(user)
    return client


@pytest.fixture
def staff_user(db):
    """Create a staff user for testing"""
    return User.objects.create_user(
        username='staffuser',
        email='staff@example.com',
        password='staffpass123',
        is_staff=True
    )


@pytest.fixture
def regular_user(db):
    """Create a regular non-staff user"""
    return User.objects.create_user(
        username='regularuser',
        email='regular@example.com',
        password='regularpass123',
        is_staff=False
    )


@pytest.fixture
def superuser(db):
    """Create a superuser for testing"""
    return User.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='admin123'
    )


@pytest.fixture
def conversation(db, regular_user):
    """Create a test conversation"""
    return Conversation.objects.create(
        title="Test Conversation",
        user=regular_user
    )


@pytest.fixture
def receipt(db, regular_user):
    """Create a test receipt"""
    return Receipt.objects.create(
        user=regular_user,
        file_name="test_receipt.jpg",
        status="uploaded"
    )


@pytest.fixture
def websocket_communicator():
    """Factory for creating WebSocket communicators"""
    def _create_communicator(consumer_class, path, user=None, **scope_kwargs):
        communicator = WebsocketCommunicator(consumer_class.as_asgi(), path)
        
        if user:
            communicator.scope["user"] = user
            communicator.scope["session"] = {
                "_auth_user_id": str(user.id),
                "_auth_user_backend": "django.contrib.auth.backends.ModelBackend"
            }
        
        # Add any additional scope data
        for key, value in scope_kwargs.items():
            communicator.scope[key] = value
            
        return communicator
    
    return _create_communicator


@pytest.fixture
def mock_channel_layer():
    """Mock channel layer for WebSocket testing"""
    with patch('channels.layers.get_channel_layer') as mock:
        mock_layer = AsyncMock()
        mock_layer.group_add = AsyncMock()
        mock_layer.group_discard = AsyncMock()
        mock_layer.group_send = AsyncMock()
        mock.return_value = mock_layer
        yield mock_layer


@pytest.fixture
def log_stream_communicator(websocket_communicator):
    """Pre-configured communicator for LogStreamConsumer"""
    def _create(user=None):
        return websocket_communicator(LogStreamConsumer, "/ws/logs/", user=user)
    return _create


@pytest.fixture
def chat_communicator(websocket_communicator, conversation):
    """Pre-configured communicator for ChatConsumer"""
    def _create(user=None):
        return websocket_communicator(
            ChatConsumer, 
            f"/ws/chat/{conversation.id}/", 
            user=user
        )
    return _create


@pytest.fixture
def receipt_communicator(websocket_communicator, receipt):
    """Pre-configured communicator for ReceiptProgressConsumer"""
    def _create(user=None):
        return websocket_communicator(
            ReceiptProgressConsumer, 
            f"/ws/receipt/{receipt.id}/", 
            user=user
        )
    return _create


@pytest.fixture
def authenticated_websocket_session(staff_user):
    """Create an authenticated WebSocket session scope"""
    return {
        "type": "websocket",
        "user": staff_user,
        "session": {
            "_auth_user_id": str(staff_user.id),
            "_auth_user_backend": "django.contrib.auth.backends.ModelBackend",
            "sessionid": "test_session_key"
        },
        "cookies": {
            "sessionid": "test_session_key"
        },
        "headers": [
            (b"origin", b"http://localhost:8000"),
            (b"user-agent", b"test-client")
        ]
    }


@pytest.fixture
def anonymous_websocket_session():
    """Create an anonymous WebSocket session scope"""
    from django.contrib.auth.models import AnonymousUser
    
    return {
        "type": "websocket",
        "user": AnonymousUser(),
        "session": {},
        "cookies": {},
        "headers": [
            (b"origin", b"http://localhost:8000"),
            (b"user-agent", b"test-client")
        ]
    }


class WebSocketTestHelper:
    """Helper class for WebSocket testing operations"""
    
    @staticmethod
    async def assert_connection_rejected(communicator, expected_code=None):
        """Assert that WebSocket connection is rejected with optional code check"""
        connected, subprotocol = await communicator.connect()
        assert not connected
        
        if expected_code:
            close_data = await communicator.receive_output()
            assert close_data['type'] == 'websocket.close'
            assert close_data['code'] == expected_code
    
    @staticmethod
    async def assert_connection_successful(communicator):
        """Assert that WebSocket connection succeeds"""
        connected, subprotocol = await communicator.connect()
        assert connected
        return connected
    
    @staticmethod
    async def send_ping_receive_pong(communicator, timestamp=None):
        """Send ping and verify pong response"""
        if not timestamp:
            timestamp = "2024-01-01T00:00:00Z"
            
        await communicator.send_json_to({
            "type": "ping",
            "timestamp": timestamp
        })
        
        response = await communicator.receive_json_from()
        assert response["type"] == "pong"
        assert response["timestamp"] == timestamp
        return response


@pytest.fixture
def websocket_helper():
    """Provide WebSocket testing helper methods"""
    return WebSocketTestHelper


@pytest.fixture
def session_debug_data(staff_user):
    """Create session debugging data for validation"""
    return {
        "user_id": staff_user.id,
        "username": staff_user.username,
        "is_authenticated": staff_user.is_authenticated,
        "is_staff": staff_user.is_staff,
        "is_superuser": staff_user.is_superuser,
        "session_key": "test_session_123",
        "backend": "django.contrib.auth.backends.ModelBackend"
    }


@pytest.fixture
def asgi_scope_validator():
    """Validator for ASGI scope data"""
    def _validate_scope(scope, expected_user=None):
        """Validate WebSocket scope contains expected data"""
        assert scope["type"] == "websocket"
        
        if expected_user:
            assert "user" in scope
            assert scope["user"] == expected_user
            assert scope["user"].is_authenticated
        
        assert "session" in scope
        return True
    
    return _validate_scope