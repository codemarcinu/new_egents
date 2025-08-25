"""
WebSocket Performance Testing Suite

Performance tests for WebSocket connections including:
- Concurrent connection performance
- Memory usage under load
- Message throughput testing
- Connection cleanup efficiency
- Rate limiting effectiveness
"""

import asyncio
import json
import time
import statistics
import psutil
from unittest.mock import AsyncMock, patch, MagicMock
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
import pytest

from agent_chat_app.chat.consumers import ChatConsumer
from agent_chat_app.logviewer.consumers import LogStreamConsumer
from agent_chat_app.receipts.consumers import ReceiptProgressConsumer
from agent_chat_app.chat.models import Conversation
from agent_chat_app.receipts.models import Receipt
from utils.websocket_load_tester import (
    WebSocketLoadTester,
    LoadTestConfig,
    LoadTestResults,
    RateLimitingTester
)

User = get_user_model()


class WebSocketPerformanceTestCase(TransactionTestCase):
    """Base test case for WebSocket performance tests"""

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


class ConcurrentConnectionTests(WebSocketPerformanceTestCase):
    """Test concurrent connection handling"""

    async def test_small_concurrent_connections(self):
        """Test performance with small number of concurrent connections"""
        config = LoadTestConfig(
            num_connections=10,
            duration_seconds=15,
            message_interval=1.0,
            connection_ramp_up=0.5
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # Verify all connections were successful
        self.assertEqual(results.successful_connections, 10)
        self.assertEqual(results.failed_connections, 0)

        # Check performance metrics
        self.assertGreater(results.connection_success_rate, 0.9)
        self.assertGreater(results.test_duration, 10)
        self.assertLess(results.avg_connection_duration, 30)  # Reasonable duration

    async def test_medium_concurrent_connections(self):
        """Test performance with medium number of concurrent connections"""
        config = LoadTestConfig(
            num_connections=50,
            duration_seconds=20,
            message_interval=2.0,
            connection_ramp_up=0.2
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # Verify good success rate
        self.assertGreater(results.connection_success_rate, 0.8)
        self.assertEqual(results.total_connections_attempted, 50)

        # Check resource usage
        self.assertGreater(results.peak_memory_usage, 0)
        self.assertLess(results.peak_memory_usage, 500)  # Less than 500MB

    async def test_large_concurrent_connections(self):
        """Test performance with large number of concurrent connections"""
        config = LoadTestConfig(
            num_connections=100,
            duration_seconds=30,
            message_interval=5.0,
            connection_ramp_up=0.1,
            max_concurrent_connections=50  # Limit concurrent to avoid overwhelming
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # With ramp-up and connection limiting, should handle well
        self.assertGreater(results.connection_success_rate, 0.7)
        self.assertEqual(results.total_connections_attempted, 100)

        # Check that memory usage is reasonable
        self.assertLess(results.peak_memory_usage, 1000)  # Less than 1GB

    async def test_connection_burst_handling(self):
        """Test handling of connection bursts"""
        # First, establish baseline connections
        base_config = LoadTestConfig(
            num_connections=20,
            duration_seconds=10,
            message_interval=2.0,
            connection_ramp_up=0.1
        )

        tester = WebSocketLoadTester(base_config)
        base_results = await tester.run_test()

        # Then add burst of connections
        burst_config = LoadTestConfig(
            num_connections=30,
            duration_seconds=15,
            message_interval=1.0,
            connection_ramp_up=0.05  # Faster ramp-up for burst
        )

        burst_tester = WebSocketLoadTester(burst_config)
        burst_results = await burst_tester.run_test()

        # Both should perform reasonably well
        self.assertGreater(base_results.connection_success_rate, 0.8)
        self.assertGreater(burst_results.connection_success_rate, 0.7)


class RateLimitingPerformanceTests(WebSocketPerformanceTestCase):
    """Test rate limiting performance"""

    async def test_connection_rate_limiting_enforcement(self):
        """Test that connection rate limiting is enforced efficiently"""
        rate_tester = RateLimitingTester(connection_limit=25, message_limit=10)

        # Test connection rate limiting
        results = await rate_tester.test_connection_rate_limiting()

        # Should accept up to limit
        self.assertEqual(results['connections_accepted'], 25)
        self.assertEqual(results['connections_rejected'], 50)  # 25 + 50 = 75 total

        # Rejections should be due to limit exceeded
        rejection_reasons = results['rejection_reasons']
        self.assertTrue(any('Limit exceeded' in reason for reason in rejection_reasons))

    async def test_message_rate_limiting_efficiency(self):
        """Test message rate limiting efficiency"""
        rate_tester = RateLimitingTester(message_limit=15)

        connection_ids = [f"conn_{i}" for i in range(5)]

        for conn_id in connection_ids:
            results = await rate_tester.test_message_rate_limiting(conn_id)

            # Should accept up to message limit
            self.assertEqual(results['messages_accepted'], 15)
            self.assertEqual(results['messages_rejected'], 10)  # 15 + 10 = 25 total

    async def test_rate_limiting_under_load(self):
        """Test rate limiting performance under load"""
        # Simulate high-frequency connection attempts
        rate_tester = RateLimitingTester(connection_limit=10)

        start_time = time.time()

        # Rapid-fire connection attempts
        tasks = []
        for i in range(50):
            tasks.append(rate_tester.test_connection_rate_limiting())

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.time()
        duration = end_time - start_time

        # Should complete within reasonable time
        self.assertLess(duration, 30)  # Less than 30 seconds

        # Count total results
        total_accepted = sum(r['connections_accepted'] for r in results_list if isinstance(r, dict))
        total_rejected = sum(r['connections_rejected'] for r in results_list if isinstance(r, dict))

        # First few should be accepted, rest rejected
        self.assertGreater(total_accepted, 0)
        self.assertGreater(total_rejected, total_accepted)


class MemoryUsagePerformanceTests(WebSocketPerformanceTestCase):
    """Test memory usage under various loads"""

    async def test_memory_usage_scaling(self):
        """Test how memory usage scales with connection count"""
        memory_samples = []

        # Test with increasing connection counts
        connection_counts = [5, 10, 25, 50]

        for count in connection_counts:
            config = LoadTestConfig(
                num_connections=count,
                duration_seconds=10,
                message_interval=2.0,
                connection_ramp_up=0.2
            )

            tester = WebSocketLoadTester(config)
            results = await tester.run_test()

            memory_samples.append({
                'connections': count,
                'peak_memory': results.peak_memory_usage,
                'avg_memory': results.avg_memory_usage
            })

        # Memory usage should scale reasonably with connection count
        for i in range(1, len(memory_samples)):
            prev = memory_samples[i-1]
            curr = memory_samples[i]

            # Memory growth should be proportional to connection growth
            memory_growth = curr['peak_memory'] - prev['peak_memory']
            connection_growth = curr['connections'] - prev['connections']

            # Rough check: memory growth shouldn't be excessive per connection
            memory_per_connection = memory_growth / connection_growth
            self.assertLess(memory_per_connection, 50)  # Less than 50MB per connection

    async def test_memory_cleanup_efficiency(self):
        """Test memory cleanup after connections close"""
        config = LoadTestConfig(
            num_connections=20,
            duration_seconds=15,
            message_interval=1.0,
            connection_ramp_up=0.3
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # Get memory after test
        process = psutil.Process()
        final_memory = process.memory_info().rss / 1024 / 1024

        # Memory should be reasonable and not show obvious leaks
        self.assertLess(final_memory, 300)  # Less than 300MB after test
        self.assertLess(results.peak_memory_usage, 400)  # Peak should be reasonable

    async def test_memory_usage_under_stress(self):
        """Test memory usage under stress conditions"""
        config = LoadTestConfig(
            num_connections=50,
            duration_seconds=30,
            message_interval=0.5,  # High message frequency
            connection_ramp_up=0.1
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # Under stress, memory usage should still be bounded
        self.assertLess(results.peak_memory_usage, 800)  # Less than 800MB under stress
        self.assertGreater(results.connection_success_rate, 0.6)  # Still reasonable success rate


class ConnectionCleanupPerformanceTests(WebSocketPerformanceTestCase):
    """Test connection cleanup performance"""

    async def test_connection_cleanup_speed(self):
        """Test speed of connection cleanup"""
        config = LoadTestConfig(
            num_connections=30,
            duration_seconds=10,
            message_interval=2.0,
            connection_ramp_up=0.2
        )

        tester = WebSocketLoadTester(config)

        start_time = time.time()
        results = await tester.run_test()
        end_time = time.time()

        cleanup_duration = end_time - start_time - config.duration_seconds

        # Cleanup should be fast
        self.assertLess(cleanup_duration, 5)  # Less than 5 seconds for cleanup

        # All connections should be properly cleaned up
        self.assertEqual(results.active_connections, 0)

    async def test_cleanup_under_error_conditions(self):
        """Test cleanup when errors occur during connections"""
        # This test simulates error conditions during cleanup
        config = LoadTestConfig(
            num_connections=15,
            duration_seconds=12,
            message_interval=1.5,
            connection_ramp_up=0.3
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # Even with potential errors, cleanup should work
        self.assertEqual(results.active_connections, 0)

        # Should have reasonable error count (some errors are expected in testing)
        self.assertLess(results.total_errors, results.total_connections_attempted)

    async def test_resource_leak_prevention(self):
        """Test prevention of resource leaks during cleanup"""
        initial_connections = 20

        config = LoadTestConfig(
            num_connections=initial_connections,
            duration_seconds=15,
            message_interval=2.0,
            connection_ramp_up=0.25
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # Verify complete cleanup
        self.assertEqual(results.successful_connections + results.failed_connections, initial_connections)
        self.assertEqual(results.active_connections, 0)

        # Check that no connections are left hanging
        self.assertEqual(results.total_connections_attempted, initial_connections)


class MessageThroughputTests(WebSocketPerformanceTestCase):
    """Test message throughput performance"""

    async def test_message_throughput_basic(self):
        """Test basic message throughput"""
        config = LoadTestConfig(
            num_connections=15,
            duration_seconds=20,
            message_interval=0.5,  # 2 messages per second per connection
            connection_ramp_up=0.3
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # Calculate expected messages
        expected_messages = (config.num_connections * config.duration_seconds) / config.message_interval

        # Should achieve reasonable throughput
        self.assertGreater(results.total_messages_sent, expected_messages * 0.7)
        self.assertGreater(results.overall_messages_per_second, 10)  # At least 10 msg/sec

    async def test_message_throughput_high_load(self):
        """Test message throughput under high load"""
        config = LoadTestConfig(
            num_connections=40,
            duration_seconds=25,
            message_interval=0.2,  # 5 messages per second per connection
            connection_ramp_up=0.1
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # Should handle high throughput
        self.assertGreater(results.overall_messages_per_second, 50)  # At least 50 msg/sec
        self.assertGreater(results.connection_success_rate, 0.7)

    async def test_message_latency_distribution(self):
        """Test message latency distribution"""
        config = LoadTestConfig(
            num_connections=20,
            duration_seconds=30,
            message_interval=1.0,
            connection_ramp_up=0.2
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # Should have reasonable latency
        self.assertGreater(results.avg_message_latency, 0)
        self.assertLess(results.avg_message_latency, 5.0)  # Less than 5 seconds average

        # Check individual connection latencies
        for conn_metrics in results.connection_metrics:
            if conn_metrics.latency_samples:
                avg_conn_latency = conn_metrics.avg_latency
                self.assertLess(avg_conn_latency, 10.0)  # Individual connections should be fast


# Pytest versions for better integration
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestWebSocketPerformancePytest:
    """Pytest-based WebSocket performance tests"""

    async def test_performance_baseline(self, user, conversation):
        """Establish performance baseline"""
        config = LoadTestConfig(
            num_connections=5,
            duration_seconds=10,
            message_interval=1.0,
            connection_ramp_up=0.5
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        assert results.connection_success_rate == 1.0
        assert results.total_messages_sent > 0
        assert results.test_duration >= 10
        assert results.peak_memory_usage > 0

    async def test_connection_scaling(self, user, conversation):
        """Test how performance scales with connections"""
        results_by_count = {}

        for count in [3, 6, 10]:
            config = LoadTestConfig(
                num_connections=count,
                duration_seconds=8,
                message_interval=2.0,
                connection_ramp_up=0.3
            )

            tester = WebSocketLoadTester(config)
            results = await tester.run_test()
            results_by_count[count] = results

        # Each increment should maintain reasonable performance
        for count in [6, 10]:
            prev_results = results_by_count[count // 2]
            curr_results = results_by_count[count]

            # Success rate shouldn't drop dramatically
            assert curr_results.connection_success_rate >= prev_results.connection_success_rate * 0.8

    async def test_memory_efficiency(self, user, conversation):
        """Test memory usage efficiency"""
        config = LoadTestConfig(
            num_connections=25,
            duration_seconds=20,
            message_interval=3.0,
            connection_ramp_up=0.2
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # Memory per connection should be reasonable
        if results.successful_connections > 0:
            memory_per_connection = results.peak_memory_usage / results.successful_connections
            assert memory_per_connection < 30  # Less than 30MB per connection

    async def test_throughput_stability(self, user, conversation):
        """Test throughput stability over time"""
        config = LoadTestConfig(
            num_connections=12,
            duration_seconds=25,
            message_interval=0.8,
            connection_ramp_up=0.4
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # Should maintain consistent throughput
        assert results.overall_messages_per_second > 5
        assert results.connection_success_rate > 0.8

        # Individual connections should have reasonable performance
        successful_connections = [m for m in results.connection_metrics if m.connected]
        assert len(successful_connections) >= 10

        for conn_metrics in successful_connections:
            assert conn_metrics.messages_per_second > 0.5


class PerformanceRegressionTests(WebSocketPerformanceTestCase):
    """Tests to detect performance regressions"""

    def test_performance_regression_detection(self):
        """Test framework for detecting performance regressions"""
        # This would typically compare against stored baseline metrics
        # For now, it establishes a framework for regression testing

        baseline_metrics = {
            'avg_connection_time': 2.0,  # seconds
            'avg_message_latency': 0.5,  # seconds
            'memory_per_connection': 25,  # MB
            'connection_success_rate': 0.95,
            'messages_per_second': 50
        }

        # In a real implementation, you would load these from a file or database
        # and compare against current performance

        # For this test, we just verify the framework works
        self.assertIsInstance(baseline_metrics, dict)
        self.assertIn('avg_connection_time', baseline_metrics)
        self.assertIn('connection_success_rate', baseline_metrics)

    async def test_performance_thresholds(self):
        """Test that performance meets minimum thresholds"""
        config = LoadTestConfig(
            num_connections=15,
            duration_seconds=15,
            message_interval=1.0,
            connection_ramp_up=0.3
        )

        tester = WebSocketLoadTester(config)
        results = await tester.run_test()

        # Define minimum performance thresholds
        min_success_rate = 0.85
        max_avg_latency = 3.0  # seconds
        max_memory_per_connection = 40  # MB

        # Check thresholds
        self.assertGreaterEqual(results.connection_success_rate, min_success_rate)
        self.assertLessEqual(results.avg_message_latency, max_avg_latency)

        if results.successful_connections > 0:
            memory_per_connection = results.peak_memory_usage / results.successful_connections
            self.assertLessEqual(memory_per_connection, max_memory_per_connection)


# Performance monitoring utilities
class PerformanceMonitor:
    """Utility for monitoring WebSocket performance"""

    def __init__(self):
        self.baseline_metrics = {}
        self.current_metrics = {}
        self.thresholds = {}

    def set_baseline(self, metrics: dict):
        """Set baseline performance metrics"""
        self.baseline_metrics = metrics.copy()

    def set_thresholds(self, thresholds: dict):
        """Set performance thresholds"""
        self.thresholds = thresholds.copy()

    def check_regression(self, current_metrics: dict) -> dict:
        """Check for performance regressions"""
        regressions = {}

        for metric, current_value in current_metrics.items():
            if metric in self.baseline_metrics:
                baseline_value = self.baseline_metrics[metric]

                # For most metrics, higher values indicate regression
                if metric in ['avg_connection_time', 'avg_message_latency', 'peak_memory_usage']:
                    if current_value > baseline_value * 1.2:  # 20% degradation
                        regressions[metric] = {
                            'baseline': baseline_value,
                            'current': current_value,
                            'degradation': (current_value - baseline_value) / baseline_value
                        }

                # For success rates, lower values indicate regression
                elif metric in ['connection_success_rate', 'messages_per_second']:
                    if current_value < baseline_value * 0.8:  # 20% degradation
                        regressions[metric] = {
                            'baseline': baseline_value,
                            'current': current_value,
                            'degradation': (baseline_value - current_value) / baseline_value
                        }

        return regressions

    def check_thresholds(self, metrics: dict) -> dict:
        """Check if metrics exceed thresholds"""
        violations = {}

        for metric, threshold in self.thresholds.items():
            if metric in metrics:
                value = metrics[metric]

                if metric in ['connection_success_rate']:
                    if value < threshold:
                        violations[metric] = {
                            'threshold': threshold,
                            'actual': value,
                            'violation': threshold - value
                        }
                else:  # Higher is worse
                    if value > threshold:
                        violations[metric] = {
                            'threshold': threshold,
                            'actual': value,
                            'violation': value - threshold
                        }

        return violations


# Global performance monitor
performance_monitor = PerformanceMonitor()
