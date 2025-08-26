#!/usr/bin/env python3
"""
API Testing Suite for Receipt Processing System

This script provides comprehensive API testing functionality including:
- Authentication testing
- Receipt upload and processing
- Status monitoring
- Error scenario validation
- Performance benchmarking
- Batch processing tests

Usage:
    python api_testing_guide.py --help
    python api_testing_guide.py --test-all
    python api_testing_guide.py --test-upload --file test_receipt.jpg
    python api_testing_guide.py --performance --receipts 20 --concurrent 5
"""

import requests
import time
import json
import argparse
import statistics
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import sys
import os

# Add the Django project to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

@dataclass
class TestResult:
    """Test result container"""
    name: str
    passed: bool
    duration: float
    message: str
    data: Optional[Dict] = None

class APITester:
    """Main API testing class"""
    
    def __init__(self, base_url: str = "http://localhost:8000", token: str = None):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.session = requests.Session()
        
        # Set default headers for API versioning
        self.session.headers.update({
            'Accept': 'application/json; version=v1',
            'User-Agent': 'APITester/1.0'
        })
        
        if token:
            self.session.headers.update({'Authorization': f'Token {token}'})
    
    def authenticate(self, username: str, password: str) -> bool:
        """Authenticate and get access token"""
        try:
            response = self.session.post(f'{self.base_url}/api/auth/login/', {
                'username': username,
                'password': password
            })
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('access_token')
                self.session.headers.update({'Authorization': f'Bearer {self.token}'})
                print(f"✓ Authentication successful for user: {username}")
                return True
            else:
                print(f"✗ Authentication failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ Authentication error: {e}")
            return False
    
    def test_health_check(self) -> TestResult:
        """Test system health endpoint"""
        start_time = time.time()
        
        try:
            response = self.session.get(f'{self.base_url}/health/')
            duration = time.time() - start_time
            
            if response.status_code == 200:
                return TestResult(
                    name="Health Check",
                    passed=True,
                    duration=duration,
                    message="System is healthy",
                    data=response.json() if response.content else {}
                )
            else:
                return TestResult(
                    name="Health Check",
                    passed=False,
                    duration=duration,
                    message=f"Health check failed with status {response.status_code}"
                )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                name="Health Check",
                passed=False,
                duration=duration,
                message=f"Health check error: {e}"
            )
    
    def test_receipt_upload(self, file_path: str) -> TestResult:
        """Test receipt file upload"""
        start_time = time.time()
        
        try:
            if not Path(file_path).exists():
                return TestResult(
                    name="Receipt Upload",
                    passed=False,
                    duration=0,
                    message=f"File not found: {file_path}"
                )
            
            with open(file_path, 'rb') as f:
                files = {'receipt_file': (file_path, f, 'image/jpeg')}
                response = self.session.post(
                    f'{self.base_url}/api/receipts/upload/',
                    files=files
                )
            
            duration = time.time() - start_time
            
            if response.status_code == 201:
                data = response.json()
                return TestResult(
                    name="Receipt Upload",
                    passed=True,
                    duration=duration,
                    message=f"Upload successful, receipt ID: {data.get('receipt_id')}",
                    data=data
                )
            else:
                return TestResult(
                    name="Receipt Upload",
                    passed=False,
                    duration=duration,
                    message=f"Upload failed with status {response.status_code}: {response.text}"
                )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                name="Receipt Upload",
                passed=False,
                duration=duration,
                message=f"Upload error: {e}"
            )
    
    def test_receipt_status(self, receipt_id: int) -> TestResult:
        """Test receipt status monitoring"""
        start_time = time.time()
        
        try:
            response = self.session.get(f'{self.base_url}/api/receipts/{receipt_id}/status/')
            duration = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                return TestResult(
                    name="Receipt Status",
                    passed=True,
                    duration=duration,
                    message=f"Status: {data.get('status')} - {data.get('processing_step')}",
                    data=data
                )
            else:
                return TestResult(
                    name="Receipt Status",
                    passed=False,
                    duration=duration,
                    message=f"Status check failed with code {response.status_code}"
                )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                name="Receipt Status",
                passed=False,
                duration=duration,
                message=f"Status check error: {e}"
            )
    
    def monitor_receipt_processing(self, receipt_id: int, timeout: int = 300) -> TestResult:
        """Monitor receipt processing until completion"""
        start_time = time.time()
        final_status = None
        steps_seen = []
        
        try:
            while (time.time() - start_time) < timeout:
                response = self.session.get(f'{self.base_url}/api/receipts/{receipt_id}/status/')
                
                if response.status_code != 200:
                    return TestResult(
                        name="Receipt Processing",
                        passed=False,
                        duration=time.time() - start_time,
                        message=f"Status check failed: {response.status_code}"
                    )
                
                data = response.json()
                status = data.get('status')
                step = data.get('processing_step')
                
                if step not in steps_seen:
                    steps_seen.append(step)
                    print(f"  Processing step: {step}")
                
                if status in ['review_pending', 'completed', 'error']:
                    final_status = status
                    break
                
                time.sleep(2)
            
            duration = time.time() - start_time
            
            if final_status in ['review_pending', 'completed']:
                return TestResult(
                    name="Receipt Processing",
                    passed=True,
                    duration=duration,
                    message=f"Processing completed with status: {final_status}",
                    data={'final_status': final_status, 'steps': steps_seen}
                )
            elif final_status == 'error':
                return TestResult(
                    name="Receipt Processing",
                    passed=False,
                    duration=duration,
                    message="Processing failed with error status",
                    data={'final_status': final_status, 'steps': steps_seen}
                )
            else:
                return TestResult(
                    name="Receipt Processing",
                    passed=False,
                    duration=duration,
                    message=f"Processing timeout after {timeout}s"
                )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                name="Receipt Processing",
                passed=False,
                duration=duration,
                message=f"Processing monitoring error: {e}"
            )
    
    def test_receipt_details(self, receipt_id: int) -> TestResult:
        """Test receipt details retrieval"""
        start_time = time.time()
        
        try:
            response = self.session.get(f'{self.base_url}/api/receipts/{receipt_id}/')
            duration = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                line_items_count = len(data.get('line_items', []))
                
                return TestResult(
                    name="Receipt Details",
                    passed=True,
                    duration=duration,
                    message=f"Retrieved receipt with {line_items_count} line items",
                    data=data
                )
            else:
                return TestResult(
                    name="Receipt Details",
                    passed=False,
                    duration=duration,
                    message=f"Details retrieval failed: {response.status_code}"
                )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                name="Receipt Details",
                passed=False,
                duration=duration,
                message=f"Details retrieval error: {e}"
            )
    
    def test_receipt_confirmation(self, receipt_id: int) -> TestResult:
        """Test receipt confirmation"""
        start_time = time.time()
        
        try:
            # First get receipt details
            details_response = self.session.get(f'{self.base_url}/api/receipts/{receipt_id}/')
            
            if details_response.status_code != 200:
                return TestResult(
                    name="Receipt Confirmation",
                    passed=False,
                    duration=time.time() - start_time,
                    message="Cannot get receipt details for confirmation"
                )
            
            receipt_data = details_response.json()
            
            # Prepare confirmation data
            confirmation_data = {
                'confirmed_data': {
                    'store_name': receipt_data.get('store_name', 'Test Store'),
                    'total': str(receipt_data.get('total', '0.00')),
                    'line_items': [
                        {
                            'product_name': item.get('product_name', 'Unknown'),
                            'quantity': float(item.get('quantity', 1.0)),
                            'unit_price': float(item.get('unit_price', 0.0)),
                            'unit_discount': float(item.get('unit_discount', 0.0))
                        }
                        for item in receipt_data.get('line_items', [])
                    ]
                }
            }
            
            # Confirm receipt
            response = self.session.patch(
                f'{self.base_url}/api/receipts/{receipt_id}/confirm/',
                json=confirmation_data
            )
            
            duration = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                return TestResult(
                    name="Receipt Confirmation",
                    passed=True,
                    duration=duration,
                    message=f"Receipt confirmed successfully: {data.get('message')}",
                    data=data
                )
            else:
                return TestResult(
                    name="Receipt Confirmation",
                    passed=False,
                    duration=duration,
                    message=f"Confirmation failed: {response.status_code} - {response.text}"
                )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                name="Receipt Confirmation",
                passed=False,
                duration=duration,
                message=f"Confirmation error: {e}"
            )
    
    def test_statistics(self) -> TestResult:
        """Test statistics endpoint"""
        start_time = time.time()
        
        try:
            response = self.session.get(f'{self.base_url}/api/receipts/stats/')
            duration = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                return TestResult(
                    name="Statistics",
                    passed=True,
                    duration=duration,
                    message=f"Stats: {data.get('success_rate', 0):.1f}% success rate",
                    data=data
                )
            else:
                return TestResult(
                    name="Statistics",
                    passed=False,
                    duration=duration,
                    message=f"Statistics failed: {response.status_code}"
                )
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                name="Statistics",
                passed=False,
                duration=duration,
                message=f"Statistics error: {e}"
            )
    
    def test_error_scenarios(self) -> List[TestResult]:
        """Test various error scenarios"""
        results = []
        
        # Test 1: Invalid file format
        start_time = time.time()
        try:
            # Create a fake text file
            fake_file_content = "This is not an image file"
            files = {'receipt_file': ('test.txt', fake_file_content, 'text/plain')}
            response = self.session.post(f'{self.base_url}/api/receipts/upload/', files=files)
            
            duration = time.time() - start_time
            
            if response.status_code == 400:
                results.append(TestResult(
                    name="Invalid File Format",
                    passed=True,
                    duration=duration,
                    message="Correctly rejected invalid file format"
                ))
            else:
                results.append(TestResult(
                    name="Invalid File Format",
                    passed=False,
                    duration=duration,
                    message=f"Should have rejected invalid file, got: {response.status_code}"
                ))
        except Exception as e:
            results.append(TestResult(
                name="Invalid File Format",
                passed=False,
                duration=time.time() - start_time,
                message=f"Error testing invalid file: {e}"
            ))
        
        # Test 2: Non-existent receipt status
        start_time = time.time()
        try:
            response = self.session.get(f'{self.base_url}/api/receipts/99999/status/')
            duration = time.time() - start_time
            
            if response.status_code == 404:
                results.append(TestResult(
                    name="Non-existent Receipt",
                    passed=True,
                    duration=duration,
                    message="Correctly returned 404 for non-existent receipt"
                ))
            else:
                results.append(TestResult(
                    name="Non-existent Receipt",
                    passed=False,
                    duration=duration,
                    message=f"Should have returned 404, got: {response.status_code}"
                ))
        except Exception as e:
            results.append(TestResult(
                name="Non-existent Receipt",
                passed=False,
                duration=time.time() - start_time,
                message=f"Error testing non-existent receipt: {e}"
            ))
        
        # Test 3: Unauthorized access
        start_time = time.time()
        try:
            # Create session without auth
            unauth_session = requests.Session()
            response = unauth_session.get(f'{self.base_url}/api/receipts/stats/')
            duration = time.time() - start_time
            
            if response.status_code in [401, 403]:
                results.append(TestResult(
                    name="Unauthorized Access",
                    passed=True,
                    duration=duration,
                    message="Correctly rejected unauthorized access"
                ))
            else:
                results.append(TestResult(
                    name="Unauthorized Access",
                    passed=False,
                    duration=duration,
                    message=f"Should have rejected unauthorized access, got: {response.status_code}"
                ))
        except Exception as e:
            results.append(TestResult(
                name="Unauthorized Access",
                passed=False,
                duration=time.time() - start_time,
                message=f"Error testing unauthorized access: {e}"
            ))
        
        return results
    
    def performance_test(self, receipt_file: str, num_receipts: int = 10, max_workers: int = 3) -> TestResult:
        """Run performance test with multiple receipts"""
        if not Path(receipt_file).exists():
            return TestResult(
                name="Performance Test",
                passed=False,
                duration=0,
                message=f"Test file not found: {receipt_file}"
            )
        
        def upload_single_receipt():
            """Upload single receipt and measure time"""
            start_time = time.time()
            
            try:
                with open(receipt_file, 'rb') as f:
                    files = {'receipt_file': f}
                    response = self.session.post(f'{self.base_url}/api/receipts/upload/', files=files)
                
                if response.status_code == 201:
                    return {
                        'success': True,
                        'duration': time.time() - start_time,
                        'receipt_id': response.json().get('receipt_id')
                    }
                else:
                    return {
                        'success': False,
                        'duration': time.time() - start_time,
                        'error': f"HTTP {response.status_code}"
                    }
            except Exception as e:
                return {
                    'success': False,
                    'duration': time.time() - start_time,
                    'error': str(e)
                }
        
        start_time = time.time()
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(upload_single_receipt) for _ in range(num_receipts)]
                results = [future.result() for future in concurrent.futures.as_completed(futures)]
            
            total_duration = time.time() - start_time
            
            # Analyze results
            successful_uploads = [r for r in results if r['success']]
            failed_uploads = [r for r in results if not r['success']]
            
            upload_times = [r['duration'] for r in successful_uploads]
            
            success_rate = len(successful_uploads) / len(results) * 100
            avg_upload_time = statistics.mean(upload_times) if upload_times else 0
            
            return TestResult(
                name="Performance Test",
                passed=success_rate >= 80,  # 80% success rate threshold
                duration=total_duration,
                message=f"Uploaded {len(successful_uploads)}/{num_receipts} receipts ({success_rate:.1f}% success)",
                data={
                    'total_receipts': num_receipts,
                    'successful_uploads': len(successful_uploads),
                    'failed_uploads': len(failed_uploads),
                    'success_rate': success_rate,
                    'avg_upload_time': avg_upload_time,
                    'total_time': total_duration,
                    'throughput_per_second': num_receipts / total_duration
                }
            )
        except Exception as e:
            return TestResult(
                name="Performance Test",
                passed=False,
                duration=time.time() - start_time,
                message=f"Performance test error: {e}"
            )
    
    def full_pipeline_test(self, receipt_file: str) -> List[TestResult]:
        """Run complete pipeline test"""
        results = []
        receipt_id = None
        
        print("Running Full Pipeline Test...")
        
        # Step 1: Upload
        print("1. Testing upload...")
        upload_result = self.test_receipt_upload(receipt_file)
        results.append(upload_result)
        
        if upload_result.passed:
            receipt_id = upload_result.data.get('receipt_id')
            print(f"   Receipt ID: {receipt_id}")
        else:
            print("   Upload failed, stopping pipeline test")
            return results
        
        # Step 2: Monitor processing
        print("2. Monitoring processing...")
        processing_result = self.monitor_receipt_processing(receipt_id)
        results.append(processing_result)
        
        if not processing_result.passed:
            print("   Processing failed, stopping pipeline test")
            return results
        
        # Step 3: Get details
        print("3. Getting receipt details...")
        details_result = self.test_receipt_details(receipt_id)
        results.append(details_result)
        
        # Step 4: Confirm receipt (only if in review_pending)
        if processing_result.data.get('final_status') == 'review_pending':
            print("4. Confirming receipt...")
            confirm_result = self.test_receipt_confirmation(receipt_id)
            results.append(confirm_result)
        
        return results

def print_test_result(result: TestResult):
    """Print formatted test result"""
    status = "✓" if result.passed else "✗"
    print(f"{status} {result.name}: {result.message} ({result.duration:.2f}s)")

def print_summary(results: List[TestResult]):
    """Print test results summary"""
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.passed)
    total_time = sum(r.duration for r in results)
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {passed_tests/total_tests*100:.1f}%")
    print(f"Total Time: {total_time:.2f}s")
    print("="*60)

def main():
    parser = argparse.ArgumentParser(description="API Testing Suite for Receipt Processing")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base API URL")
    parser.add_argument("--token", help="Authentication token")
    parser.add_argument("--username", help="Username for authentication")
    parser.add_argument("--password", help="Password for authentication")
    
    # Test selection
    parser.add_argument("--test-all", action="store_true", help="Run all tests")
    parser.add_argument("--test-upload", action="store_true", help="Test receipt upload")
    parser.add_argument("--test-pipeline", action="store_true", help="Test full pipeline")
    parser.add_argument("--test-errors", action="store_true", help="Test error scenarios")
    parser.add_argument("--test-performance", action="store_true", help="Test performance")
    parser.add_argument("--test-stats", action="store_true", help="Test statistics")
    
    # Parameters
    parser.add_argument("--file", default="tests/test_receipts/good_quality.jpg", help="Receipt file path")
    parser.add_argument("--receipts", type=int, default=10, help="Number of receipts for performance test")
    parser.add_argument("--concurrent", type=int, default=3, help="Concurrent uploads for performance test")
    
    args = parser.parse_args()
    
    # Create tester instance
    tester = APITester(base_url=args.base_url, token=args.token)
    
    # Authenticate if credentials provided
    if args.username and args.password:
        if not tester.authenticate(args.username, args.password):
            print("Authentication failed, exiting")
            return 1
    
    results = []
    
    # Health check first
    print("Performing health check...")
    health_result = tester.test_health_check()
    print_test_result(health_result)
    results.append(health_result)
    
    if not health_result.passed:
        print("System is not healthy, aborting tests")
        return 1
    
    # Run requested tests
    if args.test_all or args.test_upload:
        print("\nTesting receipt upload...")
        upload_result = tester.test_receipt_upload(args.file)
        print_test_result(upload_result)
        results.append(upload_result)
    
    if args.test_all or args.test_pipeline:
        print("\nRunning full pipeline test...")
        pipeline_results = tester.full_pipeline_test(args.file)
        for result in pipeline_results:
            print_test_result(result)
        results.extend(pipeline_results)
    
    if args.test_all or args.test_errors:
        print("\nTesting error scenarios...")
        error_results = tester.test_error_scenarios()
        for result in error_results:
            print_test_result(result)
        results.extend(error_results)
    
    if args.test_all or args.test_performance:
        print(f"\nRunning performance test ({args.receipts} receipts, {args.concurrent} concurrent)...")
        perf_result = tester.performance_test(args.file, args.receipts, args.concurrent)
        print_test_result(perf_result)
        if perf_result.data:
            print(f"   Throughput: {perf_result.data['throughput_per_second']:.1f} receipts/second")
            print(f"   Average upload time: {perf_result.data['avg_upload_time']:.2f}s")
        results.append(perf_result)
    
    if args.test_all or args.test_stats:
        print("\nTesting statistics...")
        stats_result = tester.test_statistics()
        print_test_result(stats_result)
        if stats_result.data:
            print(f"   Success rate: {stats_result.data.get('success_rate', 0):.1f}%")
            print(f"   Average processing time: {stats_result.data.get('avg_processing_time', 0):.1f} minutes")
        results.append(stats_result)
    
    # Print summary
    print_summary(results)
    
    # Return exit code based on results
    return 0 if all(r.passed for r in results) else 1

if __name__ == "__main__":
    exit(main())