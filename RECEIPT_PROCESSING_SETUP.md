# Receipt Processing System - Setup Guide

This document provides instructions for setting up and using the Receipt Processing System that has been implemented in your Agent Chat App.

## 🎯 System Overview

The Receipt Processing System implements the complete pipeline described in `system-paragonow-guide.md`:

**OCR → Parse → Match → Inventory**

- **OCR**: Hybrid OCR with EasyOCR, Tesseract, PaddleOCR, and Google Vision fallbacks
- **Parser**: LLM-based structured data extraction using Ollama or Mistral API
- **Matcher**: Intelligent product matching with fuzzy matching and automatic alias creation
- **Inventory**: Automatic inventory updates with history tracking

## 📦 Installation & Setup

### 1. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements/base.txt

# Install system dependencies for OCR
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-pol  # Polish language support
sudo apt-get install libgl1-mesa-glx libglib2.0-0  # OpenCV dependencies
```

### 2. Install Ollama (for LLM parsing)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model (e.g., llama3.2)
ollama pull llama3.2
```

### 3. Apply Database Migrations

```bash
python manage.py migrate
```

### 4. Configure Settings (Optional)

Add to your settings file for additional features:

```python
# Optional: Google Cloud Vision API key
# GOOGLE_APPLICATION_CREDENTIALS = '/path/to/service-account.json'

# Optional: Mistral API key  
# MISTRAL_API_KEY = 'your-mistral-api-key'

# Redis for WebSocket support (should already be configured)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('127.0.0.1', 6379)],
        },
    },
}
```

## 🚀 Usage

### Web Interface

1. **Navigate to Receipts**: Click "Receipts" in the navigation menu
2. **Upload Receipt**: Click "Upload New Receipt" and drag/drop or select an image
3. **Real-time Tracking**: Watch the progress in real-time via WebSocket updates
4. **View Results**: See processed data with matched products and inventory updates

### API Endpoints

```bash
# Upload receipt
POST /receipts/api/upload/
Content-Type: multipart/form-data
Body: receipt_file=<image_file>

# Check status
GET /receipts/api/{receipt_id}/status/

# Get receipt details
GET /receipts/api/{receipt_id}/

# List receipts
GET /receipts/api/

# Search products
POST /receipts/api/products/search/
{"query": "milk", "limit": 10}

# View inventory
GET /receipts/api/inventory/

# Update inventory manually
POST /receipts/api/inventory/update/
{"product_id": 1, "quantity": 10.0, "notes": "Manual adjustment"}
```

### WebSocket Connections

```javascript
// Real-time receipt processing updates
const socket = new WebSocket(`ws://localhost:8000/ws/receipt/${receiptId}/`);

// Inventory notifications
const inventorySocket = new WebSocket('ws://localhost:8000/ws/inventory/');

// General notifications
const notificationSocket = new WebSocket('ws://localhost:8000/ws/notifications/');
```

## 🎛 Services & Architecture

### Core Services

1. **HybridOCRService** (`receipts/services/ocr_service.py`)
   - Multiple OCR backends with fallback
   - Image preprocessing for better accuracy
   - Configurable confidence thresholds

2. **ReceiptParser** (`receipts/services/receipt_parser.py`)  
   - LLM-based structured data extraction
   - Support for Ollama and Mistral APIs
   - Fallback regex parsing

3. **ProductMatcher** (`receipts/services/product_matcher.py`)
   - Fuzzy matching with configurable thresholds
   - Automatic alias learning
   - Ghost product creation for unknowns

4. **InventoryService** (`receipts/services/inventory_service.py`)
   - Automatic inventory updates from receipts
   - Manual adjustments with history
   - Low stock alerts

### Celery Tasks

- **process_receipt_task**: Main processing pipeline
- **cleanup_old_processed_images**: Housekeeping
- **generate_inventory_report**: Periodic reporting

## 🔧 Configuration Options

### OCR Configuration

```python
# In your service initialization
ocr_service = HybridOCRService(
    confidence_threshold=0.7,  # Minimum confidence to stop trying backends
    max_backends=2,            # Maximum backends to try
    timeout=30                 # Timeout per backend in seconds
)
```

### Parser Configuration

```python
# Use Ollama (default)
parser = get_receipt_parser("ollama")

# Use Mistral API  
parser = get_receipt_parser("mistral")
```

### Matcher Configuration

```python
matcher = ProductMatcher(
    fuzzy_match_threshold=0.75,  # Minimum similarity for fuzzy matches
    auto_create_products=True    # Create ghost products for unknowns
)
```

## 📊 Admin Interface

The Django admin interface provides full access to:

- **Categories**: Product categories with hierarchy
- **Products**: Product catalog with aliases
- **Receipts**: Processing status and results
- **ReceiptLineItems**: Individual parsed items
- **InventoryItems**: Current stock levels
- **InventoryHistory**: All inventory changes

## 🔍 Troubleshooting

### Common Issues

1. **OCR Not Working**
   - Check Tesseract installation: `tesseract --version`
   - Verify image file permissions
   - Check logs for specific OCR backend errors

2. **LLM Parsing Fails**
   - Ensure Ollama is running: `ollama list`
   - Check model availability: `ollama pull llama3.2`
   - Verify API connectivity

3. **WebSocket Issues**
   - Ensure Redis is running: `redis-cli ping`
   - Check Django Channels configuration
   - Verify WebSocket routing

4. **File Upload Issues**
   - Check `MEDIA_ROOT` and `MEDIA_URL` settings
   - Verify file permissions
   - Check maximum file size limits

### Performance Optimization

1. **GPU Acceleration**: Set `gpu=True` in EasyOCR for CUDA-enabled systems
2. **Celery Workers**: Scale worker processes based on load
3. **Database Indexes**: Included in migrations for optimal query performance
4. **Caching**: Consider Redis caching for frequent product lookups

## 📈 Monitoring & Analytics

### Available Statistics

- Processing success rates
- Average processing time
- Product matching accuracy
- Inventory coverage
- Low stock alerts

### Logging

All services include comprehensive logging. Check Django logs for:
- Processing pipeline status
- OCR backend performance
- Product matching results
- Inventory updates

## 🔐 Security Considerations

- File upload validation (type, size)
- User authentication for all endpoints
- WebSocket connection authentication
- Input sanitization in parsers
- Secure file storage configuration

## 🚀 Production Deployment

For production deployment:

1. **Scale Celery Workers**: Use multiple worker processes
2. **Configure Redis Cluster**: For high availability
3. **Set up File Storage**: Use cloud storage (S3, GCS)
4. **Enable SSL**: For secure WebSocket connections
5. **Monitor Resources**: OCR processing is CPU/memory intensive
6. **Backup Strategy**: Include uploaded images and database

## 🔄 Maintenance Tasks

Regular maintenance includes:

1. **Image Cleanup**: Run `cleanup_old_processed_images` task
2. **Inventory Reports**: Schedule `generate_inventory_report`
3. **Database Optimization**: Monitor query performance
4. **Model Updates**: Keep LLM models current

---

The Receipt Processing System is now fully integrated into your Agent Chat App and ready for use! 🎉