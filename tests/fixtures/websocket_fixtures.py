"""
Reusable Test Fixtures for WebSocket Testing

This module provides comprehensive test fixtures for WebSocket testing including:
- User fixtures with different permission levels
- Conversation fixtures for testing chat functionality
- Receipt fixtures for testing receipt processing
- Mock consumers for isolated unit testing
- Test data factories for consistent test data
"""

import json
import asyncio
from typing import Dict, List, Any, Optional
from unittest.mock import AsyncMock, MagicMock
from django.contrib.auth import get_user_model
from django.test import TestCase
from channels.testing import WebsocketCommunicator
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


class WebSocketTestFixtures:
    """Base class for WebSocket test fixtures"""

    def __init__(self):
        self.users = {}
        self.conversations = {}
        self.receipts = {}
        self.communicators = []

    async def setup_users(self) -> Dict[str, User]:
        """Set up test users with different permission levels"""
        self.users = {
            'regular': await self.create_user('regular_user', 'regular@example.com'),
            'staff': await self.create_user('staff_user', 'staff@example.com', is_staff=True),
            'superuser': await self.create_user('superuser', 'superuser@example.com', is_superuser=True),
            'other': await self.create_user('other_user', 'other@example.com'),
            'inactive': await self.create_user('inactive_user', 'inactive@example.com', is_active=False)
        }
        return self.users

    async def create_user(self, username: str, email: str, is_staff: bool = False,
                         is_superuser: bool = False, is_active: bool = True) -> User:
        """Create a test user with specified attributes"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: User.objects.create_user(
                username=username,
                email=email,
                password='testpass123',
                is_staff=is_staff,
                is_superuser=is_superuser,
                is_active=is_active
            )
        )

    async def setup_conversations(self) -> Dict[str, Conversation]:
        """Set up test conversations"""
        await self.setup_users()

        self.conversations = {
            'regular': await self.create_conversation('Regular Conversation', self.users['regular']),
            'staff': await self.create_conversation('Staff Conversation', self.users['staff']),
            'empty': await self.create_conversation('Empty Conversation', self.users['regular']),
            'with_messages': await self.create_conversation_with_messages(
                'Conversation with Messages',
                self.users['regular'],
                num_messages=5
            )
        }
        return self.conversations

    async def create_conversation(self, title: str, user: User) -> Conversation:
        """Create a test conversation"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: Conversation.objects.create(title=title, user=user)
        )

    async def create_conversation_with_messages(self, title: str, user: User,
                                              num_messages: int = 5) -> Conversation:
        """Create a conversation with pre-populated messages"""
        conversation = await self.create_conversation(title, user)

        for i in range(num_messages):
            await self.create_message(
                conversation,
                f"Test message {i}",
                is_from_user=(i % 2 == 0)
            )

        return conversation

    async def create_message(self, conversation: Conversation, text: str,
                           is_from_user: bool = True) -> Message:
        """Create a test message"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: Message.objects.create(
                conversation=conversation,
                text=text,
                is_from_user=is_from_user
            )
        )

    async def setup_receipts(self) -> Dict[str, Receipt]:
        """Set up test receipts"""
        await self.setup_users()

        self.receipts = {
            'processing': await self.create_receipt(self.users['regular'], 'processing'),
            'completed': await self.create_receipt(self.users['regular'], 'completed'),
            'error': await self.create_receipt(self.users['regular'], 'error'),
            'other_user': await self.create_receipt(self.users['other'], 'processing')
        }
        return self.receipts

    async def create_receipt(self, user: User, status: str = 'uploaded') -> Receipt:
        """Create a test receipt"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: Receipt.objects.create(
                user=user,
                file_name=f"test_receipt_{status}.jpg",
                status=status,
                processing_step='uploaded' if status == 'uploaded' else 'completed'
            )
        )

    async def cleanup(self):
        """Clean up all test data"""
        loop = asyncio.get_event_loop()

        # Close all communicators
        for comm in self.communicators:
            try:
                await comm.disconnect()
            except Exception:
                pass

        # Delete test data
        for conversation in self.conversations.values():
            await loop.run_in_executor(None, lambda: conversation.delete())

        for receipt in self.receipts.values():
            await loop.run_in_executor(None, lambda: receipt.delete())

        for user in self.users.values():
            await loop.run_in_executor(None, lambda: user.delete())


class WebSocketCommunicatorFixtures:
    """Fixtures for creating WebSocket communicators"""

    def __init__(self):
        self.fixtures = WebSocketTestFixtures()

    async def setup(self):
        """Set up the fixtures"""
        await self.fixtures.setup_users()
        await self.fixtures.setup_conversations()
        await self.fixtures.setup_receipts()

    async def create_chat_communicator(self, user_key: str = 'regular',
                                     conversation_key: str = 'regular') -> WebsocketCommunicator:
        """Create a ChatConsumer WebSocket communicator"""
        user = self.fixtures.users[user_key]
        conversation = self.fixtures.conversations[conversation_key]

        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f"/ws/chat/{conversation.id}/"
        )
        communicator.scope["user"] = user

        # Mock channel layer to avoid Redis dependency
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            # Connect
            connected, _ = await communicator.connect()
            if not connected:
                raise Exception(f"Failed to connect ChatConsumer for user {user.username}")

        self.fixtures.communicators.append(communicator)
        return communicator

    async def create_log_stream_communicator(self, user_key: str = 'staff') -> WebsocketCommunicator:
        """Create a LogStreamConsumer WebSocket communicator"""
        user = self.fixtures.users[user_key]

        communicator = WebsocketCommunicator(
            LogStreamConsumer.as_asgi(),
            "/ws/logs/"
        )
        communicator.scope["user"] = user

        # Mock channel layer
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            # Connect
            connected, _ = await communicator.connect()
            if not connected:
                raise Exception(f"Failed to connect LogStreamConsumer for user {user.username}")

        self.fixtures.communicators.append(communicator)
        return communicator

    async def create_receipt_communicator(self, user_key: str = 'regular',
                                        receipt_key: str = 'processing') -> WebsocketCommunicator:
        """Create a ReceiptProgressConsumer WebSocket communicator"""
        user = self.fixtures.users[user_key]
        receipt = self.fixtures.receipts[receipt_key]

        communicator = WebsocketCommunicator(
            ReceiptProgressConsumer.as_asgi(),
            f"/ws/receipt/{receipt.id}/"
        )
        communicator.scope["user"] = user

        # Mock channel layer
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            # Connect
            connected, _ = await communicator.connect()
            if not connected:
                raise Exception(f"Failed to connect ReceiptProgressConsumer for user {user.username}")

        self.fixtures.communicators.append(communicator)
        return communicator

    async def create_inventory_communicator(self, user_key: str = 'regular') -> WebsocketCommunicator:
        """Create an InventoryNotificationConsumer WebSocket communicator"""
        user = self.fixtures.users[user_key]

        communicator = WebsocketCommunicator(
            InventoryNotificationConsumer.as_asgi(),
            "/ws/inventory/"
        )
        communicator.scope["user"] = user

        # Mock channel layer
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            # Connect
            connected, _ = await communicator.connect()
            if not connected:
                raise Exception(f"Failed to connect InventoryNotificationConsumer for user {user.username}")

        self.fixtures.communicators.append(communicator)
        return communicator

    async def create_general_notification_communicator(self, user_key: str = 'regular') -> WebsocketCommunicator:
        """Create a GeneralNotificationConsumer WebSocket communicator"""
        user = self.fixtures.users[user_key]

        communicator = WebsocketCommunicator(
            GeneralNotificationConsumer.as_asgi(),
            "/ws/notifications/"
        )
        communicator.scope["user"] = user

        # Mock channel layer
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            # Connect
            connected, _ = await communicator.connect()
            if not connected:
                raise Exception(f"Failed to connect GeneralNotificationConsumer for user {user.username}")

        self.fixtures.communicators.append(communicator)
        return communicator

    async def cleanup(self):
        """Clean up all fixtures and communicators"""
        await self.fixtures.cleanup()


class MockConsumerFixtures:
    """Mock consumers for isolated unit testing"""

    def create_mock_chat_consumer(self) -> MagicMock:
        """Create a mock ChatConsumer for testing"""
        mock_consumer = MagicMock(spec=ChatConsumer)
        mock_consumer.channel_name = "test_channel"
        mock_consumer.room_group_name = "chat_test"
        mock_consumer.scope = {"user": MagicMock()}

        # Mock async methods
        mock_consumer.connect = AsyncMock(return_value=None)
        mock_consumer.disconnect = AsyncMock(return_value=None)
        mock_consumer.receive = AsyncMock(return_value=None)
        mock_consumer.send = AsyncMock(return_value=None)

        # Mock channel layer
        mock_channel_layer = MagicMock()
        mock_channel_layer.group_add = AsyncMock(return_value=None)
        mock_channel_layer.group_discard = AsyncMock(return_value=None)
        mock_channel_layer.group_send = AsyncMock(return_value=None)
        mock_consumer.channel_layer = mock_channel_layer

        return mock_consumer

    def create_mock_log_consumer(self) -> MagicMock:
        """Create a mock LogStreamConsumer for testing"""
        mock_consumer = MagicMock(spec=LogStreamConsumer)
        mock_consumer.channel_name = "test_channel"
        mock_consumer.room_group_name = "log_stream"
        mock_consumer.scope = {"user": MagicMock(is_staff=True)}

        # Mock async methods
        mock_consumer.connect = AsyncMock(return_value=None)
        mock_consumer.disconnect = AsyncMock(return_value=None)
        mock_consumer.receive = AsyncMock(return_value=None)
        mock_consumer.send = AsyncMock(return_value=None)
        mock_consumer.log_entry = AsyncMock(return_value=None)

        # Mock channel layer
        mock_channel_layer = MagicMock()
        mock_channel_layer.group_add = AsyncMock(return_value=None)
        mock_channel_layer.group_discard = AsyncMock(return_value=None)
        mock_consumer.channel_layer = mock_channel_layer

        return mock_consumer

    def create_mock_receipt_consumer(self) -> MagicMock:
        """Create a mock ReceiptProgressConsumer for testing"""
        mock_consumer = MagicMock(spec=ReceiptProgressConsumer)
        mock_consumer.channel_name = "test_channel"
        mock_consumer.room_group_name = "receipt_123"
        mock_consumer.scope = {"user": MagicMock()}

        # Mock async methods
        mock_consumer.connect = AsyncMock(return_value=None)
        mock_consumer.disconnect = AsyncMock(return_value=None)
        mock_consumer.receive = AsyncMock(return_value=None)
        mock_consumer.send = AsyncMock(return_value=None)
        mock_consumer.receipt_status_update = AsyncMock(return_value=None)

        # Mock channel layer
        mock_channel_layer = MagicMock()
        mock_channel_layer.group_add = AsyncMock(return_value=None)
        mock_channel_layer.group_discard = AsyncMock(return_value=None)
        mock_consumer.channel_layer = mock_channel_layer

        return mock_consumer


class TestDataFactories:
    """Factories for generating consistent test data"""

    @staticmethod
    def create_chat_message(user_id: str = "user123", message: str = "Hello",
                          timestamp: Optional[float] = None) -> Dict[str, Any]:
        """Create a standardized chat message"""
        return {
            "type": "chat_message",
            "message": message,
            "user_id": user_id,
            "timestamp": timestamp or asyncio.get_event_loop().time(),
            "message_id": f"msg_{user_id}_{int(asyncio.get_event_loop().time())}"
        }

    @staticmethod
    def create_log_entry(level: str = "INFO", message: str = "Test log",
                        logger: str = "test") -> Dict[str, Any]:
        """Create a standardized log entry"""
        return {
            "type": "log_entry",
            "log": {
                "level": level,
                "message": message,
                "logger": logger,
                "timestamp": asyncio.get_event_loop().time()
            }
        }

    @staticmethod
    def create_receipt_status_update(receipt_id: str = "receipt123",
                                   status: str = "processing",
                                   progress: float = 50.0) -> Dict[str, Any]:
        """Create a standardized receipt status update"""
        return {
            "type": "status_update",
            "receipt_id": receipt_id,
            "status": status,
            "processing_step": "processing",
            "progress_percentage": progress,
            "message": f"Receipt {status}"
        }

    @staticmethod
    def create_inventory_notification(product_name: str = "Test Product",
                                    quantity: int = 10,
                                    threshold: int = 15) -> Dict[str, Any]:
        """Create a standardized inventory notification"""
        return {
            "type": "low_stock_alert",
            "product_name": product_name,
            "current_quantity": quantity,
            "threshold": threshold,
            "message": f"Low stock alert: {product_name} has only {quantity} items left"
        }

    @staticmethod
    def create_general_notification(title: str = "Test Notification",
                                  message: str = "This is a test",
                                  level: str = "info") -> Dict[str, Any]:
        """Create a standardized general notification"""
        return {
            "type": "system_notification",
            "title": title,
            "message": message,
            "level": level,
            "timestamp": asyncio.get_event_loop().time()
        }

    @staticmethod
    def create_websocket_message_batch(count: int = 10,
                                     message_type: str = "chat_message") -> List[Dict[str, Any]]:
        """Create a batch of WebSocket messages for testing"""
        messages = []

        for i in range(count):
            if message_type == "chat_message":
                message = TestDataFactories.create_chat_message(
                    user_id=f"user{i}",
                    message=f"Batch message {i}"
                )
            elif message_type == "log_entry":
                message = TestDataFactories.create_log_entry(
                    level="INFO",
                    message=f"Batch log {i}"
                )
            else:
                message = TestDataFactories.create_general_notification(
                    title=f"Notification {i}",
                    message=f"Batch notification {i}"
                )

            messages.append(message)

        return messages


class WebSocketTestScenarios:
    """Pre-defined test scenarios for common WebSocket testing patterns"""

    @staticmethod
    def scenario_normal_chat_flow() -> List[Dict[str, Any]]:
        """Scenario for normal chat message flow"""
        return [
            TestDataFactories.create_chat_message("user1", "Hello"),
            TestDataFactories.create_chat_message("user2", "Hi there"),
            TestDataFactories.create_chat_message("user1", "How are you?"),
            TestDataFactories.create_chat_message("user2", "I'm good, thanks!"),
            TestDataFactories.create_chat_message("user1", "Great to hear!"),
        ]

    @staticmethod
    def scenario_log_monitoring() -> List[Dict[str, Any]]:
        """Scenario for log monitoring with different log levels"""
        return [
            TestDataFactories.create_log_entry("INFO", "Application started"),
            TestDataFactories.create_log_entry("DEBUG", "Database connection established"),
            TestDataFactories.create_log_entry("WARNING", "High memory usage detected"),
            TestDataFactories.create_log_entry("ERROR", "Failed to process request"),
            TestDataFactories.create_log_entry("INFO", "Application shutdown"),
        ]

    @staticmethod
    def scenario_receipt_processing() -> List[Dict[str, Any]]:
        """Scenario for receipt processing status updates"""
        return [
            TestDataFactories.create_receipt_status_update("receipt1", "uploaded", 0),
            TestDataFactories.create_receipt_status_update("receipt1", "processing", 25),
            TestDataFactories.create_receipt_status_update("receipt1", "processing", 50),
            TestDataFactories.create_receipt_status_update("receipt1", "processing", 75),
            TestDataFactories.create_receipt_status_update("receipt1", "completed", 100),
        ]

    @staticmethod
    def scenario_inventory_alerts() -> List[Dict[str, Any]]:
        """Scenario for inventory alerts"""
        return [
            TestDataFactories.create_inventory_notification("Milk", 5, 10),
            TestDataFactories.create_inventory_notification("Bread", 3, 15),
            TestDataFactories.create_inventory_notification("Eggs", 6, 12),
        ]

    @staticmethod
    def scenario_error_conditions() -> List[Dict[str, Any]]:
        """Scenario for testing error conditions"""
        return [
            {"type": "invalid_message", "data": None},
            {"type": "chat_message", "message": "x" * 10000},  # Oversized message
            {"type": "chat_message", "message": "<script>alert('xss')</script>"},
            {"type": "chat_message", "message": "'; DROP TABLE users; --"},
        ]


# Global fixtures instance for easy access
websocket_fixtures = WebSocketTestFixtures()
communicator_fixtures = WebSocketCommunicatorFixtures()
mock_consumers = MockConsumerFixtures()
test_data = TestDataFactories()
test_scenarios = WebSocketTestScenarios()


# Pytest fixtures
@pytest.fixture
async def setup_websocket_fixtures():
    """Pytest fixture for WebSocket test fixtures"""
    fixtures = WebSocketTestFixtures()
    await fixtures.setup_users()
    await fixtures.setup_conversations()
    await fixtures.setup_receipts()

    yield fixtures

    await fixtures.cleanup()


@pytest.fixture
async def chat_communicator(setup_websocket_fixtures):
    """Pytest fixture for ChatConsumer WebSocket communicator"""
    comm_fixtures = WebSocketCommunicatorFixtures()
    await comm_fixtures.setup()

    communicator = await comm_fixtures.create_chat_communicator()

    yield communicator

    await comm_fixtures.cleanup()


@pytest.fixture
async def log_communicator(setup_websocket_fixtures):
    """Pytest fixture for LogStreamConsumer WebSocket communicator"""
    comm_fixtures = WebSocketCommunicatorFixtures()
    await comm_fixtures.setup()

    communicator = await comm_fixtures.create_log_stream_communicator()

    yield communicator

    await comm_fixtures.cleanup()


@pytest.fixture
async def mock_chat_consumer():
    """Pytest fixture for mock ChatConsumer"""
    mock_consumers = MockConsumerFixtures()
    return mock_consumers.create_mock_chat_consumer()


@pytest.fixture
async def mock_log_consumer():
    """Pytest fixture for mock LogStreamConsumer"""
    mock_consumers = MockConsumerFixtures()
    return mock_consumers.create_mock_log_consumer()
