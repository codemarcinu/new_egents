#!/usr/bin/env python3
"""
Master Test Runner for Receipt Processing System

This script orchestrates all testing procedures including:
- System health checks
- API endpoint testing
- WebSocket functionality testing
- Pipeline end-to-end testing
- Performance and load testing
- Error scenario validation

Usage:
    python run_all_tests.py --help
    python run_all_tests.py --quick
    python run_all_tests.py --full --output-report test_results.json
    python run_all_tests.py --performance --load-test
"""

import asyncio
import json
import time
import argparse
import sys
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import subprocess
import requests
import concurrent.futures

# Import our testing modules
from api_testing_guide import APITester, TestResult
from websocket_testing_guide import WebSocketTester, WebSocketTestResult

@dataclass
class TestSuiteResult:
    """Overall test suite result"""
    name: str
    passed: bool
    duration: float
    total_tests: int
    passed_tests: int
    failed_tests: int
    details: List[Dict[str, Any]]
    errors: List[str]
    timestamp: str

class MasterTestRunner:
    """Orchestrates all testing procedures"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.results = []
        self.start_time = time.time()
        
        # Initialize testers
        self.api_tester = APITester(
            base_url=config.get('api_base_url', 'http://localhost:8000'),
            token=config.get('token')
        )
        
        self.ws_tester = WebSocketTester(
            base_url=config.get('ws_base_url', 'ws://localhost:8000'),
            token=config.get('token')
        )
    
    def check_system_health(self) -> TestSuiteResult:
        """Comprehensive system health check"""
        start_time = time.time()
        health_checks = []
        errors = []
        
        print("🔍 Running System Health Checks...")
        
        # Check 1: Django server
        try:
            response = requests.get(f"{self.config.get('api_base_url', 'http://localhost:8000')}/health/", timeout=10)
            health_checks.append({
                'name': 'Django Server',
                'passed': response.status_code == 200,
                'message': f"HTTP {response.status_code}",
                'duration': response.elapsed.total_seconds()
            })
        except Exception as e:
            health_checks.append({
                'name': 'Django Server',
                'passed': False,
                'message': f"Connection failed: {e}",
                'duration': 0
            })
            errors.append(f"Django server check failed: {e}")
        
        # Check 2: Redis
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, decode_responses=True)
            r.ping()
            health_checks.append({
                'name': 'Redis Server',
                'passed': True,
                'message': "Connection successful",
                'duration': 0.1
            })
        except Exception as e:
            health_checks.append({
                'name': 'Redis Server',
                'passed': False,
                'message': f"Connection failed: {e}",
                'duration': 0
            })
            errors.append(f"Redis check failed: {e}")
        
        # Check 3: Celery
        try:
            result = subprocess.run(['celery', '-A', 'config.celery_app', 'status'], 
                                  capture_output=True, text=True, timeout=10)
            health_checks.append({
                'name': 'Celery Workers',
                'passed': result.returncode == 0,
                'message': "Workers active" if result.returncode == 0 else "No active workers",
                'duration': 1.0
            })
        except Exception as e:
            health_checks.append({
                'name': 'Celery Workers',
                'passed': False,
                'message': f"Check failed: {e}",
                'duration': 0
            })
            errors.append(f"Celery check failed: {e}")
        
        # Check 4: Database
        try:
            response = requests.get(f"{self.config.get('api_base_url')}/api/receipts/stats/",
                                  headers={'Authorization': f'Bearer {self.config.get("token")}'} if self.config.get('token') else {},
                                  timeout=10)
            health_checks.append({
                'name': 'Database Access',
                'passed': response.status_code in [200, 401],  # 401 is ok if no token
                'message': f"HTTP {response.status_code}",
                'duration': response.elapsed.total_seconds()
            })
        except Exception as e:
            health_checks.append({
                'name': 'Database Access',
                'passed': False,
                'message': f"Query failed: {e}",
                'duration': 0
            })
            errors.append(f"Database check failed: {e}")
        
        # Check 5: Ollama (if configured)
        try:
            response = requests.get('http://localhost:11434/api/tags', timeout=5)
            health_checks.append({
                'name': 'Ollama Service',
                'passed': response.status_code == 200,
                'message': "Service running" if response.status_code == 200 else f"HTTP {response.status_code}",
                'duration': response.elapsed.total_seconds()
            })
        except Exception as e:
            health_checks.append({
                'name': 'Ollama Service',
                'passed': False,
                'message': f"Service unavailable: {e}",
                'duration': 0
            })
            # Don't add to errors - Ollama might not be required
        
        duration = time.time() - start_time
        passed_checks = sum(1 for check in health_checks if check['passed'])
        
        return TestSuiteResult(
            name="System Health Check",
            passed=len(errors) == 0 and passed_checks >= 3,  # At least core services
            duration=duration,
            total_tests=len(health_checks),
            passed_tests=passed_checks,
            failed_tests=len(health_checks) - passed_checks,
            details=health_checks,
            errors=errors,
            timestamp=datetime.now().isoformat()
        )
    
    def run_api_tests(self, test_file: str = None) -> TestSuiteResult:
        """Run comprehensive API tests"""
        start_time = time.time()
        api_results = []
        errors = []
        
        print("🔗 Running API Tests...")
        
        try:
            # Basic functionality tests
            health_result = self.api_tester.test_health_check()
            api_results.append(asdict(health_result))
            
            stats_result = self.api_tester.test_statistics()
            api_results.append(asdict(stats_result))
            
            # Upload and processing test (if test file provided)
            if test_file and Path(test_file).exists():
                print(f"   Testing with file: {test_file}")
                upload_result = self.api_tester.test_receipt_upload(test_file)
                api_results.append(asdict(upload_result))
                
                if upload_result.passed and upload_result.data:
                    receipt_id = upload_result.data['receipt_id']
                    
                    # Monitor processing
                    processing_result = self.api_tester.monitor_receipt_processing(receipt_id, timeout=120)
                    api_results.append(asdict(processing_result))
                    
                    # Get details
                    details_result = self.api_tester.test_receipt_details(receipt_id)
                    api_results.append(asdict(details_result))
            
            # Error scenario tests
            error_results = self.api_tester.test_error_scenarios()
            for result in error_results:
                api_results.append(asdict(result))
            
        except Exception as e:
            errors.append(f"API testing failed: {e}")
        
        duration = time.time() - start_time
        passed_tests = sum(1 for result in api_results if result['passed'])
        
        return TestSuiteResult(
            name="API Tests",
            passed=len(errors) == 0 and len(api_results) > 0,
            duration=duration,
            total_tests=len(api_results),
            passed_tests=passed_tests,
            failed_tests=len(api_results) - passed_tests,
            details=api_results,
            errors=errors,
            timestamp=datetime.now().isoformat()
        )
    
    async def run_websocket_tests(self, receipt_id: int = None) -> TestSuiteResult:
        """Run comprehensive WebSocket tests"""
        start_time = time.time()
        ws_results = []
        errors = []
        
        print("🔌 Running WebSocket Tests...")
        
        try:
            # Connection tests
            connection_result = await self.ws_tester.test_connection("/ws/notifications/")
            ws_results.append(asdict(connection_result))
            
            # Authentication tests
            auth_results = await self.ws_tester.test_authentication()
            for result in auth_results:
                ws_results.append(asdict(result))
            
            # Performance tests
            ping_result = await self.ws_tester.test_ping_pong("/ws/notifications/", count=5)
            ws_results.append(asdict(ping_result))
            
            # Receipt monitoring (if receipt_id provided)
            if receipt_id:
                receipt_result = await self.ws_tester.test_receipt_progress(receipt_id, timeout=30)
                ws_results.append(asdict(receipt_result))
            
            # Notification tests
            notif_result = await self.ws_tester.test_general_notifications(duration_seconds=10)
            ws_results.append(asdict(notif_result))
            
        except Exception as e:
            errors.append(f"WebSocket testing failed: {e}")
        
        duration = time.time() - start_time
        passed_tests = sum(1 for result in ws_results if result['passed'])
        
        return TestSuiteResult(
            name="WebSocket Tests",
            passed=len(errors) == 0 and len(ws_results) > 0,
            duration=duration,
            total_tests=len(ws_results),
            passed_tests=passed_tests,
            failed_tests=len(ws_results) - passed_tests,
            details=ws_results,
            errors=errors,
            timestamp=datetime.now().isoformat()
        )
    
    def run_performance_tests(self, test_file: str = None) -> TestSuiteResult:
        """Run performance and load tests"""
        start_time = time.time()
        perf_results = []
        errors = []
        
        print("⚡ Running Performance Tests...")
        
        try:
            if test_file and Path(test_file).exists():
                # API performance test
                perf_result = self.api_tester.performance_test(
                    test_file, 
                    num_receipts=self.config.get('perf_receipts', 10),
                    max_workers=self.config.get('perf_workers', 3)
                )
                perf_results.append(asdict(perf_result))
            else:
                errors.append("No test file provided for performance testing")
        
        except Exception as e:
            errors.append(f"Performance testing failed: {e}")
        
        duration = time.time() - start_time
        passed_tests = sum(1 for result in perf_results if result['passed'])
        
        return TestSuiteResult(
            name="Performance Tests",
            passed=len(errors) == 0 and len(perf_results) > 0,
            duration=duration,
            total_tests=len(perf_results),
            passed_tests=passed_tests,
            failed_tests=len(perf_results) - passed_tests,
            details=perf_results,
            errors=errors,
            timestamp=datetime.now().isoformat()
        )
    
    async def run_concurrent_websocket_tests(self) -> TestSuiteResult:
        """Run concurrent WebSocket connection tests"""
        start_time = time.time()
        concurrent_results = []
        errors = []
        
        print("🔀 Running Concurrent WebSocket Tests...")
        
        try:
            # Test concurrent connections
            concurrent_result = await self.ws_tester.test_concurrent_connections(
                "/ws/notifications/",
                num_connections=self.config.get('concurrent_connections', 5),
                duration_seconds=self.config.get('concurrent_duration', 15)
            )
            concurrent_results.append(asdict(concurrent_result))
            
        except Exception as e:
            errors.append(f"Concurrent WebSocket testing failed: {e}")
        
        duration = time.time() - start_time
        passed_tests = sum(1 for result in concurrent_results if result['passed'])
        
        return TestSuiteResult(
            name="Concurrent WebSocket Tests",
            passed=len(errors) == 0 and len(concurrent_results) > 0,
            duration=duration,
            total_tests=len(concurrent_results),
            passed_tests=passed_tests,
            failed_tests=len(concurrent_results) - passed_tests,
            details=concurrent_results,
            errors=errors,
            timestamp=datetime.now().isoformat()
        )
    
    def run_integration_tests(self, test_file: str = None) -> TestSuiteResult:
        """Run end-to-end integration tests"""
        start_time = time.time()
        integration_results = []
        errors = []
        
        print("🔄 Running Integration Tests...")
        
        try:
            if test_file and Path(test_file).exists():
                # Full pipeline test
                pipeline_results = self.api_tester.full_pipeline_test(test_file)
                for result in pipeline_results:
                    integration_results.append(asdict(result))
            else:
                errors.append("No test file provided for integration testing")
        
        except Exception as e:
            errors.append(f"Integration testing failed: {e}")
        
        duration = time.time() - start_time
        passed_tests = sum(1 for result in integration_results if result['passed'])
        
        return TestSuiteResult(
            name="Integration Tests",
            passed=len(errors) == 0 and len(integration_results) > 0,
            duration=duration,
            total_tests=len(integration_results),
            passed_tests=passed_tests,
            failed_tests=len(integration_results) - passed_tests,
            details=integration_results,
            errors=errors,
            timestamp=datetime.now().isoformat()
        )
    
    async def run_full_test_suite(self, test_file: str = None) -> List[TestSuiteResult]:
        """Run complete test suite"""
        print("🚀 Starting Full Test Suite...")
        print("=" * 60)
        
        all_results = []
        
        # 1. System Health Check
        health_result = self.check_system_health()
        all_results.append(health_result)
        self.print_suite_result(health_result)
        
        if not health_result.passed:
            print("\n❌ System health check failed. Aborting remaining tests.")
            return all_results
        
        # 2. API Tests
        api_result = self.run_api_tests(test_file)
        all_results.append(api_result)
        self.print_suite_result(api_result)
        
        # 3. WebSocket Tests
        receipt_id = None
        if api_result.details and len(api_result.details) > 2:
            # Try to extract receipt_id from upload test
            for detail in api_result.details:
                if detail.get('name') == 'Receipt Upload' and detail.get('data', {}).get('receipt_id'):
                    receipt_id = detail['data']['receipt_id']
                    break
        
        ws_result = await self.run_websocket_tests(receipt_id)
        all_results.append(ws_result)
        self.print_suite_result(ws_result)
        
        # 4. Performance Tests (if configured)
        if self.config.get('include_performance', True):
            perf_result = self.run_performance_tests(test_file)
            all_results.append(perf_result)
            self.print_suite_result(perf_result)
        
        # 5. Concurrent WebSocket Tests
        if self.config.get('include_concurrent', True):
            concurrent_result = await self.run_concurrent_websocket_tests()
            all_results.append(concurrent_result)
            self.print_suite_result(concurrent_result)
        
        # 6. Integration Tests
        integration_result = self.run_integration_tests(test_file)
        all_results.append(integration_result)
        self.print_suite_result(integration_result)
        
        return all_results
    
    def print_suite_result(self, result: TestSuiteResult):
        """Print formatted test suite result"""
        status = "✅" if result.passed else "❌"
        print(f"\n{status} {result.name}")
        print(f"   Tests: {result.passed_tests}/{result.total_tests} passed")
        print(f"   Duration: {result.duration:.2f}s")
        
        if result.errors:
            print("   Errors:")
            for error in result.errors:
                print(f"     - {error}")
    
    def print_final_summary(self, results: List[TestSuiteResult]):
        """Print comprehensive test summary"""
        total_duration = time.time() - self.start_time
        total_tests = sum(r.total_tests for r in results)
        total_passed = sum(r.passed_tests for r in results)
        total_failed = total_tests - total_passed
        
        suite_success_rate = sum(1 for r in results if r.passed) / len(results) * 100
        test_success_rate = total_passed / total_tests * 100 if total_tests > 0 else 0
        
        print("\n" + "=" * 80)
        print("🏁 FINAL TEST SUMMARY")
        print("=" * 80)
        print(f"Total Test Suites: {len(results)}")
        print(f"Suite Success Rate: {suite_success_rate:.1f}%")
        print(f"Total Individual Tests: {total_tests}")
        print(f"Test Success Rate: {test_success_rate:.1f}%")
        print(f"Total Duration: {total_duration:.2f}s")
        
        print("\nSuite Breakdown:")
        for result in results:
            status = "✅" if result.passed else "❌"
            print(f"  {status} {result.name}: {result.passed_tests}/{result.total_tests} ({result.passed_tests/result.total_tests*100:.1f}%)")
        
        # Performance insights
        performance_results = [r for r in results if r.name == "Performance Tests"]
        if performance_results and performance_results[0].details:
            perf_data = performance_results[0].details[0].get('data', {})
            if 'throughput_per_second' in perf_data:
                print(f"\nPerformance Metrics:")
                print(f"  Throughput: {perf_data['throughput_per_second']:.1f} receipts/second")
                print(f"  Avg Upload Time: {perf_data['avg_upload_time']:.2f}s")
        
        # WebSocket metrics
        ws_results = [r for r in results if r.name == "WebSocket Tests"]
        if ws_results and ws_results[0].details:
            for detail in ws_results[0].details:
                if 'avg_latency_ms' in detail.get('data', {}):
                    print(f"\nWebSocket Metrics:")
                    print(f"  Average Latency: {detail['data']['avg_latency_ms']:.1f}ms")
                    break
        
        print("=" * 80)
        
        # Final verdict
        overall_success = suite_success_rate >= 80 and test_success_rate >= 85
        verdict = "🎉 PASS" if overall_success else "💥 FAIL"
        print(f"\nOVERALL RESULT: {verdict}")
        print("=" * 80)
    
    def save_report(self, results: List[TestSuiteResult], output_file: str):
        """Save detailed test report to JSON file"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_duration': time.time() - self.start_time,
            'config': self.config,
            'summary': {
                'total_suites': len(results),
                'passed_suites': sum(1 for r in results if r.passed),
                'total_tests': sum(r.total_tests for r in results),
                'passed_tests': sum(r.passed_tests for r in results),
                'suite_success_rate': sum(1 for r in results if r.passed) / len(results) * 100,
                'test_success_rate': sum(r.passed_tests for r in results) / sum(r.total_tests for r in results) * 100 if sum(r.total_tests for r in results) > 0 else 0
            },
            'results': [asdict(result) for result in results]
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\n📄 Detailed report saved to: {output_file}")

async def main():
    parser = argparse.ArgumentParser(description="Master Test Runner for Receipt Processing System")
    
    # Configuration
    parser.add_argument("--config", help="Configuration file (JSON)")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--ws-url", default="ws://localhost:8000", help="WebSocket base URL")
    parser.add_argument("--token", help="Authentication token")
    parser.add_argument("--test-file", help="Receipt file for testing")
    
    # Test selection
    parser.add_argument("--quick", action="store_true", help="Run quick test suite (excludes performance tests)")
    parser.add_argument("--full", action="store_true", help="Run full comprehensive test suite")
    parser.add_argument("--health-only", action="store_true", help="Run only system health checks")
    parser.add_argument("--api-only", action="store_true", help="Run only API tests")
    parser.add_argument("--ws-only", action="store_true", help="Run only WebSocket tests")
    parser.add_argument("--performance", action="store_true", help="Include performance tests")
    
    # Performance parameters
    parser.add_argument("--perf-receipts", type=int, default=10, help="Number of receipts for performance test")
    parser.add_argument("--perf-workers", type=int, default=3, help="Concurrent workers for performance test")
    parser.add_argument("--concurrent-connections", type=int, default=5, help="Concurrent WebSocket connections")
    parser.add_argument("--concurrent-duration", type=int, default=15, help="Concurrent test duration")
    
    # Output
    parser.add_argument("--output-report", help="Save detailed report to JSON file")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Load configuration
    config = {
        'api_base_url': args.api_url,
        'ws_base_url': args.ws_url,
        'token': args.token,
        'perf_receipts': args.perf_receipts,
        'perf_workers': args.perf_workers,
        'concurrent_connections': args.concurrent_connections,
        'concurrent_duration': args.concurrent_duration,
        'include_performance': args.performance or args.full,
        'include_concurrent': not args.quick,
        'verbose': args.verbose
    }
    
    if args.config and Path(args.config).exists():
        with open(args.config) as f:
            file_config = json.load(f)
            config.update(file_config)
    
    # Create test runner
    runner = MasterTestRunner(config)
    
    # Determine test file
    test_file = args.test_file
    if not test_file:
        # Look for default test files
        possible_files = [
            'tests/test_receipts/good_quality.jpg',
            'test_receipt.jpg',
            'receipt.jpg'
        ]
        for file_path in possible_files:
            if Path(file_path).exists():
                test_file = file_path
                break
    
    if test_file and not Path(test_file).exists():
        print(f"⚠️  Test file not found: {test_file}")
        print("   Some tests will be skipped.")
        test_file = None
    
    results = []
    
    # Run selected tests
    if args.health_only:
        results.append(runner.check_system_health())
        runner.print_suite_result(results[0])
    elif args.api_only:
        results.append(runner.run_api_tests(test_file))
        runner.print_suite_result(results[0])
    elif args.ws_only:
        ws_result = await runner.run_websocket_tests()
        results.append(ws_result)
        runner.print_suite_result(results[0])
    else:
        # Run full or quick suite
        results = await runner.run_full_test_suite(test_file)
    
    # Print final summary
    if len(results) > 1:
        runner.print_final_summary(results)
    
    # Save report if requested
    if args.output_report:
        runner.save_report(results, args.output_report)
    
    # Return exit code
    overall_success = all(r.passed for r in results)
    return 0 if overall_success else 1

if __name__ == "__main__":
    exit(asyncio.run(main()))