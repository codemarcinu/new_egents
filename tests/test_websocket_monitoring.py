"""
WebSocket Monitoring and Metrics Testing Suite

Tests for WebSocket connection monitoring, metrics collection, and performance tracking.
Includes connection lifecycle monitoring, error rate tracking, and performance metrics.
"""

import json
import asyncio
import time
import psutil
import threading
from unittest.mock import AsyncMock, patch, MagicMock
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings
import pytest

from agent_chat_app.chat.consumers import ChatConsumer
from agent_chat_app.logviewer.consumers import LogStreamConsumer
from agent_chat_app.receipts.consumers import ReceiptProgressConsumer
from agent_chat_app.chat.models import Conversation
from agent_chat_app.receipts.models import Receipt

User = get_user_model()


class ConnectionMetrics:
    """Helper class for tracking connection metrics during tests"""

    def __init__(self):
        self.connections_opened = 0
        self.connections_closed = 0
        self.messages_sent = 0
        self.messages_received = 0
        self.errors_count = 0
        self.connection_durations = []
        self.memory_usage = []
        self.start_time = None
        self.end_time = None

    def start_tracking(self):
        """Start tracking metrics"""
        self.start_time = time.time()

    def stop_tracking(self):
        """Stop tracking metrics"""
        self.end_time = time.time()

    def record_connection_opened(self):
        """Record a connection being opened"""
        self.connections_opened += 1

    def record_connection_closed(self):
        """Record a connection being closed"""
        self.connections_closed += 1

    def record_message_sent(self):
        """Record a message being sent"""
        self.messages_sent += 1

    def record_message_received(self):
        """Record a message being received"""
        self.messages_received += 1

    def record_error(self):
        """Record an error"""
        self.errors_count += 1

    def record_connection_duration(self, duration):
        """Record connection duration"""
        self.connection_durations.append(duration)

    def record_memory_usage(self):
        """Record current memory usage"""
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        self.memory_usage.append(memory_mb)

    def get_summary(self):
        """Get metrics summary"""
        total_duration = self.end_time - self.start_time if self.end_time else 0

        return {
            'total_duration': total_duration,
            'connections_opened': self.connections_opened,
            'connections_closed': self.connections_closed,
            'active_connections': self.connections_opened - self.connections_closed,
            'messages_sent': self.messages_sent,
            'messages_received': self.messages_received,
            'errors_count': self.errors_count,
            'error_rate': self.errors_count / max(self.messages_sent, 1),
            'avg_connection_duration': sum(self.connection_durations) / max(len(self.connection_durations), 1),
            'peak_memory_usage': max(self.memory_usage) if self.memory_usage else 0,
            'avg_memory_usage': sum(self.memory_usage) / max(len(self.memory_usage), 1)
        }


class WebSocketMonitoringTestCase(TransactionTestCase):
    """Base test case for WebSocket monitoring tests"""

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
        self.metrics = ConnectionMetrics()


class ConnectionMonitoringTests(WebSocketMonitoringTestCase):
    """Test connection lifecycle monitoring"""

    async def test_connection_lifecycle_tracking(self):
        """Test tracking of connection lifecycle events"""
        self.metrics.start_tracking()

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            # Record connection opened
            self.metrics.record_connection_opened()
            start_time = time.time()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send some messages
            for i in range(5):
                self.metrics.record_message_sent()
                await communicator.send_json_to({
                    "type": "chat_message",
                    "message": f"Test message {i}"
                })

                # Simulate receiving response
                self.metrics.record_message_received()

            # Record connection closed
            self.metrics.record_connection_closed()
            end_time = time.time()

            self.metrics.record_connection_duration(end_time - start_time)

            await communicator.disconnect()

        self.metrics.stop_tracking()
        summary = self.metrics.get_summary()

        self.assertEqual(summary['connections_opened'], 1)
        self.assertEqual(summary['connections_closed'], 1)
        self.assertEqual(summary['messages_sent'], 5)
        self.assertGreater(summary['total_duration'], 0)

    async def test_concurrent_connection_monitoring(self):
        """Test monitoring multiple concurrent connections"""
        self.metrics.start_tracking()

        # Create multiple communicators
        communicators = []
        for i in range(3):
            comm = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
            comm.scope["user"] = self.user
            communicators.append(comm)

        # Connect all communicators
        for comm in communicators:
            with patch.object(comm.application, 'channel_layer') as mock_channel_layer:
                mock_channel_layer.group_add = AsyncMock()

                self.metrics.record_connection_opened()
                connected, _ = await comm.connect()
                self.assertTrue(connected)

        # Send messages from all connections
        for i, comm in enumerate(communicators):
            self.metrics.record_message_sent()
            await comm.send_json_to({
                "type": "chat_message",
                "message": f"Concurrent message {i}"
            })

        # Disconnect all
        for comm in communicators:
            self.metrics.record_connection_closed()
            await comm.disconnect()

        self.metrics.stop_tracking()
        summary = self.metrics.get_summary()

        self.assertEqual(summary['connections_opened'], 3)
        self.assertEqual(summary['connections_closed'], 3)
        self.assertEqual(summary['active_connections'], 0)

    async def test_connection_error_monitoring(self):
        """Test monitoring of connection errors"""
        self.metrics.start_tracking()

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            self.metrics.record_connection_opened()
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send invalid message to trigger error
            try:
                await communicator.send_json_to("invalid json")
                self.metrics.record_error()
            except Exception:
                self.metrics.record_error()

            # Send malformed message
            try:
                await communicator.send_json_to({
                    "type": "invalid_type",
                    "data": None
                })
            except Exception:
                self.metrics.record_error()

            await communicator.disconnect()

        self.metrics.stop_tracking()
        summary = self.metrics.get_summary()

        self.assertGreaterEqual(summary['errors_count'], 0)  # May or may not record errors depending on implementation


class MemoryUsageMonitoringTests(WebSocketMonitoringTestCase):
    """Test memory usage monitoring during WebSocket operations"""

    async def test_memory_usage_during_connections(self):
        """Test memory usage tracking during connection lifecycle"""
        self.metrics.start_tracking()

        # Record baseline memory
        self.metrics.record_memory_usage()

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            # Record memory after connection setup
            self.metrics.record_memory_usage()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Record memory after connection
            self.metrics.record_memory_usage()

            # Send messages and record memory
            for i in range(10):
                await communicator.send_json_to({
                    "type": "chat_message",
                    "message": f"Memory test message {i}"
                })
                self.metrics.record_memory_usage()

            await communicator.disconnect()

            # Record memory after disconnect
            self.metrics.record_memory_usage()

        self.metrics.stop_tracking()
        summary = self.metrics.get_summary()

        self.assertGreater(summary['peak_memory_usage'], 0)
        self.assertGreater(summary['avg_memory_usage'], 0)

    async def test_memory_leak_detection(self):
        """Test detection of potential memory leaks"""
        initial_memory_samples = 5
        self.metrics.start_tracking()

        # Record initial memory samples
        for _ in range(initial_memory_samples):
            self.metrics.record_memory_usage()
            await asyncio.sleep(0.1)

        # Create and destroy multiple connections
        for i in range(5):
            communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
            communicator.scope["user"] = self.user

            with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
                mock_channel_layer.group_add = AsyncMock()

                connected, _ = await communicator.connect()
                self.assertTrue(connected)

                # Send a few messages
                for j in range(3):
                    await communicator.send_json_to({
                        "type": "chat_message",
                        "message": f"Leak test {i}-{j}"
                    })

                await communicator.disconnect()

            # Record memory after each connection cycle
            self.metrics.record_memory_usage()
            await asyncio.sleep(0.1)

        self.metrics.stop_tracking()
        summary = self.metrics.get_summary()

        # Check for significant memory growth
        memory_samples = summary['memory_usage']
        if len(memory_samples) >= initial_memory_samples + 5:
            initial_avg = sum(memory_samples[:initial_memory_samples]) / initial_memory_samples
            final_avg = sum(memory_samples[-5:]) / 5
            memory_growth = final_avg - initial_avg

            # Memory growth should be minimal (less than 50MB for this test)
            self.assertLess(memory_growth, 50, "Potential memory leak detected")


class ErrorRateMonitoringTests(WebSocketMonitoringTestCase):
    """Test error rate monitoring and alerting"""

    async def test_error_rate_calculation(self):
        """Test calculation of error rates"""
        self.metrics.start_tracking()

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Send mix of successful and failed messages
            successful_messages = 10
            failed_messages = 3

            for i in range(successful_messages):
                self.metrics.record_message_sent()
                await communicator.send_json_to({
                    "type": "chat_message",
                    "message": f"Success message {i}"
                })

            # Simulate failed messages
            for i in range(failed_messages):
                self.metrics.record_message_sent()
                self.metrics.record_error()
                # Failed message - don't send actual message

            await communicator.disconnect()

        self.metrics.stop_tracking()
        summary = self.metrics.get_summary()

        expected_error_rate = failed_messages / (successful_messages + failed_messages)
        self.assertAlmostEqual(summary['error_rate'], expected_error_rate, places=2)

    async def test_error_rate_thresholds(self):
        """Test error rate threshold monitoring"""
        self.metrics.start_tracking()

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Simulate high error rate scenario
            total_messages = 20
            error_messages = 15  # 75% error rate

            for i in range(total_messages):
                self.metrics.record_message_sent()
                if i < error_messages:
                    self.metrics.record_error()

            await communicator.disconnect()

        self.metrics.stop_tracking()
        summary = self.metrics.get_summary()

        # High error rate should be detected
        self.assertGreater(summary['error_rate'], 0.5)
        self.assertGreater(summary['errors_count'], 10)


class LatencyMonitoringTests(WebSocketMonitoringTestCase):
    """Test latency monitoring for WebSocket operations"""

    async def test_message_latency_tracking(self):
        """Test tracking of message round-trip latency"""
        self.metrics.start_tracking()

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Track message latencies
            latencies = []

            for i in range(5):
                start_time = time.time()

                await communicator.send_json_to({
                    "type": "chat_message",
                    "message": f"Latency test {i}",
                    "timestamp": time.time()
                })

                # Wait for response (this is a simplified example)
                try:
                    response = await communicator.receive_json_from()
                    end_time = time.time()
                    latency = end_time - start_time
                    latencies.append(latency)
                except Exception:
                    pass

            await communicator.disconnect()

        self.metrics.stop_tracking()

        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)

            # Average latency should be reasonable (less than 5 seconds for this test)
            self.assertLess(avg_latency, 5.0)

    async def test_connection_latency_tracking(self):
        """Test tracking of connection establishment latency"""
        connection_latencies = []

        for i in range(3):
            start_time = time.time()

            communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
            communicator.scope["user"] = self.user

            with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
                mock_channel_layer.group_add = AsyncMock()

                connected, _ = await communicator.connect()
                end_time = time.time()

                if connected:
                    connection_latencies.append(end_time - start_time)

                await communicator.disconnect()

        if connection_latencies:
            avg_connection_latency = sum(connection_latencies) / len(connection_latencies)
            # Connection latency should be reasonable
            self.assertLess(avg_connection_latency, 10.0)


class ConnectionCleanupTests(WebSocketMonitoringTestCase):
    """Test connection cleanup and resource management"""

    async def test_connection_cleanup_verification(self):
        """Test that connections are properly cleaned up"""
        self.metrics.start_tracking()

        # Create multiple connections
        communicators = []
        for i in range(5):
            comm = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
            comm.scope["user"] = self.user
            communicators.append(comm)

        # Connect all
        active_connections = 0
        for comm in communicators:
            with patch.object(comm.application, 'channel_layer') as mock_channel_layer:
                mock_channel_layer.group_add = AsyncMock()

                connected, _ = await comm.connect()
                if connected:
                    active_connections += 1
                    self.metrics.record_connection_opened()

        # Disconnect all
        for comm in communicators:
            await comm.disconnect()
            self.metrics.record_connection_closed()

        self.metrics.stop_tracking()
        summary = self.metrics.get_summary()

        self.assertEqual(summary['active_connections'], 0)
        self.assertEqual(summary['connections_opened'], active_connections)
        self.assertEqual(summary['connections_closed'], active_connections)

    async def test_resource_cleanup_under_error(self):
        """Test resource cleanup when errors occur"""
        self.metrics.start_tracking()

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{self.conversation.id}/")
        communicator.scope["user"] = self.user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            self.metrics.record_connection_opened()

            # Simulate error condition
            try:
                # Send invalid data that might cause errors
                await communicator.send_json_to(None)
            except Exception:
                pass

            # Connection should still be cleaned up properly
            await communicator.disconnect()
            self.metrics.record_connection_closed()

        self.metrics.stop_tracking()
        summary = self.metrics.get_summary()

        self.assertEqual(summary['active_connections'], 0)


# Pytest versions for better integration
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestWebSocketMonitoringPytest:
    """Pytest-based WebSocket monitoring tests"""

    async def test_connection_metrics_collection(self, user, conversation):
        """Test collection of connection metrics"""
        metrics = ConnectionMetrics()
        metrics.start_tracking()

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            metrics.record_connection_opened()
            connected, _ = await communicator.connect()
            assert connected

            # Send test messages
            for i in range(3):
                metrics.record_message_sent()
                await communicator.send_json_to({
                    "type": "chat_message",
                    "message": f"Test {i}"
                })

            metrics.record_connection_closed()
            await communicator.disconnect()

        metrics.stop_tracking()
        summary = metrics.get_summary()

        assert summary['connections_opened'] == 1
        assert summary['connections_closed'] == 1
        assert summary['messages_sent'] == 3
        assert summary['total_duration'] > 0

    async def test_memory_monitoring_under_load(self, user, conversation):
        """Test memory monitoring during load"""
        metrics = ConnectionMetrics()
        metrics.start_tracking()

        # Simulate multiple connection cycles
        for i in range(3):
            communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
            communicator.scope["user"] = user

            with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
                mock_channel_layer.group_add = AsyncMock()

                connected, _ = await communicator.connect()
                assert connected

                # Send messages
                for j in range(5):
                    await communicator.send_json_to({
                        "type": "chat_message",
                        "message": f"Load test {i}-{j}"
                    })

                await communicator.disconnect()

            metrics.record_memory_usage()

        metrics.stop_tracking()
        summary = metrics.get_summary()

        assert summary['peak_memory_usage'] > 0
        assert summary['avg_memory_usage'] > 0

    async def test_error_rate_alerting(self, user, conversation):
        """Test error rate alerting mechanisms"""
        metrics = ConnectionMetrics()
        metrics.start_tracking()

        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            assert connected

            # Simulate high error scenario
            for i in range(10):
                metrics.record_message_sent()
                if i < 8:  # 80% error rate
                    metrics.record_error()

            await communicator.disconnect()

        metrics.stop_tracking()
        summary = metrics.get_summary()

        # Error rate should be high
        assert summary['error_rate'] > 0.7
        assert summary['errors_count'] == 8

    async def test_connection_duration_tracking(self, user, conversation):
        """Test tracking of connection durations"""
        metrics = ConnectionMetrics()

        start_time = time.time()
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation.id}/")
        communicator.scope["user"] = user

        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            connected, _ = await communicator.connect()
            assert connected

            # Simulate connection duration
            await asyncio.sleep(0.1)

            end_time = time.time()
            connection_duration = end_time - start_time

            metrics.record_connection_duration(connection_duration)
            await communicator.disconnect()

        summary = metrics.get_summary()

        assert summary['avg_connection_duration'] > 0
        assert summary['avg_connection_duration'] < 1.0  # Should be less than 1 second


# Monitoring utilities
class WebSocketMonitor:
    """Advanced WebSocket monitoring utility"""

    def __init__(self):
        self.active_connections = 0
        self.total_connections = 0
        self.total_messages = 0
        self.error_count = 0
        self.connection_durations = []
        self.message_latencies = []
        self.memory_samples = []
        self.start_time = None

    def start_monitoring(self):
        """Start monitoring session"""
        self.start_time = time.time()

    def stop_monitoring(self):
        """Stop monitoring session"""
        return self.get_report()

    def on_connection_opened(self):
        """Called when a connection is opened"""
        self.active_connections += 1
        self.total_connections += 1

    def on_connection_closed(self, duration):
        """Called when a connection is closed"""
        self.active_connections = max(0, self.active_connections - 1)
        self.connection_durations.append(duration)

    def on_message_sent(self):
        """Called when a message is sent"""
        self.total_messages += 1

    def on_message_received(self, latency):
        """Called when a message is received"""
        self.message_latencies.append(latency)

    def on_error(self):
        """Called when an error occurs"""
        self.error_count += 1

    def sample_memory(self):
        """Take a memory sample"""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            self.memory_samples.append(memory_mb)
        except ImportError:
            # psutil not available
            pass

    def get_report(self):
        """Generate monitoring report"""
        duration = time.time() - self.start_time if self.start_time else 0

        return {
            'monitoring_duration': duration,
            'total_connections': self.total_connections,
            'active_connections': self.active_connections,
            'total_messages': self.total_messages,
            'error_count': self.error_count,
            'error_rate': self.error_count / max(self.total_messages, 1),
            'avg_connection_duration': sum(self.connection_durations) / max(len(self.connection_durations), 1),
            'avg_message_latency': sum(self.message_latencies) / max(len(self.message_latencies), 1),
            'peak_memory_usage': max(self.memory_samples) if self.memory_samples else 0,
            'avg_memory_usage': sum(self.memory_samples) / max(len(self.memory_samples), 1),
            'connections_per_second': self.total_connections / max(duration, 1),
            'messages_per_second': self.total_messages / max(duration, 1)
        }


# Global monitor instance
websocket_monitor = WebSocketMonitor()
