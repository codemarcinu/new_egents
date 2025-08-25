"""
Enhanced WebSocket Consumer Testing Suite

Comprehensive tests for WebSocket consumers including:
- Message broadcasting and group management
- Consumer-specific functionality
- Message queuing and persistence
- Real-time features and edge cases
"""

import json
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock, call
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
import pytest

from agent_chat_app.chat.consumers import ChatConsumer
from agent_chat_app.logviewer.consumers import LogStreamConsumer
from agent_chat_app.receipts.consumers import (
    ReceiptProgressConsumer,
    InventoryNotificationConsumer,
    GeneralNotificationConsumer
)
from agent_chat_app.chat.models import Conversation, Message
from agent_chat_app.receipts.models import Receipt

User = get_user_model()


class EnhancedConsumerTestCase(TransactionTestCase):
    """Base test case for enhanced WebSocket consumer tests"""

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
        self.other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='otherpass123'
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


class MessageBroadcastingTests(EnhancedConsumerTestCase):
    """Test message broadcasting and group management"""

    async def test_chat_message_broadcasting(self):
        """Test that chat messages are properly broadcasted to group"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send a chat message
            message_data = {
                "type": "chat_message",
                "message": "Hello everyone!",
                "timestamp": time.time()
            }

            await communicator.send_json_to(message_data)

            # Verify group_send was called with correct data
            mock_channel_layer.group_send.assert_called()

            # Check the call arguments
            call_args = mock_channel_layer.group_send.call_args
            group_name = call_args[0][0]  # First positional argument
            message_dict = call_args[0][1]  # Second positional argument

            self.assertEqual(group_name, f'chat_{self.conversation.id}')
            self.assertEqual(message_dict['type'], 'chat_message')
            self.assertEqual(message_dict['message'], 'Hello everyone!')
            self.assertTrue(message_dict['is_from_user'])

        await communicator.disconnect()

    async def test_group_management_multiple_users(self):
        """Test group management with multiple users"""
        # Create communicators for multiple users
        communicators = []

        for i, user in enumerate([self.user, self.other_user]):
            comm = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
            comm.scope["user"] = user
            communicators.append(comm)

        # Connect all users
        for comm in communicators:
            with patch.object(comm.application, 'channel_layer') as mock_channel_layer:
                mock_channel_layer.group_add = AsyncMock()

                connected, _ = await comm.connect()
                self.assertTrue(connected)

                # Verify group_add was called
                mock_channel_layer.group_add.assert_called()

        # Send message from first user
        message_data = {
            "type": "chat_message",
            "message": "Group message",
            "timestamp": time.time()
        }

        with patch.object(communicators[0].application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_send = AsyncMock()
            await communicators[0].send_json_to(message_data)

            # Should broadcast to group
            mock_channel_layer.group_send.assert_called_once()

        # Disconnect all
        for comm in communicators:
            await comm.disconnect()

    async def test_log_stream_broadcasting(self):
        """Test log stream message broadcasting"""
        communicator = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")
        communicator.scope["user"] = self.staff_user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Simulate log entry being sent to group
            log_entry = {
                "type": "log_entry",
                "log": {
                    "level": "INFO",
                    "message": "Test log message",
                    "timestamp": time.time()
                }
            }

            # Manually call the consumer's log_entry method
            consumer = LogStreamConsumer()
            consumer.channel_name = "test_channel"
            consumer.room_group_name = "log_stream"

            with patch.object(consumer, 'send') as mock_send:
                await consumer.log_entry(log_entry)

                # Verify send was called with correct data
                mock_send.assert_called_once()
                sent_data = json.loads(mock_send.call_args[0][0]['text_data'])
                self.assertEqual(sent_data['type'], 'log_entry')
                self.assertEqual(sent_data['log']['message'], 'Test log message')

        await communicator.disconnect()


class GroupManagementTests(EnhancedConsumerTestCase):
    """Test group creation, cleanup, and membership management"""

    async def test_group_creation_and_cleanup(self):
        """Test proper group creation and cleanup"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_discard = AsyncMock()

            # Connect
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Verify group_add was called
            mock_channel_layer.group_add.assert_called_once_with(
                f'chat_{self.conversation.id}',
                communicator.channel_name
            )

            # Disconnect
            await communicator.disconnect()

            # Verify group_discard was called
            mock_channel_layer.group_discard.assert_called_once_with(
                f'chat_{self.conversation.id}',
                communicator.channel_name
            )

    async def test_multiple_groups_per_user(self):
        """Test user participating in multiple groups"""
        # Create two conversations
        conversation2 = Conversation.objects.create(
            title="Second Conversation",
            user=self.user
        )

        # Connect to first conversation
        comm1 = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        comm1.scope["user"] = self.user

        # Connect to second conversation
        comm2 = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation2.id}/")
        comm2.scope["user"] = self.user

        with patch('channels.layers.InMemoryChannelLayer') as mock_layer:
            # Connect both
            connected1, _ = await comm1.connect()
            connected2, _ = await comm2.connect()

            self.assertTrue(connected1)
            self.assertTrue(connected2)

        await comm1.disconnect()
        await comm2.disconnect()

    async def test_group_membership_isolation(self):
        """Test that groups are properly isolated"""
        # Create conversation for other user
        other_conversation = Conversation.objects.create(
            title="Other Conversation",
            user=self.other_user
        )

        # Connect both users to their respective conversations
        comm1 = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        comm1.scope["user"] = self.user

        comm2 = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{other_conversation.id}/")
        comm2.scope["user"] = self.other_user

        with patch('channels.layers.InMemoryChannelLayer') as mock_layer:
            connected1, _ = await comm1.connect()
            connected2, _ = await comm2.connect()

            self.assertTrue(connected1)
            self.assertTrue(connected2)

            # Send message in first conversation
            with patch.object(comm1.application, 'channel_layer') as mock_channel_layer:
                mock_channel_layer.group_send = AsyncMock()

                message_data = {
                    "type": "chat_message",
                    "message": "Private message",
                    "timestamp": time.time()
                }

                await comm1.send_json_to(message_data)

                # Should only broadcast to first group
                call_args = mock_channel_layer.group_send.call_args
                group_name = call_args[0][0]
                self.assertEqual(group_name, f'chat_{self.conversation.id}')

        await comm1.disconnect()
        await comm2.disconnect()


class MessageQueuingTests(EnhancedConsumerTestCase):
    """Test message queuing and persistence"""

    async def test_message_persistence_chat(self):
        """Test that chat messages are properly persisted"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send a message
            test_message = "This should be saved"
            message_data = {
                "type": "chat_message",
                "message": test_message,
                "timestamp": time.time()
            }

            await communicator.send_json_to(message_data)

            # Verify message was saved to database
            saved_message = await database_sync_to_async(
                lambda: Message.objects.filter(
                    conversation=self.conversation,
                    text=test_message,
                    is_from_user=True
                ).first()
            )()

            self.assertIsNotNone(saved_message)
            self.assertEqual(saved_message.text, test_message)

        await communicator.disconnect()

    async def test_message_queuing_under_load(self):
        """Test message queuing when system is under load"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send multiple messages rapidly
            messages = [f"Message {i}" for i in range(10)]

            for message in messages:
                message_data = {
                    "type": "chat_message",
                    "message": message,
                    "timestamp": time.time()
                }

                await communicator.send_json_to(message_data)

                # Small delay to simulate real usage
                await asyncio.sleep(0.01)

            # Verify all messages were saved
            saved_count = await database_sync_to_async(
                lambda: Message.objects.filter(
                    conversation=self.conversation,
                    is_from_user=True
                ).count()
            )()

            self.assertEqual(saved_count, len(messages))

        await communicator.disconnect()

    async def test_message_order_preservation(self):
        """Test that message order is preserved"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send messages with sequence numbers
            messages = [f"Ordered message {i:02d}" for i in range(5)]

            for message in messages:
                message_data = {
                    "type": "chat_message",
                    "message": message,
                    "timestamp": time.time()
                }

                await communicator.send_json_to(message_data)

            # Verify messages are stored in correct order
            saved_messages = await database_sync_to_async(
                lambda: list(Message.objects.filter(
                    conversation=self.conversation,
                    is_from_user=True
                ).order_by('created_at').values_list('text', flat=True))
            )()

            expected_texts = messages
            self.assertEqual(saved_messages, expected_texts)

        await communicator.disconnect()


class ConsumerSpecificTests(EnhancedConsumerTestCase):
    """Test consumer-specific functionality"""

    async def test_chat_consumer_ai_response_generation(self):
        """Test ChatConsumer AI response generation"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Mock the hybrid RAG service
            with patch('agent_chat_app.chat.consumers.HybridRAGService') as mock_rag:
                mock_instance = mock_rag.return_value
                mock_instance.get_enhanced_response.return_value = (
                    "AI response",
                    MagicMock(confidence=MagicMock(overall=0.9), rag_chunks_used=[])
                )
                mock_instance.format_response_with_transparency.return_value = "Formatted AI response"

                # Send user message
                message_data = {
                    "type": "chat_message",
                    "message": "Hello AI",
                    "timestamp": time.time()
                }

                await communicator.send_json_to(message_data)

                # Verify AI response was triggered
                mock_instance.get_enhanced_response.assert_called_once()

        await communicator.disconnect()

    async def test_receipt_progress_consumer_status_updates(self):
        """Test ReceiptProgressConsumer status updates"""
        communicator = WebsocketCommunicator(
            ReceiptProgressConsumer.as_asgi(),
            f"/ws/receipt/{self.receipt.id}/"
        )
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Request status update
            status_request = {
                "type": "get_status"
            }

            await communicator.send_json_to(status_request)

            # Should receive status response
            response = await communicator.receive_json_from()
            self.assertIsNotNone(response)

        await communicator.disconnect()

    async def test_log_stream_consumer_ping_pong(self):
        """Test LogStreamConsumer ping-pong functionality"""
        communicator = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")
        communicator.scope["user"] = self.staff_user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send ping
            ping_data = {
                "type": "ping",
                "timestamp": time.time()
            }

            await communicator.send_json_to(ping_data)

            # Should receive pong
            response = await communicator.receive_json_from()
            self.assertEqual(response['type'], 'pong')
            self.assertEqual(response['timestamp'], ping_data['timestamp'])

        await communicator.disconnect()

    async def test_notification_consumer_inventory_updates(self):
        """Test InventoryNotificationConsumer functionality"""
        communicator = WebsocketCommunicator(InventoryNotificationConsumer.as_asgi(), "/ws/inventory/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Simulate inventory update being sent to the consumer
            consumer = InventoryNotificationConsumer()
            consumer.channel_name = "test_channel"
            consumer.room_group_name = f'inventory_user_{self.user.id}'

            inventory_data = {
                'type': 'inventory_update',
                'product_name': 'Test Product',
                'new_quantity': 50,
                'unit': 'pieces',
                'message': 'Stock updated'
            }

            with patch.object(consumer, 'send') as mock_send:
                await consumer.inventory_update(inventory_data)

                # Verify correct message format
                mock_send.assert_called_once()
                sent_data = json.loads(mock_send.call_args[0][0]['text_data'])
                self.assertEqual(sent_data['type'], 'inventory_update')
                self.assertEqual(sent_data['product_name'], 'Test Product')

        await communicator.disconnect()


class RealTimeFeaturesTests(EnhancedConsumerTestCase):
    """Test real-time features and edge cases"""

    async def test_typing_indicators(self):
        """Test typing indicator functionality"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Mock the AI response generation to include typing indicators
            with patch('agent_chat_app.chat.consumers.HybridRAGService') as mock_rag:
                mock_instance = mock_rag.return_value
                mock_instance.get_enhanced_response.return_value = (
                    "AI response",
                    MagicMock(confidence=MagicMock(overall=0.9), rag_chunks_used=[])
                )
                mock_instance.format_response_with_transparency.return_value = "Formatted AI response"

                # Send user message
                message_data = {
                    "type": "chat_message",
                    "message": "Hello AI",
                    "timestamp": time.time()
                }

                await communicator.send_json_to(message_data)

                # Verify typing indicators were sent
                typing_calls = [
                    call for call in mock_channel_layer.group_send.call_args_list
                    if call[0][1].get('type') == 'typing_indicator'
                ]

                # Should have at least two typing indicator calls (start and stop)
                self.assertGreaterEqual(len(typing_calls), 2)

        await communicator.disconnect()

    async def test_error_message_handling(self):
        """Test error message handling"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Mock the AI service to raise an exception
            with patch('agent_chat_app.chat.consumers.HybridRAGService') as mock_rag:
                mock_instance = mock_rag.return_value
                mock_instance.get_enhanced_response.side_effect = Exception("AI service error")

                # Send user message that will cause error
                message_data = {
                    "type": "chat_message",
                    "message": "This will cause error",
                    "timestamp": time.time()
                }

                await communicator.send_json_to(message_data)

                # Verify error message was sent
                error_calls = [
                    call for call in mock_channel_layer.group_send.call_args_list
                    if call[0][1].get('type') == 'error_message'
                ]

                self.assertEqual(len(error_calls), 1)
                error_call = error_calls[0]
                self.assertIn('Sorry, I encountered an error', error_call[0][1]['message'])

        await communicator.disconnect()

    async def test_concurrent_message_processing(self):
        """Test processing multiple messages concurrently"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send multiple messages rapidly
            tasks = []
            for i in range(5):
                message_data = {
                    "type": "chat_message",
                    "message": f"Concurrent message {i}",
                    "timestamp": time.time()
                }

                task = communicator.send_json_to(message_data)
                tasks.append(task)

            # Wait for all messages to be sent
            await asyncio.gather(*tasks)

            # Verify all messages were processed
            self.assertEqual(mock_channel_layer.group_send.call_count, 5)

        await communicator.disconnect()


# Pytest versions for better integration
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestWebSocketConsumersPytest:
    """Pytest-based WebSocket consumer tests"""

    async def test_chat_consumer_message_flow(self, user, conversation):
        """Test complete chat consumer message flow"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            connected, _ = await communicator.connect()
            assert connected

            # Mock AI service
            with patch('agent_chat_app.chat.consumers.HybridRAGService') as mock_rag:
                mock_instance = mock_rag.return_value
                mock_instance.get_enhanced_response.return_value = (
                    "Test response",
                    MagicMock(confidence=MagicMock(overall=0.8), rag_chunks_used=[])
                )
                mock_instance.format_response_with_transparency.return_value = "Formatted response"

                # Send message
                await communicator.send_json_to({
                    "type": "chat_message",
                    "message": "Test message",
                    "timestamp": time.time()
                })

                # Verify interactions
                mock_instance.get_enhanced_response.assert_called_once()
                assert mock_channel_layer.group_send.call_count >= 3  # User msg, typing indicators, AI response

        await communicator.disconnect()

    async def test_consumer_isolation(self, user, conversation, staff_user):
        """Test that different consumers don't interfere with each other"""
        # Chat consumer
        chat_comm = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        chat_comm.scope["user"] = user

        # Log consumer
        log_comm = WebsocketCommunicator(LogStreamConsumer.as_asgi(), "/ws/logs/")
        log_comm.scope["user"] = staff_user

        with patch('channels.layers.InMemoryChannelLayer'):
            # Connect both
            chat_connected, _ = await chat_comm.connect()
            log_connected, _ = await log_comm.connect()

            assert chat_connected
            assert log_connected

            # Send message to chat
            with patch.object(chat_comm.application, 'channel_layer') as chat_mock:
                chat_mock.group_send = AsyncMock()

                await chat_comm.send_json_to({
                    "type": "chat_message",
                    "message": "Chat message",
                    "timestamp": time.time()
                })

                # Should only affect chat consumer
                chat_mock.group_send.assert_called()
                call_args = chat_mock.group_send.call_args[0]
                assert call_args[0] == f'chat_{conversation.id}'

        await chat_comm.disconnect()
        await log_comm.disconnect()

    async def test_message_validation(self, user, conversation):
        """Test message validation and sanitization"""
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            connected, _ = await communicator.connect()
            assert connected

            # Test various message types
            test_cases = [
                {"type": "chat_message", "message": "Normal message"},
                {"type": "chat_message", "message": ""},  # Empty message
                {"type": "chat_message", "message": "A" * 10000},  # Very long message
            ]

            for test_case in test_cases:
                test_case["timestamp"] = time.time()
                await communicator.send_json_to(test_case)

            # Should handle all cases gracefully
            assert mock_channel_layer.group_send.call_count == len(test_cases)

        await communicator.disconnect()


class ConsumerEdgeCaseTests(EnhancedConsumerTestCase):
    """Test edge cases and error conditions"""

    async def test_rapid_connect_disconnect(self):
        """Test rapid connect/disconnect cycles"""
        for i in range(10):
            communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
            communicator.scope["user"] = self.user

            with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
                mock_channel_layer.group_add = AsyncMock()
                mock_channel_layer.group_discard = AsyncMock()

                connected, _ = await communicator.connect()
                self.assertTrue(connected)

                # Quick disconnect
                await communicator.disconnect()

                # Verify cleanup
                mock_channel_layer.group_discard.assert_called()

    async def test_memory_usage_under_sustained_load(self):
        """Test memory usage with sustained message load"""
        import psutil

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send sustained load
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024

            for i in range(50):
                await communicator.send_json_to({
                    "type": "chat_message",
                    "message": f"Sustained load message {i}",
                    "timestamp": time.time()
                })

                if i % 10 == 0:
                    await asyncio.sleep(0.1)  # Small delay every 10 messages

            end_memory = psutil.Process().memory_info().rss / 1024 / 1024
            memory_growth = end_memory - start_memory

            # Memory growth should be reasonable (less than 100MB)
            self.assertLess(memory_growth, 100)

        await communicator.disconnect()

    async def test_concurrent_consumer_instances(self):
        """Test multiple instances of the same consumer"""
        # Create multiple instances of the same conversation
        communicators = []

        for i in range(5):
            comm = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
            comm.scope["user"] = self.user
            communicators.append(comm)

        # Connect all
        for comm in communicators:
            with patch.object(comm.application, 'channel_layer') as mock_channel_layer:
                mock_channel_layer.group_add = AsyncMock()

                connected, _ = await comm.connect()
                self.assertTrue(connected)

        # Send message from one
        with patch.object(communicators[0].application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_send = AsyncMock()

            await communicators[0].send_json_to({
                "type": "chat_message",
                "message": "Broadcast message",
                "timestamp": time.time()
            })

            # Should broadcast to group once
            mock_channel_layer.group_send.assert_called_once()

        # Disconnect all
        for comm in communicators:
            await comm.disconnect()
