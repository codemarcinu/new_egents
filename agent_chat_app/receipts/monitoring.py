"""
Performance monitoring and alerting system for receipt processing.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from channels.layers import get_channel_layer
import asyncio

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Monitor and track receipt processing performance."""
    
    # Cache keys
    PERFORMANCE_STATS_KEY = "receipt_performance_stats"
    PROCESSING_TIMES_KEY = "receipt_processing_times"
    ALERT_COOLDOWN_KEY = "alert_cooldown:{alert_type}"
    
    # Alert thresholds
    SLOW_PROCESSING_THRESHOLD = getattr(settings, 'SLOW_PROCESSING_THRESHOLD', 120)  # 2 minutes
    HIGH_FAILURE_RATE_THRESHOLD = getattr(settings, 'HIGH_FAILURE_RATE_THRESHOLD', 0.2)  # 20%
    ALERT_COOLDOWN_MINUTES = getattr(settings, 'ALERT_COOLDOWN_MINUTES', 30)
    
    def __init__(self):
        self.channel_layer = get_channel_layer()
    
    def record_processing_start(self, receipt_id: int) -> None:
        """Record when receipt processing starts."""
        start_time = time.time()
        cache.set(f"processing_start:{receipt_id}", start_time, timeout=3600)
        logger.info(f"Started monitoring receipt {receipt_id}")
    
    def record_processing_step(self, receipt_id: int, step: str, duration: float) -> None:
        """Record processing time for a specific step."""
        step_data = {
            'receipt_id': receipt_id,
            'step': step,
            'duration': duration,
            'timestamp': time.time()
        }
        
        # Store individual step timing
        step_key = f"step_timing:{receipt_id}:{step}"
        cache.set(step_key, step_data, timeout=3600)
        
        # Add to processing times list
        times_key = f"{self.PROCESSING_TIMES_KEY}:{step}"
        recent_times = cache.get(times_key, [])
        recent_times.append(duration)
        
        # Keep only last 100 measurements
        if len(recent_times) > 100:
            recent_times = recent_times[-100:]
            
        cache.set(times_key, recent_times, timeout=3600)
        
        # Check for slow processing alert
        if duration > self.SLOW_PROCESSING_THRESHOLD:
            asyncio.create_task(
                self._send_slow_processing_alert(receipt_id, step, duration)
            )
        
        logger.info(f"Receipt {receipt_id} {step} completed in {duration:.2f}s")
    
    def record_processing_completion(self, receipt_id: int, success: bool, error: str = None) -> None:
        """Record when receipt processing completes."""
        start_time = cache.get(f"processing_start:{receipt_id}")
        if not start_time:
            logger.warning(f"No start time found for receipt {receipt_id}")
            return
        
        total_duration = time.time() - start_time
        
        # Update performance stats
        stats = self._get_performance_stats()
        stats['total_processed'] += 1
        
        if success:
            stats['successful'] += 1
        else:
            stats['failed'] += 1
            stats['recent_failures'].append({
                'receipt_id': receipt_id,
                'error': error,
                'timestamp': time.time()
            })
        
        # Add to processing times
        stats['processing_times'].append(total_duration)
        
        # Keep only last 1000 times and 100 recent failures
        if len(stats['processing_times']) > 1000:
            stats['processing_times'] = stats['processing_times'][-1000:]
        
        if len(stats['recent_failures']) > 100:
            stats['recent_failures'] = stats['recent_failures'][-100:]
        
        # Update cache
        cache.set(self.PERFORMANCE_STATS_KEY, stats, timeout=86400)  # 24 hours
        
        # Clean up individual receipt tracking
        cache.delete(f"processing_start:{receipt_id}")
        
        # Check for high failure rate alert
        failure_rate = self._calculate_recent_failure_rate()
        if failure_rate > self.HIGH_FAILURE_RATE_THRESHOLD:
            asyncio.create_task(
                self._send_high_failure_rate_alert(failure_rate)
            )
        
        logger.info(
            f"Receipt {receipt_id} processing completed in {total_duration:.2f}s, "
            f"success: {success}"
        )
    
    def get_performance_summary(self) -> Dict:
        """Get current performance summary."""
        stats = self._get_performance_stats()
        
        if not stats['processing_times']:
            return {
                'total_processed': 0,
                'success_rate': 0,
                'avg_processing_time': 0,
                'median_processing_time': 0,
                'slow_processing_count': 0
            }
        
        times = sorted(stats['processing_times'])
        avg_time = sum(times) / len(times)
        median_time = times[len(times) // 2]
        slow_count = sum(1 for t in times if t > self.SLOW_PROCESSING_THRESHOLD)
        
        success_rate = (
            stats['successful'] / max(stats['total_processed'], 1)
        ) if stats['total_processed'] > 0 else 0
        
        return {
            'total_processed': stats['total_processed'],
            'successful': stats['successful'],
            'failed': stats['failed'],
            'success_rate': success_rate,
            'avg_processing_time': avg_time,
            'median_processing_time': median_time,
            'slow_processing_count': slow_count,
            'recent_failure_rate': self._calculate_recent_failure_rate()
        }
    
    def get_step_performance(self, step: str) -> Dict:
        """Get performance stats for a specific processing step."""
        times_key = f"{self.PROCESSING_TIMES_KEY}:{step}"
        times = cache.get(times_key, [])
        
        if not times:
            return {'step': step, 'count': 0, 'avg_time': 0, 'max_time': 0}
        
        return {
            'step': step,
            'count': len(times),
            'avg_time': sum(times) / len(times),
            'max_time': max(times),
            'min_time': min(times)
        }
    
    def _get_performance_stats(self) -> Dict:
        """Get or initialize performance stats."""
        default_stats = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'processing_times': [],
            'recent_failures': []
        }
        
        return cache.get(self.PERFORMANCE_STATS_KEY, default_stats)
    
    def _calculate_recent_failure_rate(self) -> float:
        """Calculate failure rate for the last hour."""
        stats = self._get_performance_stats()
        recent_failures = stats['recent_failures']
        
        if not recent_failures:
            return 0.0
        
        one_hour_ago = time.time() - 3600
        recent_count = sum(
            1 for failure in recent_failures 
            if failure['timestamp'] > one_hour_ago
        )
        
        # Get total processed in last hour (approximate)
        total_recent = max(len(recent_failures), 10)  # At least 10 for meaningful rate
        
        return recent_count / total_recent
    
    async def _send_slow_processing_alert(self, receipt_id: int, step: str, duration: float):
        """Send alert for slow processing."""
        alert_type = f"slow_processing_{step}"
        cooldown_key = self.ALERT_COOLDOWN_KEY.format(alert_type=alert_type)
        
        # Check cooldown
        if cache.get(cooldown_key):
            return
        
        # Set cooldown
        cache.set(cooldown_key, True, timeout=self.ALERT_COOLDOWN_MINUTES * 60)
        
        # Send alert to admins
        alert_message = {
            'type': 'system_notification',
            'title': 'Slow Receipt Processing',
            'message': f'Receipt {receipt_id} {step} took {duration:.1f}s (threshold: {self.SLOW_PROCESSING_THRESHOLD}s)',
            'level': 'warning',
            'timestamp': datetime.now().isoformat()
        }
        
        if self.channel_layer:
            await self.channel_layer.group_send(
                'admin_notifications',
                {
                    'type': 'system_notification',
                    **alert_message
                }
            )
        
        logger.warning(
            f"ALERT: Slow processing - Receipt {receipt_id} {step} "
            f"took {duration:.1f}s"
        )
    
    async def _send_high_failure_rate_alert(self, failure_rate: float):
        """Send alert for high failure rate."""
        alert_type = "high_failure_rate"
        cooldown_key = self.ALERT_COOLDOWN_KEY.format(alert_type=alert_type)
        
        # Check cooldown
        if cache.get(cooldown_key):
            return
        
        # Set cooldown
        cache.set(cooldown_key, True, timeout=self.ALERT_COOLDOWN_MINUTES * 60)
        
        # Send alert to admins
        alert_message = {
            'type': 'system_notification',
            'title': 'High Failure Rate',
            'message': f'Receipt processing failure rate is {failure_rate:.1%} (threshold: {self.HIGH_FAILURE_RATE_THRESHOLD:.1%})',
            'level': 'error',
            'timestamp': datetime.now().isoformat()
        }
        
        if self.channel_layer:
            await self.channel_layer.group_send(
                'admin_notifications',
                {
                    'type': 'system_notification',
                    **alert_message
                }
            )
        
        logger.error(
            f"ALERT: High failure rate - {failure_rate:.1%} of receipts failing"
        )


# Global monitor instance
performance_monitor = PerformanceMonitor()


# Convenience functions
def start_monitoring(receipt_id: int):
    """Start monitoring receipt processing."""
    performance_monitor.record_processing_start(receipt_id)


def record_step_timing(receipt_id: int, step: str, duration: float):
    """Record timing for a processing step."""
    performance_monitor.record_processing_step(receipt_id, step, duration)


def complete_monitoring(receipt_id: int, success: bool, error: str = None):
    """Complete monitoring for receipt processing."""
    performance_monitor.record_processing_completion(receipt_id, success, error)


def get_performance_summary():
    """Get current performance summary."""
    return performance_monitor.get_performance_summary()


def get_step_performance(step: str):
    """Get performance for specific step."""
    return performance_monitor.get_step_performance(step)