#!/usr/bin/env python3
"""
WebSocket Testing Suite for Receipt Processing System

This script provides comprehensive WebSocket testing functionality including:
- Connection testing and authentication
- Real-time status monitoring
- Message validation
- Performance and latency testing
- Error handling scenarios
- Concurrent connection testing

Usage:
    python websocket_testing_guide.py --help
    python websocket_testing_guide.py --test-all
    python websocket_testing_guide.py --test-receipt --receipt-id 1
    python websocket_testing_guide.py --performance --connections 10 --duration 60
"""

import asyncio
import websockets
import json
import time
import argparse
import statistics
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import ssl
import logging
import concurrent.futures
from pathlib import Path
import sys
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class WebSocketTestResult:
    """WebSocket test result container"""
    name: str
    passed: bool
    duration: float
    message: str
    data: Optional[Dict] = None
    errors: List[str] = field(default_factory=list)

class WebSocketTester:
    """Main WebSocket testing class"""
    
    def __init__(self, base_url: str = "ws://localhost:8000", token: str = None):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.connections = []
        self.ssl_context = None
        
        # Configure SSL context for WSS
        if base_url.startswith('wss://'):
            self.ssl_context = ssl.create_default_context()
    
    def get_headers(self) -> Dict[str, str]:
        """Get WebSocket connection headers"""
        headers = {}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers
    
    async def test_connection(self, endpoint: str, timeout: int = 10) -> WebSocketTestResult:
        """Test WebSocket connection to endpoint"""
        start_time = time.time()
        uri = f"{self.base_url}{endpoint}"
        
        try:
            # Simple connection without headers for now
            async with websockets.connect(uri, ping_timeout=timeout) as websocket:
                # Test connection is established
                duration = time.time() - start_time
                
                return WebSocketTestResult(
                    name=f"Connection Test - {endpoint}",
                    passed=True,
                    duration=duration,
                    message=f"Successfully connected to {endpoint}",
                    data={'uri': uri, 'state': websocket.state.name}
                )
                
        except websockets.exceptions.InvalidStatusCode as e:
            duration = time.time() - start_time
            return WebSocketTestResult(
                name=f"Connection Test - {endpoint}",
                passed=False,
                duration=duration,
                message=f"Connection rejected with status {e.status_code}",
                errors=[str(e)]
            )
        except Exception as e:
            duration = time.time() - start_time
            return WebSocketTestResult(
                name=f"Connection Test - {endpoint}",
                passed=False,
                duration=duration,
                message=f"Connection failed: {type(e).__name__}",
                errors=[str(e)]
            )
    
    async def test_receipt_progress(self, receipt_id: int, timeout: int = 30) -> WebSocketTestResult:
        """Test receipt progress WebSocket"""
        start_time = time.time()
        endpoint = f"/ws/receipt/{receipt_id}/"
        uri = f"{self.base_url}{endpoint}"
        messages_received = []
        
        try:
            async with websockets.connect(
                uri,
                extra_headers=self.get_headers(),
                ssl=self.ssl_context
            ) as websocket:
                
                # Wait for messages or timeout
                try:
                    while (time.time() - start_time) < timeout:
                        message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        
                        try:
                            data = json.loads(message)
                            messages_received.append({
                                'timestamp': time.time(),
                                'data': data
                            })
                            
                            logger.info(f"Received: {data.get('type', 'unknown')} - {data.get('message', '')}")
                            
                            # Check if processing is complete
                            if data.get('status') in ['completed', 'error', 'review_pending']:
                                break
                                
                        except json.JSONDecodeError:
                            messages_received.append({
                                'timestamp': time.time(),
                                'raw': message
                            })
                            
                except asyncio.TimeoutError:
                    # No more messages, that's okay
                    pass
                
                duration = time.time() - start_time
                
                return WebSocketTestResult(
                    name=f"Receipt Progress - {receipt_id}",
                    passed=len(messages_received) > 0,
                    duration=duration,
                    message=f"Received {len(messages_received)} messages",
                    data={
                        'messages_count': len(messages_received),
                        'messages': messages_received,
                        'final_status': messages_received[-1]['data'].get('status') if messages_received else None
                    }
                )
                
        except Exception as e:
            duration = time.time() - start_time
            return WebSocketTestResult(
                name=f"Receipt Progress - {receipt_id}",
                passed=False,
                duration=duration,
                message=f"Progress monitoring failed: {type(e).__name__}",
                errors=[str(e)]
            )
    
    async def test_inventory_notifications(self, duration_seconds: int = 30) -> WebSocketTestResult:
        """Test inventory notifications WebSocket"""
        start_time = time.time()
        endpoint = "/ws/inventory/"
        uri = f"{self.base_url}{endpoint}"
        notifications_received = []
        
        try:
            async with websockets.connect(
                uri,
                extra_headers=self.get_headers(),
                ssl=self.ssl_context
            ) as websocket:
                
                # Listen for notifications
                end_time = start_time + duration_seconds
                
                while time.time() < end_time:
                    try:
                        message = await asyncio.wait_for(
                            websocket.recv(), 
                            timeout=min(5.0, end_time - time.time())
                        )
                        
                        try:
                            data = json.loads(message)
                            notifications_received.append({
                                'timestamp': time.time(),
                                'data': data
                            })
                            
                            logger.info(f"Inventory notification: {data.get('type', 'unknown')}")
                            
                        except json.JSONDecodeError:
                            notifications_received.append({
                                'timestamp': time.time(),
                                'raw': message
                            })
                            
                    except asyncio.TimeoutError:
                        continue
                
                test_duration = time.time() - start_time
                
                return WebSocketTestResult(
                    name="Inventory Notifications",
                    passed=True,  # Connection succeeded
                    duration=test_duration,
                    message=f"Monitored for {test_duration:.1f}s, received {len(notifications_received)} notifications",
                    data={
                        'notifications_count': len(notifications_received),
                        'notifications': notifications_received
                    }
                )
                
        except Exception as e:
            test_duration = time.time() - start_time
            return WebSocketTestResult(
                name="Inventory Notifications",
                passed=False,
                duration=test_duration,
                message=f"Inventory monitoring failed: {type(e).__name__}",
                errors=[str(e)]
            )
    
    async def test_general_notifications(self, duration_seconds: int = 30) -> WebSocketTestResult:
        """Test general notifications WebSocket"""
        start_time = time.time()
        endpoint = "/ws/notifications/"
        uri = f"{self.base_url}{endpoint}"
        notifications_received = []
        
        try:
            async with websockets.connect(
                uri,
                extra_headers=self.get_headers(),
                ssl=self.ssl_context
            ) as websocket:
                
                # Listen for notifications
                end_time = start_time + duration_seconds
                
                while time.time() < end_time:
                    try:
                        message = await asyncio.wait_for(
                            websocket.recv(), 
                            timeout=min(5.0, end_time - time.time())
                        )
                        
                        try:
                            data = json.loads(message)
                            notifications_received.append({
                                'timestamp': time.time(),
                                'data': data
                            })
                            
                            logger.info(f"General notification: {data.get('type', 'unknown')}")
                            
                        except json.JSONDecodeError:
                            notifications_received.append({
                                'timestamp': time.time(),
                                'raw': message
                            })
                            
                    except asyncio.TimeoutError:
                        continue
                
                test_duration = time.time() - start_time
                
                return WebSocketTestResult(
                    name="General Notifications",
                    passed=True,
                    duration=test_duration,
                    message=f"Monitored for {test_duration:.1f}s, received {len(notifications_received)} notifications",
                    data={
                        'notifications_count': len(notifications_received),
                        'notifications': notifications_received
                    }
                )
                
        except Exception as e:
            test_duration = time.time() - start_time
            return WebSocketTestResult(
                name="General Notifications",
                passed=False,
                duration=test_duration,
                message=f"General notifications failed: {type(e).__name__}",
                errors=[str(e)]
            )
    
    async def test_ping_pong(self, endpoint: str, count: int = 10) -> WebSocketTestResult:
        """Test ping/pong latency"""
        start_time = time.time()
        uri = f"{self.base_url}{endpoint}"
        latencies = []
        errors = []
        
        try:
            async with websockets.connect(
                uri,
                extra_headers=self.get_headers(),
                ssl=self.ssl_context
            ) as websocket:
                
                for i in range(count):
                    ping_start = time.time()
                    
                    try:
                        # Send ping
                        ping_data = {
                            'type': 'ping',
                            'timestamp': ping_start,
                            'sequence': i
                        }
                        
                        await websocket.send(json.dumps(ping_data))
                        
                        # Wait for pong
                        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        pong_time = time.time()
                        
                        try:
                            pong_data = json.loads(response)
                            if pong_data.get('type') == 'pong':
                                latency = (pong_time - ping_start) * 1000  # Convert to ms
                                latencies.append(latency)
                            else:
                                errors.append(f"Unexpected response type: {pong_data.get('type')}")
                        except json.JSONDecodeError:
                            errors.append(f"Invalid JSON response: {response}")
                            
                    except asyncio.TimeoutError:
                        errors.append(f"Timeout on ping {i}")
                    except Exception as e:
                        errors.append(f"Error on ping {i}: {e}")
                    
                    await asyncio.sleep(0.1)  # Brief pause between pings
                
                test_duration = time.time() - start_time
                
                if latencies:
                    avg_latency = statistics.mean(latencies)
                    min_latency = min(latencies)
                    max_latency = max(latencies)
                    
                    return WebSocketTestResult(
                        name=f"Ping/Pong - {endpoint}",
                        passed=len(errors) == 0,
                        duration=test_duration,
                        message=f"Avg latency: {avg_latency:.1f}ms ({len(latencies)}/{count} successful)",
                        data={
                            'avg_latency_ms': avg_latency,
                            'min_latency_ms': min_latency,
                            'max_latency_ms': max_latency,
                            'successful_pings': len(latencies),
                            'total_pings': count,
                            'latencies': latencies
                        },
                        errors=errors
                    )
                else:
                    return WebSocketTestResult(
                        name=f"Ping/Pong - {endpoint}",
                        passed=False,
                        duration=test_duration,
                        message="No successful ping/pong exchanges",
                        errors=errors
                    )
                    
        except Exception as e:
            test_duration = time.time() - start_time
            return WebSocketTestResult(
                name=f"Ping/Pong - {endpoint}",
                passed=False,
                duration=test_duration,
                message=f"Ping/pong test failed: {type(e).__name__}",
                errors=[str(e)] + errors
            )
    
    async def test_authentication(self) -> List[WebSocketTestResult]:
        """Test authentication scenarios"""
        results = []
        
        # Test 1: Valid authentication
        if self.token:
            result = await self.test_connection("/ws/notifications/")
            result.name = "Valid Authentication"
            results.append(result)
        
        # Test 2: No authentication
        original_token = self.token
        self.token = None
        
        start_time = time.time()
        try:
            async with websockets.connect(
                f"{self.base_url}/ws/notifications/",
                extra_headers=self.get_headers(),
                ssl=self.ssl_context
            ) as websocket:
                # Should not reach here if authentication is enforced
                duration = time.time() - start_time
                results.append(WebSocketTestResult(
                    name="No Authentication",
                    passed=False,
                    duration=duration,
                    message="Connection succeeded without authentication (security issue!)"
                ))
                
        except websockets.exceptions.InvalidStatusCode as e:
            duration = time.time() - start_time
            if e.status_code in [401, 403]:
                results.append(WebSocketTestResult(
                    name="No Authentication",
                    passed=True,
                    duration=duration,
                    message=f"Correctly rejected unauthenticated connection (HTTP {e.status_code})"
                ))
            else:
                results.append(WebSocketTestResult(
                    name="No Authentication",
                    passed=False,
                    duration=duration,
                    message=f"Unexpected status code: {e.status_code}"
                ))
        except Exception as e:
            duration = time.time() - start_time
            results.append(WebSocketTestResult(
                name="No Authentication",
                passed=False,
                duration=duration,
                message=f"Unexpected error: {e}",
                errors=[str(e)]
            ))
        
        # Test 3: Invalid token
        self.token = "invalid_token"
        
        start_time = time.time()
        try:
            async with websockets.connect(
                f"{self.base_url}/ws/notifications/",
                extra_headers=self.get_headers(),
                ssl=self.ssl_context
            ) as websocket:
                duration = time.time() - start_time
                results.append(WebSocketTestResult(
                    name="Invalid Authentication",
                    passed=False,
                    duration=duration,
                    message="Connection succeeded with invalid token (security issue!)"
                ))
                
        except websockets.exceptions.InvalidStatusCode as e:
            duration = time.time() - start_time
            if e.status_code in [401, 403]:
                results.append(WebSocketTestResult(
                    name="Invalid Authentication",
                    passed=True,
                    duration=duration,
                    message=f"Correctly rejected invalid token (HTTP {e.status_code})"
                ))
            else:
                results.append(WebSocketTestResult(
                    name="Invalid Authentication",
                    passed=False,
                    duration=duration,
                    message=f"Unexpected status code: {e.status_code}"
                ))
        except Exception as e:
            duration = time.time() - start_time
            results.append(WebSocketTestResult(
                name="Invalid Authentication",
                passed=False,
                duration=duration,
                message=f"Unexpected error: {e}",
                errors=[str(e)]
            ))
        
        # Restore original token
        self.token = original_token
        
        return results
    
    async def test_concurrent_connections(self, endpoint: str, num_connections: int = 10, duration_seconds: int = 30) -> WebSocketTestResult:
        """Test multiple concurrent connections"""
        start_time = time.time()
        uri = f"{self.base_url}{endpoint}"
        
        async def single_connection(connection_id: int):
            """Single connection test"""
            messages_received = 0
            connection_duration = 0
            error = None
            
            try:
                connection_start = time.time()
                async with websockets.connect(
                    uri,
                    extra_headers=self.get_headers(),
                    ssl=self.ssl_context
                ) as websocket:
                    
                    # Listen for messages until timeout
                    end_time = start_time + duration_seconds
                    
                    while time.time() < end_time:
                        try:
                            message = await asyncio.wait_for(
                                websocket.recv(), 
                                timeout=min(2.0, end_time - time.time())
                            )
                            messages_received += 1
                            
                        except asyncio.TimeoutError:
                            continue
                        except websockets.exceptions.ConnectionClosed:
                            break
                    
                    connection_duration = time.time() - connection_start
                    
            except Exception as e:
                error = str(e)
                connection_duration = time.time() - connection_start
            
            return {
                'connection_id': connection_id,
                'messages_received': messages_received,
                'duration': connection_duration,
                'error': error,
                'success': error is None
            }
        
        try:
            # Create concurrent connections
            tasks = [single_connection(i) for i in range(num_connections)]
            connection_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            test_duration = time.time() - start_time
            
            # Analyze results
            successful_connections = []
            failed_connections = []
            total_messages = 0
            
            for result in connection_results:
                if isinstance(result, dict):
                    if result['success']:
                        successful_connections.append(result)
                        total_messages += result['messages_received']
                    else:
                        failed_connections.append(result)
                else:
                    failed_connections.append({'error': str(result), 'connection_id': 'unknown'})
            
            success_rate = len(successful_connections) / num_connections * 100
            
            return WebSocketTestResult(
                name=f"Concurrent Connections - {endpoint}",
                passed=success_rate >= 80,  # 80% success threshold
                duration=test_duration,
                message=f"{len(successful_connections)}/{num_connections} connections successful ({success_rate:.1f}%)",
                data={
                    'total_connections': num_connections,
                    'successful_connections': len(successful_connections),
                    'failed_connections': len(failed_connections),
                    'success_rate': success_rate,
                    'total_messages_received': total_messages,
                    'avg_messages_per_connection': total_messages / len(successful_connections) if successful_connections else 0,
                    'connection_results': connection_results
                }
            )
            
        except Exception as e:
            test_duration = time.time() - start_time
            return WebSocketTestResult(
                name=f"Concurrent Connections - {endpoint}",
                passed=False,
                duration=test_duration,
                message=f"Concurrent connection test failed: {type(e).__name__}",
                errors=[str(e)]
            )
    
    async def test_message_validation(self, endpoint: str) -> List[WebSocketTestResult]:
        """Test various message formats and validation"""
        results = []
        uri = f"{self.base_url}{endpoint}"
        
        test_messages = [
            {
                'name': 'Valid JSON',
                'message': json.dumps({'type': 'test', 'data': 'valid'}),
                'should_pass': True
            },
            {
                'name': 'Invalid JSON',
                'message': '{"invalid": json}',
                'should_pass': False
            },
            {
                'name': 'Empty Message',
                'message': '',
                'should_pass': False
            },
            {
                'name': 'Large Message',
                'message': json.dumps({'type': 'test', 'data': 'x' * 10000}),
                'should_pass': False  # Assuming there are size limits
            },
            {
                'name': 'Special Characters',
                'message': json.dumps({'type': 'test', 'data': '🚀💻📊'}),
                'should_pass': True
            }
        ]
        
        try:
            async with websockets.connect(
                uri,
                extra_headers=self.get_headers(),
                ssl=self.ssl_context
            ) as websocket:
                
                for test_case in test_messages:
                    start_time = time.time()
                    error_occurred = False
                    
                    try:
                        await websocket.send(test_case['message'])
                        
                        # Try to receive a response (or error)
                        try:
                            response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                        except asyncio.TimeoutError:
                            response = None
                        
                    except Exception as e:
                        error_occurred = True
                        response = str(e)
                    
                    duration = time.time() - start_time
                    
                    # Evaluate result
                    if test_case['should_pass']:
                        passed = not error_occurred
                        message = "Message accepted" if passed else f"Message rejected: {response}"
                    else:
                        passed = error_occurred
                        message = "Message correctly rejected" if passed else "Message incorrectly accepted"
                    
                    results.append(WebSocketTestResult(
                        name=f"Message Validation - {test_case['name']}",
                        passed=passed,
                        duration=duration,
                        message=message,
                        data={'test_message': test_case['message'][:100], 'response': str(response)[:100] if response else None}
                    ))
                    
        except Exception as e:
            results.append(WebSocketTestResult(
                name="Message Validation Setup",
                passed=False,
                duration=0,
                message=f"Could not establish connection for message validation: {e}",
                errors=[str(e)]
            ))
        
        return results

def print_test_result(result: WebSocketTestResult):
    """Print formatted test result"""
    status = "✓" if result.passed else "✗"
    print(f"{status} {result.name}: {result.message} ({result.duration:.2f}s)")
    
    if result.errors:
        for error in result.errors:
            print(f"    Error: {error}")

def print_summary(results: List[WebSocketTestResult]):
    """Print test results summary"""
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.passed)
    total_time = sum(r.duration for r in results)
    
    print("\n" + "="*60)
    print("WEBSOCKET TEST SUMMARY")
    print("="*60)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {passed_tests/total_tests*100:.1f}%")
    print(f"Total Time: {total_time:.2f}s")
    
    # Performance metrics
    latency_tests = [r for r in results if r.data and 'avg_latency_ms' in r.data]
    if latency_tests:
        avg_latencies = [r.data['avg_latency_ms'] for r in latency_tests]
        print(f"Average Latency: {statistics.mean(avg_latencies):.1f}ms")
    
    print("="*60)

async def main():
    parser = argparse.ArgumentParser(description="WebSocket Testing Suite for Receipt Processing")
    parser.add_argument("--base-url", default="ws://localhost:8000", help="Base WebSocket URL")
    parser.add_argument("--token", help="Authentication token")
    
    # Test selection
    parser.add_argument("--test-all", action="store_true", help="Run all WebSocket tests")
    parser.add_argument("--test-connection", action="store_true", help="Test basic connections")
    parser.add_argument("--test-receipt", action="store_true", help="Test receipt progress monitoring")
    parser.add_argument("--test-inventory", action="store_true", help="Test inventory notifications")
    parser.add_argument("--test-notifications", action="store_true", help="Test general notifications")
    parser.add_argument("--test-auth", action="store_true", help="Test authentication scenarios")
    parser.add_argument("--test-performance", action="store_true", help="Test performance and latency")
    parser.add_argument("--test-concurrent", action="store_true", help="Test concurrent connections")
    parser.add_argument("--test-messages", action="store_true", help="Test message validation")
    
    # Parameters
    parser.add_argument("--receipt-id", type=int, default=1, help="Receipt ID for testing")
    parser.add_argument("--connections", type=int, default=10, help="Number of concurrent connections")
    parser.add_argument("--duration", type=int, default=30, help="Test duration in seconds")
    parser.add_argument("--pings", type=int, default=10, help="Number of ping/pong tests")
    
    args = parser.parse_args()
    
    # Create tester instance
    tester = WebSocketTester(base_url=args.base_url, token=args.token)
    
    results = []
    
    # Test basic connections
    if args.test_all or args.test_connection:
        print("Testing WebSocket connections...")
        endpoints = ["/ws/notifications/", "/ws/inventory/"]
        
        for endpoint in endpoints:
            result = await tester.test_connection(endpoint)
            print_test_result(result)
            results.append(result)
    
    # Test authentication
    if args.test_all or args.test_auth:
        print("\nTesting authentication scenarios...")
        auth_results = await tester.test_authentication()
        for result in auth_results:
            print_test_result(result)
        results.extend(auth_results)
    
    # Test receipt progress monitoring
    if args.test_all or args.test_receipt:
        print(f"\nTesting receipt progress monitoring (Receipt ID: {args.receipt_id})...")
        result = await tester.test_receipt_progress(args.receipt_id, timeout=args.duration)
        print_test_result(result)
        results.append(result)
    
    # Test inventory notifications
    if args.test_all or args.test_inventory:
        print(f"\nTesting inventory notifications ({args.duration}s)...")
        result = await tester.test_inventory_notifications(args.duration)
        print_test_result(result)
        results.append(result)
    
    # Test general notifications
    if args.test_all or args.test_notifications:
        print(f"\nTesting general notifications ({args.duration}s)...")
        result = await tester.test_general_notifications(args.duration)
        print_test_result(result)
        results.append(result)
    
    # Test performance (ping/pong)
    if args.test_all or args.test_performance:
        print(f"\nTesting performance ({args.pings} ping/pong tests)...")
        result = await tester.test_ping_pong("/ws/notifications/", args.pings)
        print_test_result(result)
        if result.data and 'avg_latency_ms' in result.data:
            print(f"   Average latency: {result.data['avg_latency_ms']:.1f}ms")
            print(f"   Min/Max latency: {result.data['min_latency_ms']:.1f}ms / {result.data['max_latency_ms']:.1f}ms")
        results.append(result)
    
    # Test concurrent connections
    if args.test_all or args.test_concurrent:
        print(f"\nTesting concurrent connections ({args.connections} connections, {args.duration}s)...")
        result = await tester.test_concurrent_connections("/ws/notifications/", args.connections, args.duration)
        print_test_result(result)
        if result.data:
            print(f"   Success rate: {result.data['success_rate']:.1f}%")
            print(f"   Total messages: {result.data['total_messages_received']}")
        results.append(result)
    
    # Test message validation
    if args.test_all or args.test_messages:
        print("\nTesting message validation...")
        message_results = await tester.test_message_validation("/ws/notifications/")
        for result in message_results:
            print_test_result(result)
        results.extend(message_results)
    
    # Print summary
    print_summary(results)
    
    # Return exit code based on results
    return 0 if all(r.passed for r in results) else 1

if __name__ == "__main__":
    exit(asyncio.run(main()))