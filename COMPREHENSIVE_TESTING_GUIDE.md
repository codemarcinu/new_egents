# Comprehensive Testing Guide - Receipt Processing System

This guide provides complete testing procedures for the receipt processing pipeline, covering API endpoints, WebSocket connections, error scenarios, and performance validation.

## Table of Contents

1. [Environment Setup](#environment-setup)
2. [API Testing](#api-testing)
3. [WebSocket Testing](#websocket-testing)
4. [Pipeline Testing](#pipeline-testing)
5. [Service Component Testing](#service-component-testing)
6. [Error Handling Testing](#error-handling-testing)
7. [Performance Testing](#performance-testing)
8. [Diagnostic Tools](#diagnostic-tools)
9. [Success Criteria](#success-criteria)

## Environment Setup

### Prerequisites

```bash
# Clone repository
git clone https://github.com/codemarcinu/new_egents.git
cd agent_chat_app

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements/local_sqlite.txt

# Database setup
python manage.py migrate
python manage.py createsuperuser

# Start Redis (required for Celery)
redis-server --port 6379

# Start Celery worker
celery -A config.celery_app worker --loglevel=info --detach

# Start Django with ASGI (WebSocket support)
daphne -p 8000 config.asgi:application
```

### Ollama Models Setup

```bash
# Install required models
ollama pull gemma2:2b
ollama pull gemma3:4b
ollama pull mxbai-embed-large
```

### Test Data Preparation

Create test receipt images in various formats and qualities:
- `tests/test_receipts/good_quality.jpg` - Clear, high-resolution receipt
- `tests/test_receipts/poor_quality.jpg` - Low quality, blurry receipt
- `tests/test_receipts/foreign_language.jpg` - Receipt in non-English language
- `tests/test_receipts/corrupted.jpg` - Corrupted image file
- `tests/test_receipts/empty_receipt.jpg` - Empty or white image

## API Testing

### Core Endpoints

#### 1. Receipt Upload
```bash
# Test successful upload
curl -X POST http://localhost:8000/api/receipts/upload/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "receipt_file=@tests/test_receipts/good_quality.jpg"

# Expected Response:
{
  "receipt_id": 1,
  "task_id": "abc123-def456",
  "status": "uploaded",
  "message": "Receipt uploaded successfully, processing started"
}
```

#### 2. Receipt Status Monitoring
```bash
# Monitor processing status
curl -X GET http://localhost:8000/api/receipts/1/status/ \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expected Response Sequence:
# Status 1: {"status": "processing", "processing_step": "ocr_in_progress"}
# Status 2: {"status": "processing", "processing_step": "parsing_in_progress"}
# Status 3: {"status": "processing", "processing_step": "matching_in_progress"}
# Status 4: {"status": "review_pending", "processing_step": "review_pending"}
```

#### 3. Receipt Details
```bash
# Get detailed receipt information
curl -X GET http://localhost:8000/api/receipts/1/ \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expected Response includes:
{
  "id": 1,
  "store_name": "Example Store",
  "total": "45.67",
  "line_items": [
    {
      "product_name": "Milk",
      "quantity": "2.00",
      "unit_price": "3.50",
      "line_total": "7.00",
      "matched_product": {...},
      "match_confidence": 0.95
    }
  ]
}
```

#### 4. Receipt Confirmation
```bash
# Confirm receipt with user edits
curl -X PATCH http://localhost:8000/api/receipts/1/confirm/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "confirmed_data": {
      "store_name": "Corrected Store Name",
      "total": "45.67",
      "line_items": [
        {
          "product_name": "Milk 2%",
          "quantity": 2,
          "unit_price": 3.50,
          "unit_discount": 0.00
        }
      ]
    }
  }'
```

#### 5. Statistics
```bash
# Get processing statistics
curl -X GET http://localhost:8000/api/receipts/stats/ \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expected Response:
{
  "total_receipts": 10,
  "processed_receipts": 8,
  "pending_receipts": 1,
  "failed_receipts": 1,
  "success_rate": 80.0,
  "avg_processing_time": 1.25
}
```

### Error Scenario Testing

```bash
# Test file format validation
curl -X POST http://localhost:8000/api/receipts/upload/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "receipt_file=@tests/invalid.txt"
# Expected: 400 Bad Request

# Test file size limits
curl -X POST http://localhost:8000/api/receipts/upload/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "receipt_file=@tests/huge_file.jpg"
# Expected: 400 Bad Request

# Test corrupted file
curl -X POST http://localhost:8000/api/receipts/upload/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "receipt_file=@tests/corrupted.jpg"
# Expected: Processing will fail at OCR stage
```

## WebSocket Testing

### Connection Testing

```python
# Python WebSocket client for testing
import asyncio
import websockets
import json

async def test_receipt_websocket():
    uri = "ws://localhost:8000/ws/receipt/1/"
    headers = {"Authorization": "Bearer YOUR_TOKEN"}
    
    async with websockets.connect(uri, extra_headers=headers) as websocket:
        # Listen for status updates
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Status Update: {data}")
            
            if data.get('status') == 'completed':
                break

# Run the test
asyncio.run(test_receipt_websocket())
```

### WebSocket Endpoints

1. **Receipt Progress**: `/ws/receipt/<receipt_id>/`
   - Real-time processing status updates
   - Progress percentage tracking
   - Error notifications

2. **Inventory Notifications**: `/ws/inventory/`
   - Low stock alerts
   - Inventory updates

3. **General Notifications**: `/ws/notifications/`
   - System-wide notifications
   - Processing completions

### Expected WebSocket Events

```json
// Receipt processing events
{
  "type": "status_update",
  "receipt_id": 1,
  "status": "processing",
  "processing_step": "ocr_in_progress",
  "progress_percentage": 25.0,
  "message": "Extracting text from receipt image..."
}

// Inventory alert
{
  "type": "low_stock_alert",
  "product_name": "Milk",
  "current_quantity": 3,
  "threshold": 10,
  "message": "Low stock alert: Milk has only 3 items left"
}
```

## Pipeline Testing

### Happy Path Testing

```python
import requests
import time

def test_full_pipeline():
    """Test complete receipt processing pipeline"""
    
    # 1. Upload receipt
    with open('tests/test_receipts/good_quality.jpg', 'rb') as f:
        response = requests.post(
            'http://localhost:8000/api/receipts/upload/',
            files={'receipt_file': f},
            headers={'Authorization': 'Bearer YOUR_TOKEN'}
        )
    
    receipt_id = response.json()['receipt_id']
    print(f"Receipt uploaded: {receipt_id}")
    
    # 2. Monitor processing
    while True:
        status_response = requests.get(
            f'http://localhost:8000/api/receipts/{receipt_id}/status/',
            headers={'Authorization': 'Bearer YOUR_TOKEN'}
        )
        
        status_data = status_response.json()
        print(f"Status: {status_data['processing_step']}")
        
        if status_data['status'] == 'review_pending':
            break
        elif status_data['status'] == 'error':
            print(f"Processing failed: {status_data.get('error_message')}")
            return
            
        time.sleep(5)
    
    # 3. Get detailed results
    detail_response = requests.get(
        f'http://localhost:8000/api/receipts/{receipt_id}/',
        headers={'Authorization': 'Bearer YOUR_TOKEN'}
    )
    
    receipt_data = detail_response.json()
    print(f"Found {len(receipt_data['line_items'])} products")
    
    # 4. Confirm receipt
    confirm_response = requests.patch(
        f'http://localhost:8000/api/receipts/{receipt_id}/confirm/',
        json={'confirmed_data': receipt_data},
        headers={'Authorization': 'Bearer YOUR_TOKEN'}
    )
    
    print("Receipt confirmed successfully")
    return receipt_id

# Run the test
test_full_pipeline()
```

### Batch Processing Test

```python
import concurrent.futures
import requests

def upload_multiple_receipts(num_receipts=10):
    """Test concurrent receipt processing"""
    
    def upload_single(receipt_path):
        with open(receipt_path, 'rb') as f:
            response = requests.post(
                'http://localhost:8000/api/receipts/upload/',
                files={'receipt_file': f},
                headers={'Authorization': 'Bearer YOUR_TOKEN'}
            )
        return response.json()['receipt_id']
    
    # Upload receipts concurrently
    receipt_files = [f'tests/test_receipts/receipt_{i}.jpg' for i in range(num_receipts)]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        receipt_ids = list(executor.map(upload_single, receipt_files))
    
    print(f"Uploaded {len(receipt_ids)} receipts")
    
    # Monitor completion
    completed = 0
    while completed < len(receipt_ids):
        for receipt_id in receipt_ids:
            status_response = requests.get(
                f'http://localhost:8000/api/receipts/{receipt_id}/status/',
                headers={'Authorization': 'Bearer YOUR_TOKEN'}
            )
            
            if status_response.json()['status'] in ['review_pending', 'completed', 'error']:
                completed += 1
        
        time.sleep(10)
    
    print(f"All {num_receipts} receipts processed")

# Run batch test
upload_multiple_receipts(20)
```

## Service Component Testing

### OCR Service Testing

```python
from agent_chat_app.receipts.services.ocr_service import get_hybrid_ocr_service
import asyncio

async def test_ocr_service():
    """Test OCR service with different image qualities"""
    ocr_service = get_hybrid_ocr_service()
    
    test_images = [
        'tests/test_receipts/good_quality.jpg',
        'tests/test_receipts/poor_quality.jpg',
        'tests/test_receipts/blurry.jpg'
    ]
    
    for image_path in test_images:
        print(f"Testing OCR on {image_path}")
        
        extracted_text = await ocr_service.extract_text_from_file(image_path)
        print(f"Extracted text length: {len(extracted_text)}")
        print(f"Sample text: {extracted_text[:200]}...")
        
        # Validate text quality
        if len(extracted_text) < 50:
            print("Warning: Very short extracted text")
        
        print("-" * 50)

asyncio.run(test_ocr_service())
```

### Parser Service Testing

```python
from agent_chat_app.receipts.services.receipt_parser import get_receipt_parser

def test_parser_service():
    """Test receipt parser with sample OCR text"""
    parser = get_receipt_parser()
    
    sample_ocr_text = """
    SUPER MARKET
    123 Main St
    Date: 2024-01-15
    
    Milk 2% Organic    2x  3.50    7.00
    Bread Whole Wheat  1x  2.99    2.99
    Apples Red         3x  1.25    3.75
    
    Subtotal:          13.74
    Tax:                1.37
    Total:             15.11
    """
    
    parsed_data = parser.parse(sample_ocr_text)
    
    print("Parsed Results:")
    print(f"Store: {parsed_data.get('store_name')}")
    print(f"Date: {parsed_data.get('date')}")
    print(f"Total: {parsed_data.get('total')}")
    print(f"Products found: {len(parsed_data.get('products', []))}")
    
    for product in parsed_data.get('products', []):
        print(f"  - {product['name']}: {product['quantity']} x ${product['price']}")

test_parser_service()
```

### Product Matcher Testing

```python
from agent_chat_app.receipts.services.product_matcher import get_product_matcher
from agent_chat_app.receipts.services.receipt_parser import ParsedProduct

def test_product_matcher():
    """Test product matching with various product names"""
    matcher = get_product_matcher()
    
    test_products = [
        ParsedProduct("Milk 2%", 2.0, 3.50, 7.00, "liters"),
        ParsedProduct("Whole Wheat Bread", 1.0, 2.99, 2.99, "loaf"),
        ParsedProduct("Red Apples", 3.0, 1.25, 3.75, "kg"),
        ParsedProduct("Unknown Product XYZ", 1.0, 5.00, 5.00, "pcs")
    ]
    
    match_results = matcher.batch_match_products(test_products)
    
    for product, match_result in zip(test_products, match_results):
        print(f"Product: {product.name}")
        print(f"  Match: {match_result.product.name if match_result.product else 'No match'}")
        print(f"  Confidence: {match_result.confidence:.2f}")
        print(f"  Match Type: {match_result.match_type}")
        print("-" * 30)

test_product_matcher()
```

## Error Handling Testing

### File Validation Errors

```bash
# Test invalid file formats
curl -X POST http://localhost:8000/api/receipts/upload/ \
  -F "receipt_file=@tests/invalid.txt" \
  -H "Authorization: Bearer YOUR_TOKEN"
# Expected: 400 - Invalid file format

# Test oversized files (>10MB)
curl -X POST http://localhost:8000/api/receipts/upload/ \
  -F "receipt_file=@tests/huge_file.jpg" \
  -H "Authorization: Bearer YOUR_TOKEN"
# Expected: 400 - File too large
```

### Processing Failures

```python
def test_processing_failures():
    """Test various processing failure scenarios"""
    
    failure_scenarios = [
        {
            'file': 'tests/test_receipts/empty_image.jpg',
            'expected_failure': 'ocr_failed',
            'description': 'Empty or white image'
        },
        {
            'file': 'tests/test_receipts/corrupted.jpg',
            'expected_failure': 'ocr_failed',
            'description': 'Corrupted image file'
        },
        {
            'file': 'tests/test_receipts/foreign_language.jpg',
            'expected_failure': 'parsing_failed',
            'description': 'Non-English receipt'
        }
    ]
    
    for scenario in failure_scenarios:
        print(f"Testing: {scenario['description']}")
        
        # Upload file
        with open(scenario['file'], 'rb') as f:
            response = requests.post(
                'http://localhost:8000/api/receipts/upload/',
                files={'receipt_file': f},
                headers={'Authorization': 'Bearer YOUR_TOKEN'}
            )
        
        receipt_id = response.json()['receipt_id']
        
        # Wait for processing to complete or fail
        while True:
            status_response = requests.get(
                f'http://localhost:8000/api/receipts/{receipt_id}/status/',
                headers={'Authorization': 'Bearer YOUR_TOKEN'}
            )
            
            status_data = status_response.json()
            
            if status_data['status'] == 'error':
                print(f"✓ Failed as expected: {status_data.get('error_message')}")
                break
            elif status_data['status'] in ['review_pending', 'completed']:
                print(f"✗ Unexpectedly succeeded")
                break
            
            time.sleep(5)
        
        print("-" * 50)

test_processing_failures()
```

## Performance Testing

### Load Testing

```python
import time
import statistics
from concurrent.futures import ThreadPoolExecutor

def performance_test(num_receipts=50, concurrent_uploads=10):
    """Test system performance under load"""
    
    def upload_and_monitor(receipt_path):
        start_time = time.time()
        
        # Upload
        with open(receipt_path, 'rb') as f:
            response = requests.post(
                'http://localhost:8000/api/receipts/upload/',
                files={'receipt_file': f},
                headers={'Authorization': 'Bearer YOUR_TOKEN'}
            )
        
        receipt_id = response.json()['receipt_id']
        
        # Monitor completion
        while True:
            status_response = requests.get(
                f'http://localhost:8000/api/receipts/{receipt_id}/status/',
                headers={'Authorization': 'Bearer YOUR_TOKEN'}
            )
            
            status_data = status_response.json()
            
            if status_data['status'] in ['review_pending', 'completed', 'error']:
                end_time = time.time()
                return {
                    'receipt_id': receipt_id,
                    'processing_time': end_time - start_time,
                    'status': status_data['status'],
                    'success': status_data['status'] != 'error'
                }
            
            time.sleep(2)
    
    # Run performance test
    receipt_files = ['tests/test_receipts/good_quality.jpg'] * num_receipts
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=concurrent_uploads) as executor:
        results = list(executor.map(upload_and_monitor, receipt_files))
    
    total_time = time.time() - start_time
    
    # Analyze results
    processing_times = [r['processing_time'] for r in results]
    success_count = sum(1 for r in results if r['success'])
    
    print(f"Performance Test Results:")
    print(f"Total receipts: {num_receipts}")
    print(f"Successful: {success_count} ({success_count/num_receipts*100:.1f}%)")
    print(f"Total time: {total_time:.2f}s")
    print(f"Avg processing time: {statistics.mean(processing_times):.2f}s")
    print(f"Min processing time: {min(processing_times):.2f}s")
    print(f"Max processing time: {max(processing_times):.2f}s")

# Run performance test
performance_test(num_receipts=20, concurrent_uploads=5)
```

### WebSocket Performance

```python
import asyncio
import websockets
import time

async def websocket_performance_test():
    """Test WebSocket connection performance and latency"""
    
    latencies = []
    
    async def test_connection():
        uri = "ws://localhost:8000/ws/notifications/"
        headers = {"Authorization": "Bearer YOUR_TOKEN"}
        
        async with websockets.connect(uri, extra_headers=headers) as websocket:
            for i in range(100):
                start_time = time.time()
                
                # Send ping
                await websocket.send(json.dumps({
                    "type": "ping",
                    "timestamp": start_time
                }))
                
                # Receive pong
                response = await websocket.recv()
                end_time = time.time()
                
                latency = (end_time - start_time) * 1000  # Convert to ms
                latencies.append(latency)
                
                await asyncio.sleep(0.1)
    
    await test_connection()
    
    print(f"WebSocket Performance:")
    print(f"Average latency: {statistics.mean(latencies):.2f}ms")
    print(f"Min latency: {min(latencies):.2f}ms")
    print(f"Max latency: {max(latencies):.2f}ms")

asyncio.run(websocket_performance_test())
```

## Diagnostic Tools

### System Health Check

```python
def system_health_check():
    """Comprehensive system health check"""
    
    health_status = {
        'django': False,
        'redis': False,
        'celery': False,
        'database': False,
        'ollama': False
    }
    
    # Check Django
    try:
        response = requests.get('http://localhost:8000/health/')
        health_status['django'] = response.status_code == 200
    except:
        pass
    
    # Check Redis
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.ping()
        health_status['redis'] = True
    except:
        pass
    
    # Check Celery
    try:
        from celery import Celery
        app = Celery('test')
        app.config_from_object('config.settings.local')
        inspect = app.control.inspect()
        stats = inspect.stats()
        health_status['celery'] = bool(stats)
    except:
        pass
    
    # Check Database
    try:
        import os
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
        django.setup()
        from django.db import connection
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        health_status['database'] = True
    except:
        pass
    
    # Check Ollama
    try:
        response = requests.get('http://localhost:11434/api/tags')
        health_status['ollama'] = response.status_code == 200
    except:
        pass
    
    print("System Health Check:")
    for service, status in health_status.items():
        status_icon = "✓" if status else "✗"
        print(f"  {status_icon} {service.upper()}: {'OK' if status else 'FAILED'}")
    
    return all(health_status.values())

# Run health check
system_health_check()
```

### Log Monitoring

```bash
# Monitor Django logs
tail -f logs/django.log | grep "receipt"

# Monitor Celery logs
tail -f logs/celery.log

# Monitor Redis
redis-cli monitor | grep "receipt"

# System resource monitoring
htop
# or
top -p $(pgrep -d, -f "celery\|daphne\|redis")
```

### Database Integrity Check

```python
def database_integrity_check():
    """Check database integrity for receipt processing"""
    
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
    django.setup()
    
    from agent_chat_app.receipts.models import Receipt, ReceiptLineItem, Product, InventoryItem
    
    print("Database Integrity Check:")
    
    # Check receipt statuses
    receipts = Receipt.objects.all()
    completed_receipts = receipts.filter(status='completed')
    
    print(f"Total receipts: {receipts.count()}")
    print(f"Completed receipts: {completed_receipts.count()}")
    
    # Check line items for completed receipts
    orphaned_items = 0
    for receipt in completed_receipts:
        if not receipt.line_items.exists():
            orphaned_items += 1
            print(f"Warning: Receipt {receipt.id} completed but has no line items")
    
    # Check inventory consistency
    products_with_inventory = Product.objects.filter(inventory__isnull=False).count()
    inventory_items = InventoryItem.objects.count()
    
    print(f"Products with inventory: {products_with_inventory}")
    print(f"Inventory items: {inventory_items}")
    
    # Check for negative inventory
    negative_inventory = InventoryItem.objects.filter(quantity__lt=0).count()
    if negative_inventory > 0:
        print(f"Warning: {negative_inventory} products have negative inventory")
    
    print("Integrity check completed.")

database_integrity_check()
```

## Success Criteria

### Acceptance Thresholds

- **Success Rate**: ≥ 85% of receipts processed successfully
- **Processing Time**: ≤ 2 minutes average per receipt
- **OCR Accuracy**: ≥ 90% text extraction accuracy on good quality images
- **WebSocket Latency**: ≤ 100ms average response time
- **Load Stability**: System handles 50+ concurrent uploads without crashes
- **Error Recovery**: Failed receipts marked appropriately with clear error messages

### Quality Metrics

```python
def calculate_success_metrics():
    """Calculate and display success metrics"""
    
    response = requests.get(
        'http://localhost:8000/api/receipts/stats/',
        headers={'Authorization': 'Bearer YOUR_TOKEN'}
    )
    
    stats = response.json()
    
    print("Success Metrics:")
    print(f"Success Rate: {stats['success_rate']:.1f}% (Target: ≥85%)")
    print(f"Avg Processing Time: {stats['avg_processing_time']:.1f}min (Target: ≤2min)")
    
    # Color-coded results
    success_rate_status = "✓" if stats['success_rate'] >= 85 else "✗"
    time_status = "✓" if stats['avg_processing_time'] <= 2.0 else "✗"
    
    print(f"\nResults:")
    print(f"{success_rate_status} Success Rate")
    print(f"{time_status} Processing Time")

calculate_success_metrics()
```

### Automated Test Suite

```python
def run_full_test_suite():
    """Run complete automated test suite"""
    
    test_results = {
        'system_health': False,
        'api_functionality': False,
        'websocket_connectivity': False,
        'pipeline_processing': False,
        'error_handling': False,
        'performance': False
    }
    
    print("Running Full Test Suite...")
    
    # 1. System Health
    test_results['system_health'] = system_health_check()
    
    # 2. API Functionality
    try:
        test_full_pipeline()
        test_results['api_functionality'] = True
    except Exception as e:
        print(f"API test failed: {e}")
    
    # 3. WebSocket Connectivity
    try:
        asyncio.run(websocket_performance_test())
        test_results['websocket_connectivity'] = True
    except Exception as e:
        print(f"WebSocket test failed: {e}")
    
    # 4. Pipeline Processing
    try:
        upload_multiple_receipts(5)
        test_results['pipeline_processing'] = True
    except Exception as e:
        print(f"Pipeline test failed: {e}")
    
    # 5. Error Handling
    try:
        test_processing_failures()
        test_results['error_handling'] = True
    except Exception as e:
        print(f"Error handling test failed: {e}")
    
    # 6. Performance
    try:
        performance_test(num_receipts=10, concurrent_uploads=3)
        test_results['performance'] = True
    except Exception as e:
        print(f"Performance test failed: {e}")
    
    # Results Summary
    print("\n" + "="*50)
    print("TEST SUITE RESULTS")
    print("="*50)
    
    for test_name, passed in test_results.items():
        status_icon = "✓" if passed else "✗"
        print(f"{status_icon} {test_name.replace('_', ' ').title()}")
    
    overall_success = all(test_results.values())
    print(f"\nOverall Result: {'PASS' if overall_success else 'FAIL'}")
    
    return overall_success

# Run the complete test suite
run_full_test_suite()
```

---

## Usage Instructions

1. **Setup Environment**: Follow the environment setup section first
2. **Quick Test**: Run `test_full_pipeline()` to verify basic functionality
3. **Load Testing**: Use `performance_test()` for stress testing
4. **Monitoring**: Use diagnostic tools for real-time system monitoring
5. **Full Validation**: Execute `run_full_test_suite()` for comprehensive testing

This testing guide ensures thorough validation of the receipt processing system across all components, error scenarios, and performance requirements.