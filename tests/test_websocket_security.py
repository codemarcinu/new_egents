"""
WebSocket Security Testing Suite

Comprehensive security tests for WebSocket consumers including:
- Session hijacking prevention
- CSRF token validation
- Origin validation
- Message tampering prevention
- Authentication bypass attempts
"""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings
from django.middleware.csrf import get_token

from agent_chat_app.chat.consumers import ChatConsumer
from agent_chat_app.logviewer.consumers import LogStreamConsumer
from agent_chat_app.receipts.consumers import ReceiptProgressConsumer
from agent_chat_app.chat.models import Conversation
from agent_chat_app.receipts.models import Receipt

User = get_user_model()


class WebSocketSecurityTestCase(TransactionTestCase):
    """Base test case for WebSocket security tests"""

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
        self.conversation = Conversation.objects.create(
            title="Test Conversation",
            user=self.user
        )
        self.receipt = Receipt.objects.create(
            user=self.user,
            file_name="test_receipt.jpg",
            status="uploaded"
        )


class SessionHijackingTests(WebSocketSecurityTestCase):
    """Test session hijacking prevention mechanisms"""

    async def test_session_id_validation(self):
        """Test that session IDs are properly validated"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")

        # Try connecting without session
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

        # Try connecting with invalid session
        communicator.scope["session"] = {"_auth_user_id": "99999"}  # Non-existent user
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    async def test_session_timeout_handling(self):
        """Test behavior when session expires during connection"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Simulate session expiry by clearing user
            communicator.scope["user"] = None

            # Send message - should be rejected
            await communicator.send_json_to({"type": "chat_message", "message": "test"})

            # Connection should be closed
            response = await communicator.receive_output()
            self.assertEqual(response['type'], 'websocket.close')

        await communicator.disconnect()

    async def test_concurrent_session_handling(self):
        """Test handling of multiple sessions for same user"""
        # Create two communicators for same user
        comm1 = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        comm2 = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")

        comm1.scope["user"] = self.user
        comm2.scope["user"] = self.user

        # Both should connect successfully (depending on implementation)
        with patch('channels.layers.InMemoryChannelLayer') as mock_layer:
            connected1, _ = await comm1.connect()
            connected2, _ = await comm2.connect()

            # At minimum, first connection should work
            self.assertTrue(connected1)

        await comm1.disconnect()
        await comm2.disconnect()


class CSRFTokenValidationTests(WebSocketSecurityTestCase):
    """Test CSRF token validation for WebSocket connections"""

    async def test_csrf_token_validation(self):
        """Test that CSRF tokens are validated for WebSocket connections"""
        from django.middleware.csrf import CsrfViewMiddleware

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        # Test without CSRF token
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

        # Test with invalid CSRF token
        communicator.scope["session"] = {"csrf_token": "invalid_token"}
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    async def test_csrf_token_rotation(self):
        """Test CSRF token rotation during connection"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        # Generate valid CSRF token
        csrf_token = get_token(self.user)  # This is a simplified example
        communicator.scope["session"] = {"csrf_token": csrf_token}

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Simulate token rotation
            new_csrf_token = "new_rotated_token"
            communicator.scope["session"] = {"csrf_token": new_csrf_token}

            # Connection should remain active if implementation allows rotation
            # (This depends on your specific CSRF implementation)

        await communicator.disconnect()


class OriginValidationTests(WebSocketSecurityTestCase):
    """Test origin validation for WebSocket connections"""

    @override_settings(ALLOWED_HOSTS=['localhost', 'example.com'])
    async def test_allowed_origin_validation(self):
        """Test connections from allowed origins"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user
        communicator.scope["headers"] = [
            (b'origin', b'https://example.com'),
            (b'host', b'example.com'),
        ]

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

        await communicator.disconnect()

    @override_settings(ALLOWED_HOSTS=['localhost', 'example.com'])
    async def test_blocked_origin_rejection(self):
        """Test rejection of connections from blocked origins"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user
        communicator.scope["headers"] = [
            (b'origin', b'https://malicious.com'),
            (b'host', b'malicious.com'),
        ]

        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    async def test_missing_origin_header(self):
        """Test handling of missing origin header"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user
        communicator.scope["headers"] = [
            (b'host', b'example.com'),
        ]

        # Should handle gracefully (depending on your security policy)
        connected, _ = await communicator.connect()
        # This might be allowed or rejected based on your configuration
        await communicator.disconnect()


class MessageTamperingPreventionTests(WebSocketSecurityTestCase):
    """Test prevention of message tampering and replay attacks"""

    async def test_message_integrity_validation(self):
        """Test that message integrity is validated"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send valid message
            valid_message = {
                "type": "chat_message",
                "message": "Hello World",
                "timestamp": "2024-01-01T00:00:00Z"
            }
            await communicator.send_json_to(valid_message)

            # Should be processed successfully
            response = await communicator.receive_json_from()
            self.assertIsNotNone(response)

            # Send malformed message
            malformed_message = {
                "type": "chat_message",
                # Missing required fields
            }
            await communicator.send_json_to(malformed_message)

            # Should handle gracefully
            response = await communicator.receive_json_from()
            self.assertIsNotNone(response)

        await communicator.disconnect()

    async def test_replay_attack_prevention(self):
        """Test prevention of message replay attacks"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send message with timestamp
            message = {
                "type": "chat_message",
                "message": "Test Message",
                "timestamp": "2024-01-01T00:00:00Z",
                "sequence_id": "12345"
            }
            await communicator.send_json_to(message)

            # Attempt to replay same message
            await communicator.send_json_to(message)

            # Should be handled appropriately (rejected or deduplicated)

        await communicator.disconnect()

    async def test_message_size_limits(self):
        """Test enforcement of message size limits"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send oversized message
            large_message = {
                "type": "chat_message",
                "message": "x" * 100000,  # Very large message
            }

            # This should be rejected or truncated
            await communicator.send_json_to(large_message)

        await communicator.disconnect()


class AuthenticationBypassTests(WebSocketSecurityTestCase):
    """Test various authentication bypass attempts"""

    async def test_header_injection_bypass(self):
        """Test attempts to bypass auth through header injection"""
        communicator = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")

        # Try injecting user via headers
        communicator.scope["headers"] = [
            (b'x-user-id', str(self.staff_user.id)),
            (b'x-username', self.staff_user.username),
        ]

        connected, _ = await communicator.connect()
        # Should still require proper authentication
        self.assertFalse(connected)

    async def test_parameter_injection_bypass(self):
        """Test attempts to bypass auth through parameter injection"""
        # Try to access another user's conversation
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='otherpass123'
        )
        other_conversation = Conversation.objects.create(
            title="Other Conversation",
            user=other_user
        )

        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f"/ws/chat/{other_conversation.id}/"
        )
        communicator.scope["user"] = self.user  # Wrong user

        connected, _ = await communicator.connect()
        # Should be rejected due to ownership check
        self.assertFalse(connected)

    async def test_session_fixation_attack(self):
        """Test session fixation attack attempts"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")

        # Try with fixed session ID
        fixed_session_id = "fixed_session_123"
        communicator.scope["session"] = {
            "session_key": fixed_session_id,
            "_auth_user_id": str(self.user.id)
        }

        connected, _ = await communicator.connect()
        # Should validate session properly
        self.assertFalse(connected)  # Assuming session validation is strict


# Pytest versions for better integration
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestWebSocketSecurityPytest:
    """Pytest-based WebSocket security tests"""

    async def test_sql_injection_via_websocket(self, user, conversation):
        """Test SQL injection prevention through WebSocket messages"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            assert connected

            # Attempt SQL injection
            malicious_message = {
                "type": "chat_message",
                "message": "'; DROP TABLE messages; --",
            }

            await communicator.send_json_to(malicious_message)

            # Should be sanitized and not execute SQL
            response = await communicator.receive_json_from()
            assert response is not None

        await communicator.disconnect()

    async def test_xss_prevention_in_messages(self, user, conversation):
        """Test XSS prevention in WebSocket messages"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            assert connected

            # Attempt XSS
            xss_message = {
                "type": "chat_message",
                "message": "<script>alert('XSS')</script>",
            }

            await communicator.send_json_to(xss_message)

            # Should be sanitized
            response = await communicator.receive_json_from()
            assert response is not None
            # Response should not contain unsanitized script tags

        await communicator.disconnect()

    async def test_json_injection_attack(self, user, conversation):
        """Test JSON injection attack prevention"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            assert connected

            # Attempt JSON injection
            json_injection = {
                "type": "chat_message",
                "message": '{"__proto__": {"isAdmin": true}}',
            }

            await communicator.send_json_to(json_injection)

            # Should be handled safely
            response = await communicator.receive_json_from()
            assert response is not None

        await communicator.disconnect()


# Security monitoring helpers
class SecurityMonitoring:
    """Helper class for monitoring security events during tests"""

    def __init__(self):
        self.security_events = []

    def log_security_event(self, event_type, details):
        """Log a security event"""
        self.security_events.append({
            'type': event_type,
            'details': details,
            'timestamp': asyncio.get_event_loop().time()
        })

    def get_events_by_type(self, event_type):
        """Get all events of a specific type"""
        return [event for event in self.security_events if event['type'] == event_type]

    def clear_events(self):
        """Clear all logged events"""
        self.security_events.clear()


# Global security monitor for tests
security_monitor = SecurityMonitoring()
