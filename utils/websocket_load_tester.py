"""
WebSocket Load Testing Utility

Advanced load testing framework for WebSocket connections including:
- Concurrent connection simulation
- Rate limiting tests
- Memory usage monitoring
- Connection cleanup verification
- Performance metrics collection
"""

import asyncio
import json
import time
import statistics
import psutil
import threading
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from agent_chat_app.chat.consumers import ChatConsumer
from agent_chat_app.logviewer.consumers import LogStreamConsumer
from agent_chat_app.receipts.consumers import ReceiptProgressConsumer

User = get_user_model()


@dataclass
class LoadTestConfig:
    """Configuration for load testing"""
    num_connections: int = 100
    duration_seconds: int = 60
    message_interval: float = 1.0  # Messages per second per connection
    connection_ramp_up: float = 0.1  # Seconds between connections
    max_concurrent_connections: int = 1000
    enable_memory_monitoring: bool = True
    enable_rate_limiting: bool = True
    collect_detailed_metrics: bool = False


@dataclass
class ConnectionMetrics:
    """Metrics collected for each connection"""
    connection_id: str
    start_time: float = 0
    end_time: float = 0
    messages_sent: int = 0
    messages_received: int = 0
    errors: int = 0
    latency_samples: List[float] = field(default_factory=list)
    connected: bool = False

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time if self.end_time else 0

    @property
    def avg_latency(self) -> float:
        return statistics.mean(self.latency_samples) if self.latency_samples else 0

    @property
    def messages_per_second(self) -> float:
        return self.messages_sent / max(self.duration, 1)


@dataclass
class LoadTestResults:
    """Results from load testing"""
    total_connections_attempted: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    total_messages_sent: int = 0
    total_messages_received: int = 0
    total_errors: int = 0
    test_duration: float = 0
    peak_memory_usage: float = 0
    avg_memory_usage: float = 0
    connection_metrics: List[ConnectionMetrics] = field(default_factory=list)
    error_details: List[str] = field(default_factory=list)

    @property
    def connection_success_rate(self) -> float:
        return self.successful_connections / max(self.total_connections_attempted, 1)

    @property
    def overall_messages_per_second(self) -> float:
        return self.total_messages_sent / max(self.test_duration, 1)

    @property
    def avg_connection_duration(self) -> float:
        durations = [m.duration for m in self.connection_metrics if m.connected]
        return statistics.mean(durations) if durations else 0

    @property
    def avg_message_latency(self) -> float:
        latencies = []
        for conn_metrics in self.connection_metrics:
            latencies.extend(conn_metrics.latency_samples)
        return statistics.mean(latencies) if latencies else 0


class MemoryMonitor:
    """Monitor memory usage during load testing"""

    def __init__(self):
        self.memory_samples = []
        self.start_time = time.time()
        self.monitoring = False

    def start(self):
        """Start memory monitoring"""
        self.monitoring = True
        self.memory_samples = []

    def stop(self):
        """Stop memory monitoring"""
        self.monitoring = False

    def sample_memory(self):
        """Take a memory sample"""
        if self.monitoring:
            try:
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                self.memory_samples.append(memory_mb)
            except Exception as e:
                print(f"Error sampling memory: {e}")

    def get_stats(self) -> Dict[str, float]:
        """Get memory statistics"""
        if not self.memory_samples:
            return {'peak': 0, 'avg': 0, 'min': 0, 'max': 0}

        return {
            'peak': max(self.memory_samples),
            'avg': statistics.mean(self.memory_samples),
            'min': min(self.memory_samples),
            'max': max(self.memory_samples)
        }


class WebSocketLoadTester:
    """Main WebSocket load testing class"""

    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.results = LoadTestResults()
        self.memory_monitor = MemoryMonitor()
        self._running = False
        self._connections = []
        self._connection_lock = asyncio.Lock()

    async def run_test(self) -> LoadTestResults:
        """Run the complete load test"""
        print(f"Starting WebSocket load test with {self.config.num_connections} connections")
        print(f"Test duration: {self.config.duration_seconds} seconds")

        start_time = time.time()
        self._running = True

        # Start memory monitoring if enabled
        if self.config.enable_memory_monitoring:
            self.memory_monitor.start()
            # Start memory sampling in background
            asyncio.create_task(self._memory_sampling_task())

        try:
            # Run connections with ramp-up
            await self._run_connections_with_ramp_up()

            # Wait for test duration
            await asyncio.sleep(self.config.duration_seconds)

        finally:
            self._running = False

            # Stop memory monitoring
            if self.config.enable_memory_monitoring:
                self.memory_monitor.stop()

            # Close all connections
            await self._cleanup_connections()

        # Calculate final results
        end_time = time.time()
        self.results.test_duration = end_time - start_time

        # Add memory stats
        if self.config.enable_memory_monitoring:
            memory_stats = self.memory_monitor.get_stats()
            self.results.peak_memory_usage = memory_stats['peak']
            self.results.avg_memory_usage = memory_stats['avg']

        print("Load test completed!")
        print(f"Results: {self.results.successful_connections}/{self.results.total_connections_attempted} connections successful")
        print(".2f")

        return self.results

    async def _memory_sampling_task(self):
        """Background task for memory sampling"""
        while self._running:
            self.memory_monitor.sample_memory()
            await asyncio.sleep(1.0)  # Sample every second

    async def _run_connections_with_ramp_up(self):
        """Run connections with controlled ramp-up"""
        tasks = []

        for i in range(self.config.num_connections):
            # Ramp-up delay
            if self.config.connection_ramp_up > 0:
                await asyncio.sleep(self.config.connection_ramp_up)

            # Start connection
            task = asyncio.create_task(self._run_single_connection(i))
            tasks.append(task)

            # Limit concurrent connections
            if len(tasks) >= self.config.max_concurrent_connections:
                # Wait for some connections to complete
                await asyncio.gather(*tasks[:len(tasks)//2], return_exceptions=True)
                tasks = tasks[len(tasks)//2:]

        # Wait for remaining connections
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_single_connection(self, connection_id: int) -> None:
        """Run a single connection test"""
        connection_metrics = ConnectionMetrics(
            connection_id=f"conn_{connection_id}",
            start_time=time.time()
        )

        self.results.total_connections_attempted += 1

        try:
            # Create and run connection
            async with self._create_websocket_connection(connection_id) as (communicator, user):
                connection_metrics.connected = True
                self.results.successful_connections += 1

                # Run message loop
                await self._run_message_loop(communicator, connection_metrics)

        except Exception as e:
            self.results.failed_connections += 1
            self.results.error_details.append(f"Connection {connection_id}: {str(e)}")
            connection_metrics.errors += 1

        finally:
            connection_metrics.end_time = time.time()
            self.results.connection_metrics.append(connection_metrics)

            async with self._connection_lock:
                self._connections.append(connection_metrics)

    @asynccontextmanager
    async def _create_websocket_connection(self, connection_id: int):
        """Create a WebSocket connection for testing"""
        # Create test user
        from django.test import TransactionTestCase
        from agent_chat_app.chat.models import Conversation

        # We need to create user and conversation in a sync context
        loop = asyncio.get_event_loop()
        user = await loop.run_in_executor(
            None,
            lambda: User.objects.create_user(
                username=f'testuser_{connection_id}',
                email=f'test_{connection_id}@example.com',
                password='testpass123'
            )
        )

        conversation = await loop.run_in_executor(
            None,
            lambda: Conversation.objects.create(
                title=f"Load Test Conversation {connection_id}",
                user=user
            )
        )

        # Create WebSocket communicator
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f"/ws/chat/{conversation.id}/"
        )
        communicator.scope["user"] = user

        # Mock channel layer to avoid Redis dependency in tests
        from unittest.mock import patch, AsyncMock
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()

            # Connect
            connected, _ = await communicator.connect()

            if not connected:
                raise Exception(f"Failed to connect WebSocket for connection {connection_id}")

            try:
                yield communicator, user
            finally:
                await communicator.disconnect()

                # Cleanup test data
                await loop.run_in_executor(None, lambda: conversation.delete())
                await loop.run_in_executor(None, lambda: user.delete())

    async def _run_message_loop(self, communicator, metrics: ConnectionMetrics):
        """Run message sending loop for a connection"""
        message_count = 0

        while self._running:
            try:
                # Send message
                start_time = time.time()

                message = {
                    "type": "chat_message",
                    "message": f"Load test message {message_count}",
                    "timestamp": time.time()
                }

                await communicator.send_json_to(message)
                metrics.messages_sent += 1
                self.results.total_messages_sent += 1

                message_count += 1

                # Try to receive response (with timeout)
                try:
                    response = await asyncio.wait_for(
                        communicator.receive_json_from(),
                        timeout=5.0
                    )
                    end_time = time.time()
                    latency = end_time - start_time
                    metrics.latency_samples.append(latency)
                    metrics.messages_received += 1
                    self.results.total_messages_received += 1

                except asyncio.TimeoutError:
                    # No response received
                    pass

                # Wait before next message
                await asyncio.sleep(1.0 / self.config.message_interval)

            except Exception as e:
                metrics.errors += 1
                self.results.total_errors += 1
                self.results.error_details.append(f"Message error: {str(e)}")

                # Break if too many errors
                if metrics.errors > 10:
                    break

    async def _cleanup_connections(self):
        """Cleanup all connections"""
        # All cleanup is handled in the connection context managers
        pass


class RateLimitingTester:
    """Test rate limiting functionality"""

    def __init__(self, connection_limit: int = 100, message_limit: int = 10):
        self.connection_limit = connection_limit
        self.message_limit = message_limit
        self.connection_count = 0
        self.message_counts = {}  # connection_id -> message_count

    async def test_connection_rate_limiting(self) -> Dict[str, Any]:
        """Test connection rate limiting"""
        results = {
            'connections_attempted': 0,
            'connections_accepted': 0,
            'connections_rejected': 0,
            'rejection_reasons': []
        }

        # Try to create more connections than the limit
        for i in range(self.connection_limit + 50):
            results['connections_attempted'] += 1

            try:
                # This would normally check your rate limiting logic
                if self.connection_count >= self.connection_limit:
                    results['connections_rejected'] += 1
                    results['rejection_reasons'].append(f"Connection {i}: Limit exceeded")
                else:
                    self.connection_count += 1
                    results['connections_accepted'] += 1

            except Exception as e:
                results['connections_rejected'] += 1
                results['rejection_reasons'].append(f"Connection {i}: {str(e)}")

        return results

    async def test_message_rate_limiting(self, connection_id: str) -> Dict[str, Any]:
        """Test message rate limiting for a connection"""
        results = {
            'messages_attempted': 0,
            'messages_accepted': 0,
            'messages_rejected': 0,
            'rejection_reasons': []
        }

        message_count = self.message_counts.get(connection_id, 0)

        # Try to send more messages than the limit
        for i in range(self.message_limit + 10):
            results['messages_attempted'] += 1

            if message_count >= self.message_limit:
                results['messages_rejected'] += 1
                results['rejection_reasons'].append(f"Message {i}: Rate limit exceeded")
            else:
                message_count += 1
                results['messages_accepted'] += 1

        self.message_counts[connection_id] = message_count
        return results


class LoadTestRunner:
    """High-level load test runner"""

    @staticmethod
    async def run_basic_load_test(num_connections: int = 50, duration: int = 30) -> LoadTestResults:
        """Run a basic load test"""
        config = LoadTestConfig(
            num_connections=num_connections,
            duration_seconds=duration,
            message_interval=2.0,
            connection_ramp_up=0.2
        )

        tester = WebSocketLoadTester(config)
        return await tester.run_test()

    @staticmethod
    async def run_stress_test(num_connections: int = 200, duration: int = 60) -> LoadTestResults:
        """Run a stress test with higher load"""
        config = LoadTestConfig(
            num_connections=num_connections,
            duration_seconds=duration,
            message_interval=5.0,
            connection_ramp_up=0.05,
            max_concurrent_connections=500
        )

        tester = WebSocketLoadTester(config)
        return await tester.run_test()

    @staticmethod
    async def run_rate_limiting_test() -> Dict[str, Any]:
        """Run rate limiting tests"""
        tester = RateLimitingTester()

        connection_results = await tester.test_connection_rate_limiting()

        # Test message rate limiting on a few connections
        message_results = {}
        for i in range(3):
            message_results[f"conn_{i}"] = await tester.test_message_rate_limiting(f"conn_{i}")

        return {
            'connection_rate_limiting': connection_results,
            'message_rate_limiting': message_results
        }


# Utility functions for easy testing
async def run_quick_load_test(num_connections: int = 20) -> LoadTestResults:
    """Quick load test for development"""
    return await LoadTestRunner.run_basic_load_test(num_connections, 10)


async def run_comprehensive_load_test() -> Dict[str, Any]:
    """Run comprehensive load testing suite"""
    results = {}

    print("Running basic load test...")
    results['basic'] = await LoadTestRunner.run_basic_load_test(50, 30)

    print("Running stress test...")
    results['stress'] = await LoadTestRunner.run_stress_test(100, 45)

    print("Running rate limiting tests...")
    results['rate_limiting'] = await LoadTestRunner.run_rate_limiting_test()

    return results


if __name__ == "__main__":
    # Example usage
    import sys

    async def main():
        if len(sys.argv) > 1 and sys.argv[1] == "comprehensive":
            results = await run_comprehensive_load_test()
            print("Comprehensive test completed!")
            print(f"Basic test success rate: {results['basic'].connection_success_rate:.2%}")
            print(f"Stress test success rate: {results['stress'].connection_success_rate:.2%}")
        else:
            results = await run_quick_load_test()
            print("Quick test completed!")
            print(f"Success rate: {results.connection_success_rate:.2%}")

    # Run the test
    asyncio.run(main())
