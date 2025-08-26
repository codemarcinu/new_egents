#!/usr/bin/env python3
"""
Test Data Generator for Receipt Processing System

This script creates test data including:
- Sample receipt images (mock files)
- Test user accounts
- Sample product database
- Test receipts in various states
- Performance test datasets

Usage:
    python create_test_data.py --help
    python create_test_data.py --create-all
    python create_test_data.py --create-images --count 20
    python create_test_data.py --create-users --count 5
    python create_test_data.py --create-products --count 100
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
import random
from datetime import datetime, timedelta

# Add Django to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')

import django
django.setup()

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont
import io

from agent_chat_app.receipts.models import Receipt, Product, Category, InventoryItem, ReceiptLineItem

User = get_user_model()

class TestDataGenerator:
    """Generate test data for comprehensive testing"""
    
    def __init__(self):
        self.test_dir = Path('tests')
        self.receipts_dir = self.test_dir / 'test_receipts'
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        
        # Sample store data
        self.stores = [
            "Super Market Plus", "Fresh Foods", "Corner Store", "Grocery World",
            "Metro Market", "City Supermarket", "Quick Shop", "Family Foods",
            "Green Grocers", "Food Express"
        ]
        
        # Sample product data
        self.product_categories = {
            "Dairy": ["Milk", "Cheese", "Yogurt", "Butter", "Cream"],
            "Bakery": ["Bread", "Rolls", "Croissants", "Muffins", "Bagels"],
            "Meat": ["Chicken Breast", "Ground Beef", "Pork Chops", "Salmon", "Bacon"],
            "Produce": ["Apples", "Bananas", "Tomatoes", "Lettuce", "Carrots"],
            "Beverages": ["Water", "Juice", "Soda", "Coffee", "Tea"],
            "Pantry": ["Rice", "Pasta", "Beans", "Cereal", "Oil"],
            "Snacks": ["Chips", "Cookies", "Crackers", "Nuts", "Chocolate"],
            "Household": ["Detergent", "Toilet Paper", "Soap", "Shampoo", "Toothpaste"]
        }
        
        # Price ranges by category
        self.price_ranges = {
            "Dairy": (2.50, 8.99),
            "Bakery": (1.99, 5.99),
            "Meat": (5.99, 15.99),
            "Produce": (0.99, 4.99),
            "Beverages": (1.49, 6.99),
            "Pantry": (1.99, 7.99),
            "Snacks": (2.49, 6.99),
            "Household": (3.99, 12.99)
        }
    
    def create_mock_receipt_image(self, store_name: str, items: List[Dict], 
                                total: float, receipt_id: str = None) -> bytes:
        """Create a mock receipt image"""
        
        # Calculate image dimensions
        width = 400
        line_height = 25
        header_height = 80
        footer_height = 60
        item_height = len(items) * line_height
        height = header_height + item_height + footer_height + 100
        
        # Create image
        img = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(img)
        
        # Try to use a basic font
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except:
            font = ImageFont.load_default()
            small_font = font
        
        y_offset = 20
        
        # Header
        draw.text((width//2 - len(store_name)*4, y_offset), store_name, fill='black', font=font)
        y_offset += 30
        draw.text((width//2 - 60, y_offset), "123 Test Street", fill='black', font=small_font)
        y_offset += 20
        draw.text((width//2 - 50, y_offset), f"Date: {datetime.now().strftime('%Y-%m-%d')}", fill='black', font=small_font)
        y_offset += 40
        
        # Line separator
        draw.line([(20, y_offset), (width-20, y_offset)], fill='black', width=1)
        y_offset += 20
        
        # Items
        for item in items:
            item_text = f"{item['name'][:20]}"
            quantity_text = f"{item['quantity']}x"
            price_text = f"${item['price']:.2f}"
            total_text = f"${item['total']:.2f}"
            
            # Item name
            draw.text((20, y_offset), item_text, fill='black', font=small_font)
            # Quantity and price
            draw.text((width-200, y_offset), quantity_text, fill='black', font=small_font)
            draw.text((width-150, y_offset), price_text, fill='black', font=small_font)
            # Total
            draw.text((width-80, y_offset), total_text, fill='black', font=small_font)
            
            y_offset += line_height
        
        # Footer separator
        y_offset += 10
        draw.line([(20, y_offset), (width-20, y_offset)], fill='black', width=2)
        y_offset += 20
        
        # Total
        draw.text((width-200, y_offset), f"TOTAL: ${total:.2f}", fill='black', font=font)
        y_offset += 40
        
        # Receipt ID (if provided)
        if receipt_id:
            draw.text((20, y_offset), f"Receipt ID: {receipt_id}", fill='black', font=small_font)
        
        # Convert to bytes
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()
    
    def create_test_images(self, count: int = 20) -> List[str]:
        """Create test receipt images"""
        print(f"📷 Creating {count} test receipt images...")
        
        created_files = []
        
        for i in range(count):
            # Generate random receipt data
            store = random.choice(self.stores)
            num_items = random.randint(2, 8)
            
            items = []
            total = 0.0
            
            for _ in range(num_items):
                category = random.choice(list(self.product_categories.keys()))
                product = random.choice(self.product_categories[category])
                price_range = self.price_ranges[category]
                
                quantity = random.randint(1, 3)
                unit_price = round(random.uniform(*price_range), 2)
                item_total = round(quantity * unit_price, 2)
                total += item_total
                
                items.append({
                    'name': product,
                    'quantity': quantity,
                    'price': unit_price,
                    'total': item_total
                })
            
            # Create image
            receipt_id = f"TEST{i+1:03d}"
            image_data = self.create_mock_receipt_image(store, items, total, receipt_id)
            
            # Determine image quality/type
            if i < count * 0.7:  # 70% good quality
                quality_suffix = "good"
            elif i < count * 0.9:  # 20% poor quality
                quality_suffix = "poor"
            else:  # 10% special cases
                quality_suffix = random.choice(["blurry", "rotated", "cropped"])
            
            filename = f"test_receipt_{i+1:03d}_{quality_suffix}.jpg"
            file_path = self.receipts_dir / filename
            
            with open(file_path, 'wb') as f:
                f.write(image_data)
            
            created_files.append(str(file_path))
            
            # Create some special case files
            if quality_suffix == "poor":
                # Create a lower quality version
                img = Image.open(io.BytesIO(image_data))
                img = img.resize((200, int(img.height * 200 / img.width)))
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=30)
                
                with open(file_path, 'wb') as f:
                    f.write(buffer.getvalue())
            
            elif quality_suffix == "blurry":
                # Add blur effect (simplified)
                img = Image.open(io.BytesIO(image_data))
                img = img.resize((int(img.width * 0.8), int(img.height * 0.8)))
                img = img.resize((img.width * 2, img.height * 2))
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=50)
                
                with open(file_path, 'wb') as f:
                    f.write(buffer.getvalue())
        
        # Create special test files
        special_files = self.create_special_test_files()
        created_files.extend(special_files)
        
        print(f"   ✅ Created {len(created_files)} test images in {self.receipts_dir}")
        return created_files
    
    def create_special_test_files(self) -> List[str]:
        """Create special test files for error scenarios"""
        special_files = []
        
        # Empty image (white)
        empty_img = Image.new('RGB', (400, 600), 'white')
        empty_path = self.receipts_dir / "empty_receipt.jpg"
        empty_img.save(empty_path, 'JPEG')
        special_files.append(str(empty_path))
        
        # Text file (invalid format)
        text_path = self.receipts_dir / "invalid.txt"
        with open(text_path, 'w') as f:
            f.write("This is not an image file")
        special_files.append(str(text_path))
        
        # Corrupted image
        corrupt_path = self.receipts_dir / "corrupted.jpg"
        with open(corrupt_path, 'wb') as f:
            f.write(b'Not a real JPEG file content')
        special_files.append(str(corrupt_path))
        
        return special_files
    
    def create_test_users(self, count: int = 5) -> List[User]:
        """Create test user accounts"""
        print(f"👥 Creating {count} test users...")
        
        created_users = []
        
        for i in range(count):
            username = f"testuser{i+1}"
            email = f"testuser{i+1}@example.com"
            
            # Delete existing user if exists
            User.objects.filter(username=username).delete()
            
            user = User.objects.create_user(
                username=username,
                email=email,
                password='testpass123',
                first_name=f"Test{i+1}",
                last_name="User"
            )
            
            # Make first user staff
            if i == 0:
                user.is_staff = True
                user.save()
            
            created_users.append(user)
        
        print(f"   ✅ Created {len(created_users)} test users")
        return created_users
    
    def create_product_database(self, count: int = 100) -> List[Product]:
        """Create sample product database"""
        print(f"🛒 Creating product database with {count} products...")
        
        created_products = []
        
        # Create categories first
        categories = {}
        for cat_name in self.product_categories.keys():
            category, created = Category.objects.get_or_create(
                name=cat_name,
                defaults={'description': f'{cat_name} products'}
            )
            categories[cat_name] = category
        
        # Create products
        product_id = 1
        while len(created_products) < count:
            for cat_name, product_names in self.product_categories.items():
                for product_name in product_names:
                    if len(created_products) >= count:
                        break
                    
                    # Create variations
                    variations = [
                        product_name,
                        f"{product_name} Organic",
                        f"{product_name} Premium",
                        f"Store Brand {product_name}",
                        f"{product_name} 2-Pack"
                    ]
                    
                    for variation in variations:
                        if len(created_products) >= count:
                            break
                        
                        product, created = Product.objects.get_or_create(
                            name=variation,
                            defaults={
                                'category': categories[cat_name],
                                'brand': random.choice(['Brand A', 'Brand B', 'Generic', 'Premium', 'Store']),
                                'barcode': f"123456{product_id:06d}",
                                'aliases': []
                            }
                        )
                        
                        if created:
                            created_products.append(product)
                            
                            # Create inventory item
                            InventoryItem.objects.get_or_create(
                                product=product,
                                defaults={
                                    'quantity': random.randint(0, 100),
                                    'unit': random.choice(['pcs', 'kg', 'liters', 'pack'])
                                }
                            )
                            
                            product_id += 1
                
                if len(created_products) >= count:
                    break
        
        print(f"   ✅ Created {len(created_products)} products with inventory")
        return created_products
    
    def create_test_receipts(self, users: List[User], count: int = 20) -> List[Receipt]:
        """Create test receipts in various states"""
        print(f"🧾 Creating {count} test receipts...")
        
        if not users:
            print("   ⚠️  No users provided, skipping receipt creation")
            return []
        
        created_receipts = []
        
        # Get some products for line items
        products = list(Product.objects.all()[:50])
        
        for i in range(count):
            user = random.choice(users)
            store_name = random.choice(self.stores)
            
            # Determine receipt status distribution
            if i < count * 0.3:  # 30% completed
                status = 'completed'
                processing_step = 'done'
            elif i < count * 0.6:  # 30% review pending
                status = 'review_pending'
                processing_step = 'review_pending'
            elif i < count * 0.8:  # 20% processing
                status = 'processing'
                processing_step = random.choice(['ocr_in_progress', 'parsing_in_progress', 'matching_in_progress'])
            elif i < count * 0.95:  # 15% pending
                status = 'pending'
                processing_step = 'uploaded'
            else:  # 5% error
                status = 'error'
                processing_step = 'failed'
            
            # Create receipt
            receipt = Receipt.objects.create(
                user=user,
                store_name=store_name,
                purchased_at=datetime.now() - timedelta(days=random.randint(0, 30)),
                total=round(random.uniform(5.99, 89.99), 2),
                currency='PLN',
                status=status,
                processing_step=processing_step,
                error_message='Test error message' if status == 'error' else '',
                raw_ocr_text=f'Test OCR text for receipt {i+1}' if status != 'pending' else '',
                extracted_data={'test': True, 'receipt_id': i+1} if status in ['completed', 'review_pending'] else {}
            )
            
            # Create line items for completed/review pending receipts
            if status in ['completed', 'review_pending'] and products:
                num_items = random.randint(2, 6)
                for _ in range(num_items):
                    product = random.choice(products)
                    quantity = random.randint(1, 3)
                    unit_price = round(random.uniform(1.99, 15.99), 2)
                    
                    ReceiptLineItem.objects.create(
                        receipt=receipt,
                        product_name=product.name,
                        quantity=quantity,
                        unit_price=unit_price,
                        line_total=round(quantity * unit_price, 2),
                        matched_product=product if random.random() > 0.2 else None,
                        match_confidence=random.uniform(0.7, 1.0),
                        match_type=random.choice(['exact', 'fuzzy', 'alias', 'created'])
                    )
            
            created_receipts.append(receipt)
        
        print(f"   ✅ Created {len(created_receipts)} test receipts")
        return created_receipts
    
    def create_performance_dataset(self, image_count: int = 50) -> str:
        """Create dataset for performance testing"""
        print(f"⚡ Creating performance test dataset...")
        
        perf_dir = self.test_dir / 'performance'
        perf_dir.mkdir(exist_ok=True)
        
        # Create batch of similar receipt images
        created_files = []
        
        for i in range(image_count):
            # Use consistent format for performance testing
            store = "Performance Test Store"
            items = [
                {'name': 'Test Item A', 'quantity': 1, 'price': 2.99, 'total': 2.99},
                {'name': 'Test Item B', 'quantity': 2, 'price': 4.50, 'total': 9.00},
                {'name': 'Test Item C', 'quantity': 1, 'price': 1.99, 'total': 1.99}
            ]
            total = sum(item['total'] for item in items)
            
            image_data = self.create_mock_receipt_image(store, items, total, f"PERF{i+1:03d}")
            
            filename = f"perf_test_{i+1:03d}.jpg"
            file_path = perf_dir / filename
            
            with open(file_path, 'wb') as f:
                f.write(image_data)
            
            created_files.append(str(file_path))
        
        # Create manifest file
        manifest = {
            'created_at': datetime.now().isoformat(),
            'image_count': len(created_files),
            'files': created_files,
            'test_parameters': {
                'expected_store': "Performance Test Store",
                'expected_items': 3,
                'expected_total': sum(item['total'] for item in items)
            }
        }
        
        manifest_path = perf_dir / 'manifest.json'
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        print(f"   ✅ Created {len(created_files)} performance test images")
        print(f"   📄 Manifest saved to {manifest_path}")
        return str(perf_dir)
    
    def create_config_files(self) -> List[str]:
        """Create configuration files for testing"""
        print("⚙️  Creating test configuration files...")
        
        config_files = []
        
        # API test configuration
        api_config = {
            "api_base_url": "http://localhost:8000",
            "ws_base_url": "ws://localhost:8000",
            "test_user": "testuser1",
            "test_password": "testpass123",
            "performance": {
                "receipts": 20,
                "concurrent_uploads": 5,
                "timeout_seconds": 120
            },
            "websocket": {
                "concurrent_connections": 10,
                "test_duration_seconds": 30
            }
        }
        
        api_config_path = self.test_dir / 'api_config.json'
        with open(api_config_path, 'w') as f:
            json.dump(api_config, f, indent=2)
        config_files.append(str(api_config_path))
        
        # Test suite configuration
        suite_config = {
            "test_files": {
                "good_quality": "tests/test_receipts/test_receipt_001_good.jpg",
                "poor_quality": "tests/test_receipts/test_receipt_015_poor.jpg",
                "corrupted": "tests/test_receipts/corrupted.jpg",
                "performance_batch": "tests/performance/"
            },
            "success_criteria": {
                "min_success_rate": 85,
                "max_processing_time_minutes": 2,
                "min_ocr_accuracy": 90,
                "max_websocket_latency_ms": 100
            },
            "load_test": {
                "concurrent_receipts": 50,
                "max_workers": 10,
                "timeout_minutes": 10
            }
        }
        
        suite_config_path = self.test_dir / 'test_suite_config.json'
        with open(suite_config_path, 'w') as f:
            json.dump(suite_config, f, indent=2)
        config_files.append(str(suite_config_path))
        
        print(f"   ✅ Created {len(config_files)} configuration files")
        return config_files
    
    def generate_test_report_template(self) -> str:
        """Generate test report template"""
        template_path = self.test_dir / 'test_report_template.md'
        
        template_content = """# Receipt Processing System - Test Report

**Test Date:** {test_date}
**Test Environment:** {environment}
**Tester:** {tester}

## Test Summary

- **Total Test Suites:** {total_suites}
- **Passed Suites:** {passed_suites}
- **Failed Suites:** {failed_suites}
- **Overall Success Rate:** {success_rate}%

## System Health Check

| Component | Status | Notes |
|-----------|--------|-------|
| Django Server | ✅/❌ | HTTP response status |
| Redis | ✅/❌ | Connection test |
| Celery | ✅/❌ | Worker status |
| Database | ✅/❌ | Query test |
| Ollama | ✅/❌ | Model availability |

## API Tests

| Test | Status | Duration | Notes |
|------|--------|----------|-------|
| Health Check | ✅/❌ | {duration}s | {notes} |
| Receipt Upload | ✅/❌ | {duration}s | {notes} |
| Status Monitoring | ✅/❌ | {duration}s | {notes} |
| Statistics | ✅/❌ | {duration}s | {notes} |
| Error Handling | ✅/❌ | {duration}s | {notes} |

## WebSocket Tests

| Test | Status | Duration | Notes |
|------|--------|----------|-------|
| Connection | ✅/❌ | {duration}s | {notes} |
| Authentication | ✅/❌ | {duration}s | {notes} |
| Receipt Progress | ✅/❌ | {duration}s | {notes} |
| Notifications | ✅/❌ | {duration}s | {notes} |
| Performance | ✅/❌ | {duration}s | Avg latency: {latency}ms |

## Performance Metrics

- **Throughput:** {throughput} receipts/second
- **Average Processing Time:** {avg_processing_time} minutes
- **Success Rate:** {success_rate}%
- **WebSocket Latency:** {ws_latency}ms

## Issues Found

1. **Issue Title**
   - Severity: High/Medium/Low
   - Description: 
   - Steps to reproduce:
   - Expected vs Actual:

## Recommendations

1. **Performance Optimization**
   - 

2. **Error Handling**
   - 

3. **User Experience**
   - 

## Test Environment Details

- **OS:** 
- **Python Version:** 
- **Django Version:** 
- **Redis Version:** 
- **Celery Version:** 
- **Hardware:** 

---
*Generated by Receipt Processing Test Suite*
"""
        
        with open(template_path, 'w') as f:
            f.write(template_content)
        
        print(f"   ✅ Test report template saved to {template_path}")
        return str(template_path)
    
    def cleanup_test_data(self):
        """Clean up existing test data"""
        print("🧹 Cleaning up existing test data...")
        
        # Delete test receipts
        Receipt.objects.filter(user__username__startswith='testuser').delete()
        
        # Delete test users
        User.objects.filter(username__startswith='testuser').delete()
        
        # Keep products and categories as they might be useful
        
        print("   ✅ Test data cleaned up")

def main():
    parser = argparse.ArgumentParser(description="Test Data Generator for Receipt Processing System")
    
    # Actions
    parser.add_argument("--create-all", action="store_true", help="Create all test data")
    parser.add_argument("--create-images", action="store_true", help="Create test receipt images")
    parser.add_argument("--create-users", action="store_true", help="Create test user accounts")
    parser.add_argument("--create-products", action="store_true", help="Create product database")
    parser.add_argument("--create-receipts", action="store_true", help="Create test receipts")
    parser.add_argument("--create-performance", action="store_true", help="Create performance test dataset")
    parser.add_argument("--create-configs", action="store_true", help="Create configuration files")
    parser.add_argument("--cleanup", action="store_true", help="Clean up existing test data")
    
    # Parameters
    parser.add_argument("--image-count", type=int, default=20, help="Number of test images to create")
    parser.add_argument("--user-count", type=int, default=5, help="Number of test users to create")
    parser.add_argument("--product-count", type=int, default=100, help="Number of products to create")
    parser.add_argument("--receipt-count", type=int, default=20, help="Number of test receipts to create")
    parser.add_argument("--perf-count", type=int, default=50, help="Number of performance test images")
    
    args = parser.parse_args()
    
    generator = TestDataGenerator()
    
    if args.cleanup:
        generator.cleanup_test_data()
    
    users = []
    
    if args.create_all or args.create_users:
        users = generator.create_test_users(args.user_count)
    else:
        # Get existing test users
        users = list(User.objects.filter(username__startswith='testuser'))
    
    if args.create_all or args.create_products:
        generator.create_product_database(args.product_count)
    
    if args.create_all or args.create_images:
        generator.create_test_images(args.image_count)
    
    if args.create_all or args.create_receipts:
        generator.create_test_receipts(users, args.receipt_count)
    
    if args.create_all or args.create_performance:
        generator.create_performance_dataset(args.perf_count)
    
    if args.create_all or args.create_configs:
        generator.create_config_files()
        generator.generate_test_report_template()
    
    if args.create_all:
        print("\n🎉 Test data generation complete!")
        print(f"   📁 Test directory: {generator.test_dir}")
        print(f"   📷 Receipt images: {generator.receipts_dir}")
        print("   🚀 Ready for testing!")

if __name__ == "__main__":
    main()