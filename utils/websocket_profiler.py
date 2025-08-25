"""
WebSocket Profiler Utility

Advanced profiling and debugging tools for WebSocket connections including:
- Connection performance profiling
- Message flow analysis
- Memory usage profiling
- Bottleneck identification
- Performance debugging utilities
"""

import asyncio
import cProfile
import io
import json
import pstats
import time
import tracemalloc
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Union
from unittest.mock import patch, AsyncMock

from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from agent_chat_app.chat.consumers import ChatConsumer
from agent_chat_app.logviewer.consumers import LogStreamConsumer
from agent_chat_app.receipts.consumers import ReceiptProgressConsumer

User = get_user_model()


@dataclass
class ProfilingMetrics:
    """Metrics collected during profiling"""
    start_time: float = 0
    end_time: float = 0
    duration: float = 0
    cpu_time: float = 0
    memory_samples: List[int] = field(default_factory=list)
    function_calls: Dict[str, int] = field(default_factory=dict)
    message_counts: Dict[str, int] = field(default_factory=dict)
    error_counts: Dict[str, int] = field(default_factory=dict)
    latency_samples: List[float] = field(default_factory=list)

    @property
    def total_messages(self) -> int:
        return sum(self.message_counts.values())

    @property
    def total_errors(self) -> int:
        return sum(self.error_counts.values())

    @property
    def avg_latency(self) -> float:
        return sum(self.latency_samples) / max(len(self.latency_samples), 1)

    @property
    def peak_memory(self) -> int:
        return max(self.memory_samples) if self.memory_samples else 0

    @property
    def memory_growth(self) -> int:
        if len(self.memory_samples) >= 2:
            return self.memory_samples[-1] - self.memory_samples[0]
        return 0


@dataclass
class PerformanceReport:
    """Comprehensive performance report"""
    overall_metrics: ProfilingMetrics
    consumer_metrics: Dict[str, ProfilingMetrics] = field(default_factory=dict)
    bottleneck_analysis: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary"""
        return {
            'overall_metrics': {
                'duration': self.overall_metrics.duration,
                'cpu_time': self.overall_metrics.cpu_time,
                'total_messages': self.overall_metrics.total_messages,
                'total_errors': self.overall_metrics.total_errors,
                'avg_latency': self.overall_metrics.avg_latency,
                'peak_memory': self.overall_metrics.peak_memory,
                'memory_growth': self.overall_metrics.memory_growth,
                'function_calls': self.overall_metrics.function_calls,
                'message_counts': self.overall_metrics.message_counts,
                'error_counts': self.overall_metrics.error_counts
            },
            'consumer_metrics': {
                consumer: {
                    'duration': metrics.duration,
                    'cpu_time': metrics.cpu_time,
                    'total_messages': metrics.total_messages,
                    'total_errors': metrics.total_errors,
                    'avg_latency': metrics.avg_latency,
                    'peak_memory': metrics.peak_memory,
                    'function_calls': metrics.function_calls
                }
                for consumer, metrics in self.consumer_metrics.items()
            },
            'bottleneck_analysis': self.bottleneck_analysis,
            'recommendations': self.recommendations,
            'generated_at': self.generated_at
        }

    def to_json(self) -> str:
        """Convert report to JSON string"""
        return json.dumps(self.to_dict(), indent=2)

    def save_report(self, filename: str):
        """Save report to file"""
        with open(filename, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    def print_summary(self):
        """Print a summary of the performance report"""
        print("=" * 60)
        print("WebSocket Performance Profiling Summary")
        print("=" * 60)
        print(f"Duration: {self.overall_metrics.duration:.2f}s")
        print(f"CPU Time: {self.overall_metrics.cpu_time:.2f}s")
        print(f"Total Messages: {self.overall_metrics.total_messages}")
        print(f"Total Errors: {self.overall_metrics.total_errors}")
        print(f"Average Latency: {self.overall_metrics.avg_latency:.3f}s")
        print(f"Peak Memory: {self.overall_metrics.peak_memory / 1024 / 1024:.1f} MB")
        print(f"Memory Growth: {self.overall_metrics.memory_growth / 1024 / 1024:.1f} MB")
        print()
        print("Top Function Calls:")
        for func, count in sorted(self.overall_metrics.function_calls.items(),
                                key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {func}: {count}")
        print()
        print("Recommendations:")
        for rec in self.recommendations:
            print(f"  - {rec}")
        print("=" * 60)


class WebSocketProfiler:
    """Main WebSocket profiling class"""

    def __init__(self):
        self.profiler = cProfile.Profile()
        self.tracemalloc_enabled = False
        self.snapshots = []
        self.metrics = ProfilingMetrics()
        self.consumer_metrics = defaultdict(ProfilingMetrics)
        self.message_queue = asyncio.Queue()
        self.is_profiling = False

    def start_profiling(self):
        """Start profiling"""
        self.is_profiling = True
        self.metrics.start_time = time.time()
        self.profiler.enable()

        if tracemalloc.is_available:
            tracemalloc.start()
            self.tracemalloc_enabled = True

    def stop_profiling(self):
        """Stop profiling and return report"""
        self.is_profiling = False
        self.profiler.disable()

        if self.tracemalloc_enabled:
            tracemalloc.stop()

        self.metrics.end_time = time.time()
        self.metrics.duration = self.metrics.end_time - self.metrics.start_time

        return self._generate_report()

    def _generate_report(self) -> PerformanceReport:
        """Generate comprehensive performance report"""
        # Get CPU profiling stats
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s).sort_stats('cumulative')
        ps.print_stats()

        # Analyze bottlenecks
        bottleneck_analysis = self._analyze_bottlenecks(ps)

        # Generate recommendations
        recommendations = self._generate_recommendations(bottleneck_analysis)

        return PerformanceReport(
            overall_metrics=self.metrics,
            consumer_metrics=dict(self.consumer_metrics),
            bottleneck_analysis=bottleneck_analysis,
            recommendations=recommendations
        )

    def _analyze_bottlenecks(self, stats: pstats.Stats) -> Dict[str, Any]:
        """Analyze performance bottlenecks"""
        analysis = {
            'slow_functions': [],
            'high_call_functions': [],
            'memory_intensive': [],
            'inefficient_patterns': []
        }

        # Analyze function call statistics
        for func, (cc, nc, tt, ct, callers) in stats.stats.items():
            func_name = f"{func[0]}:{func[1]}({func[2]})"

            # Functions with high cumulative time
            if ct > 0.1:  # More than 100ms
                analysis['slow_functions'].append({
                    'function': func_name,
                    'cumulative_time': ct,
                    'calls': nc
                })

            # Functions with high call count
            if nc > 1000:
                analysis['high_call_functions'].append({
                    'function': func_name,
                    'calls': nc,
                    'total_time': tt
                })

        # Analyze memory usage patterns
        if self.metrics.memory_samples:
            memory_growth = self.metrics.memory_growth
            if memory_growth > 50 * 1024 * 1024:  # More than 50MB growth
                analysis['memory_intensive'].append({
                    'type': 'high_memory_growth',
                    'growth_mb': memory_growth / 1024 / 1024,
                    'recommendation': 'Consider implementing memory cleanup or streaming for large data'
                })

        return analysis

    def _generate_recommendations(self, bottleneck_analysis: Dict[str, Any]) -> List[str]:
        """Generate performance recommendations"""
        recommendations = []

        # CPU recommendations
        slow_functions = bottleneck_analysis.get('slow_functions', [])
        if slow_functions:
            recommendations.append(
                f"Optimize {len(slow_functions)} slow functions taking >100ms each"
            )

        # Memory recommendations
        memory_issues = bottleneck_analysis.get('memory_intensive', [])
        if memory_issues:
            recommendations.append(
                "High memory usage detected - consider implementing streaming or pagination"
            )

        # General recommendations based on metrics
        if self.metrics.avg_latency > 1.0:
            recommendations.append(
                "High average latency detected - consider optimizing database queries"
            )

        if self.metrics.total_errors > self.metrics.total_messages * 0.1:
            recommendations.append(
                f"High error rate ({self.metrics.total_errors}/{self.metrics.total_messages}) - investigate error handling"
            )

        if not recommendations:
            recommendations.append("Performance looks good - no major issues detected")

        return recommendations

    async def profile_connection_lifecycle(self, consumer_class, url: str,
                                         user=None, **kwargs) -> ProfilingMetrics:
        """Profile a complete connection lifecycle"""
        consumer_name = consumer_class.__name__

        # Create metrics for this consumer
        if consumer_name not in self.consumer_metrics:
            self.consumer_metrics[consumer_name] = ProfilingMetrics()

        consumer_metrics = self.consumer_metrics[consumer_name]

        start_time = time.time()
        consumer_metrics.start_time = start_time

        # Create communicator
        communicator = WebsocketCommunicator(consumer_class.as_asgi(), url)

        if user:
            communicator.scope["user"] = user

        # Mock channel layer
        with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
            mock_channel_layer.group_add = AsyncMock()
            mock_channel_layer.group_send = AsyncMock()

            # Connect
            connected, _ = await communicator.connect()
            if not connected:
                consumer_metrics.error_counts['connection_failed'] += 1
                return consumer_metrics

            # Simulate message flow
            messages = [
                {"type": "test_message", "content": f"Test {i}"}
                for i in range(10)
            ]

            for message in messages:
                message_start = time.time()

                await communicator.send_json_to(message)
                consumer_metrics.message_counts['sent'] += 1

                # Simulate response time
                await asyncio.sleep(0.01)

                consumer_metrics.latency_samples.append(time.time() - message_start)

            await communicator.disconnect()

        consumer_metrics.end_time = time.time()
        consumer_metrics.duration = consumer_metrics.end_time - consumer_metrics.start_time

        return consumer_metrics

    async def profile_multiple_connections(self, consumer_class, url: str,
                                         count: int = 10, **kwargs) -> Dict[str, ProfilingMetrics]:
        """Profile multiple concurrent connections"""
        tasks = []

        for i in range(count):
            task = asyncio.create_task(
                self.profile_connection_lifecycle(
                    consumer_class,
                    f"{url}_{i}",
                    **kwargs
                )
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        aggregated = ProfilingMetrics()

        for result in results:
            if isinstance(result, ProfilingMetrics):
                aggregated.message_counts = {
                    k: aggregated.message_counts.get(k, 0) + v
                    for k, v in result.message_counts.items()
                }
                aggregated.error_counts = {
                    k: aggregated.error_counts.get(k, 0) + v
                    for k, v in result.error_counts.items()
                }
                aggregated.latency_samples.extend(result.latency_samples)

        return {f"connection_{i}": result for i, result in enumerate(results)}


class PerformanceDebugger:
    """Debugging utilities for WebSocket performance issues"""

    def __init__(self):
        self.debug_info = {}
        self.trace_buffer = deque(maxlen=1000)

    def log_event(self, event_type: str, details: Dict[str, Any]):
        """Log a debugging event"""
        event = {
            'timestamp': time.time(),
            'type': event_type,
            'details': details
        }
        self.trace_buffer.append(event)

    def analyze_message_flow(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze message flow patterns"""
        analysis = {
            'total_messages': len(messages),
            'message_types': defaultdict(int),
            'message_sizes': [],
            'time_gaps': [],
            'error_messages': []
        }

        prev_timestamp = None

        for message in messages:
            # Count message types
            msg_type = message.get('type', 'unknown')
            analysis['message_types'][msg_type] += 1

            # Analyze message size
            message_size = len(json.dumps(message))
            analysis['message_sizes'].append(message_size)

            # Analyze timing
            timestamp = message.get('timestamp', time.time())
            if prev_timestamp is not None:
                gap = timestamp - prev_timestamp
                analysis['time_gaps'].append(gap)
            prev_timestamp = timestamp

            # Check for errors
            if 'error' in message or message.get('type') == 'error':
                analysis['error_messages'].append(message)

        # Calculate statistics
        if analysis['message_sizes']:
            analysis['avg_message_size'] = sum(analysis['message_sizes']) / len(analysis['message_sizes'])
            analysis['max_message_size'] = max(analysis['message_sizes'])
            analysis['min_message_size'] = min(analysis['message_sizes'])

        if analysis['time_gaps']:
            analysis['avg_time_gap'] = sum(analysis['time_gaps']) / len(analysis['time_gaps'])
            analysis['max_time_gap'] = max(analysis['time_gaps'])

        return analysis

    def detect_performance_anomalies(self, metrics: ProfilingMetrics) -> List[str]:
        """Detect performance anomalies"""
        anomalies = []

        # Check for high latency
        if metrics.avg_latency > 2.0:
            anomalies.append(f"High average latency: {metrics.avg_latency:.2f}s")

        # Check for high error rate
        if metrics.total_messages > 0:
            error_rate = metrics.total_errors / metrics.total_messages
            if error_rate > 0.1:
                anomalies.append(f"High error rate: {error_rate:.1%}")

        # Check for memory issues
        if metrics.memory_growth > 100 * 1024 * 1024:  # 100MB
            anomalies.append(f"High memory growth: {metrics.memory_growth / 1024 / 1024:.1f} MB")

        # Check for slow functions
        for func, calls in metrics.function_calls.items():
            if 'sleep' in func.lower() or 'wait' in func.lower():
                if calls > 10:
                    anomalies.append(f"Excessive blocking calls in {func}: {calls}")

        return anomalies


class WebSocketPerformanceMonitor:
    """Real-time performance monitoring for WebSocket connections"""

    def __init__(self):
        self.active_connections = 0
        self.message_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.latency_samples = deque(maxlen=1000)
        self.start_time = time.time()
        self.monitoring = False

    def start_monitoring(self):
        """Start real-time monitoring"""
        self.monitoring = True
        self.start_time = time.time()

    def stop_monitoring(self):
        """Stop monitoring and return summary"""
        self.monitoring = False

        return {
            'monitoring_duration': time.time() - self.start_time,
            'active_connections': self.active_connections,
            'total_messages': sum(self.message_counts.values()),
            'total_errors': sum(self.error_counts.values()),
            'avg_latency': sum(self.latency_samples) / max(len(self.latency_samples), 1),
            'message_counts': dict(self.message_counts),
            'error_counts': dict(self.error_counts)
        }

    def on_connection_opened(self, consumer_type: str):
        """Called when a connection is opened"""
        self.active_connections += 1

    def on_connection_closed(self, consumer_type: str):
        """Called when a connection is closed"""
        self.active_connections = max(0, self.active_connections - 1)

    def on_message_sent(self, consumer_type: str, message_type: str):
        """Called when a message is sent"""
        self.message_counts[f"{consumer_type}.{message_type}"] += 1

    def on_message_received(self, consumer_type: str, message_type: str, latency: float):
        """Called when a message is received"""
        self.latency_samples.append(latency)

    def on_error(self, consumer_type: str, error_type: str):
        """Called when an error occurs"""
        self.error_counts[f"{consumer_type}.{error_type}"] += 1


# Global instances for easy access
profiler = WebSocketProfiler()
debugger = PerformanceDebugger()
monitor = WebSocketPerformanceMonitor()


# Profiling context managers
@asynccontextmanager
async def profile_websocket_operation(operation_name: str):
    """Context manager for profiling WebSocket operations"""
    profiler.start_profiling()

    try:
        yield
    finally:
        report = profiler.stop_profiling()
        report.save_report(f"websocket_profile_{operation_name}_{int(time.time())}.json")
        report.print_summary()


@asynccontextmanager
async def debug_websocket_connection():
    """Context manager for debugging WebSocket connections"""
    monitor.start_monitoring()

    try:
        yield
    finally:
        summary = monitor.stop_monitoring()
        print("Connection Monitoring Summary:")
        print(f"Duration: {summary['monitoring_duration']:.2f}s")
        print(f"Active Connections: {summary['active_connections']}")
        print(f"Total Messages: {summary['total_messages']}")
        print(f"Average Latency: {summary['avg_latency']:.3f}s")


# Utility functions
async def quick_profile_consumer(consumer_class, url: str, message_count: int = 10) -> PerformanceReport:
    """Quick profiling of a consumer"""
    profiler.start_profiling()

    communicator = WebsocketCommunicator(consumer_class.as_asgi(), url)

    with patch.object(communicator.application, 'channel_layer') as mock_channel_layer:
        mock_channel_layer.group_add = AsyncMock()
        mock_channel_layer.group_send = AsyncMock()

        connected, _ = await communicator.connect()
        if connected:
            for i in range(message_count):
                await communicator.send_json_to({
                    "type": "test_message",
                    "content": f"Test {i}"
                })

        await communicator.disconnect()

    return profiler.stop_profiling()


async def compare_consumer_performance(consumer_classes: List, url_template: str,
                                    message_count: int = 50) -> Dict[str, PerformanceReport]:
    """Compare performance of multiple consumers"""
    results = {}

    for consumer_class in consumer_classes:
        print(f"Profiling {consumer_class.__name__}...")

        report = await quick_profile_consumer(
            consumer_class,
            url_template.format(consumer_class.__name__),
            message_count
        )

        results[consumer_class.__name__] = report

    return results


def print_performance_comparison(reports: Dict[str, PerformanceReport]):
    """Print a comparison of performance reports"""
    print("\n" + "=" * 80)
    print("WebSocket Consumer Performance Comparison")
    print("=" * 80)

    print("<30")
    print("-" * 80)

    for consumer_name, report in reports.items():
        metrics = report.overall_metrics
        print("<30"
              "<15.2f"
              "<10")

    print("=" * 80)


if __name__ == "__main__":
    # Example usage
    import sys

    async def main():
        if len(sys.argv) > 1 and sys.argv[1] == "profile":
            print("Profiling WebSocket consumers...")

            # Profile ChatConsumer
            print("\nProfiling ChatConsumer...")
            report = await quick_profile_consumer(ChatConsumer, "/ws/chat/1/", 20)
            report.print_summary()

        elif len(sys.argv) > 1 and sys.argv[1] == "compare":
            print("Comparing WebSocket consumers...")

            consumers = [ChatConsumer, LogStreamConsumer, ReceiptProgressConsumer]
            reports = await compare_consumer_performance(consumers, "/ws/test/{}/")
            print_performance_comparison(reports)

        else:
            print("Usage:")
            print("  python websocket_profiler.py profile  # Profile ChatConsumer")
            print("  python websocket_profiler.py compare  # Compare all consumers")

    # Run the profiler
    asyncio.run(main())
