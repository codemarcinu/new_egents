# System Obsługi Paragonów - Przewodnik Implementacji

## 📋 Przegląd Systemu

System obsługi paragonów to kompletny pipeline przetwarzania: **OCR → Parse → Match → Inventory**, który automatycznie przetwarza zdjęcia paragonów na strukturalne dane produktów w magazynie.

### 🎯 Główne komponenty systemu:

1. **Modele danych** - `Receipt`, `ReceiptLineItem`, `Product`, `Category`, `InventoryItem`
2. **OCR hybrydowy** - EasyOCR + Tesseract + Mistral API z inteligentnym fallback
3. **Parser AI** - Ekstrakcja strukturalnych danych z LLM
4. **Product Matcher** - Fuzzy matching z automatycznym tworzeniem aliasów
5. **Asynchroniczne przetwarzanie** - Celery + WebSocket notifications
6. **API endpoints** - RESTful API do obsługi całego procesu

## 🏗️ Struktura Implementacji

### 1. Modele Danych (Django Models)

#### **Receipt Model** - Główny model paragonu
```python
class Receipt(models.Model):
    # Status tracking
    STATUS_CHOICES = [
        ("pending", "Oczekuje"),
        ("processing", "W trakcie przetwarzania"), 
        ("review_pending", "Oczekuje na weryfikację"),
        ("completed", "Zakończono"),
        ("error", "Błąd"),
    ]
    
    PROCESSING_STEP_CHOICES = [
        ("uploaded", "File Uploaded"),
        ("ocr_in_progress", "OCR in Progress"),
        ("ocr_completed", "OCR Completed"),
        ("parsing_in_progress", "Parsing in Progress"),
        ("parsing_completed", "Parsing Completed"),
        ("matching_in_progress", "Matching Products"),
        ("matching_completed", "Matching Completed"),
        ("finalizing_inventory", "Finalizing Inventory"),
        ("review_pending", "Review Pending"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]
    
    # Pola podstawowe
    store_name = models.CharField(max_length=200, blank=True, default="")
    purchased_at = models.DateTimeField(null=True, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="PLN")
    
    # Pola techniczne
    receipt_file = models.FileField(upload_to="receipt_files/")
    raw_ocr_text = models.TextField(blank=True)
    raw_text = JSONField(default=dict, blank=True)
    extracted_data = JSONField(null=True, blank=True)
    parsed_data = JSONField(default=dict, blank=True)
    
    # Status i tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    processing_step = models.CharField(max_length=30, choices=PROCESSING_STEP_CHOICES)
    error_message = models.TextField(blank=True)
    task_id = models.CharField(max_length=255, blank=True)
    
    # Business logic methods
    def mark_as_processing(self, step=None):
        self.status = 'processing'
        if step:
            self.processing_step = step
        self.save()
    
    def mark_as_completed(self):
        self.status = "completed"
        self.processing_step = "done"
        self.processed_at = timezone.now()
        self.save()
```

#### **Product Model** - Katalog produktów z aliasami
```python
class Product(models.Model):
    name = models.CharField(max_length=300, db_index=True)
    brand = models.CharField(max_length=100, blank=True)
    barcode = models.CharField(max_length=50, blank=True, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    
    # Aliasy dla fuzzy matching
    aliases = JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)  # False dla "ghost" produktów
    
    def add_alias(self, alias_name):
        """Dodaj alias z metadanymi (count, first_seen, last_seen, status)"""
        found = False
        for alias_entry in self.aliases:
            if alias_entry.get("name") == alias_name:
                alias_entry["count"] = alias_entry.get("count", 0) + 1
                alias_entry["last_seen"] = timezone.now().isoformat()
                found = True
                break
        
        if not found:
            self.aliases.append({
                "name": alias_name,
                "count": 1,
                "first_seen": timezone.now().isoformat(),
                "last_seen": timezone.now().isoformat(),
                "status": "unverified",
            })
        
        self.save(update_fields=["aliases"])
```

### 2. Serwisy Przetwarzania

#### **UnifiedReceiptProcessor** - Główny orchestrator
```python
class UnifiedReceiptProcessor:
    """Ujednolicony procesor łączący OCR i parsing"""
    
    def __init__(self):
        self.ocr_service = ocr_service
        self.receipt_parser = get_receipt_parser()
    
    def process_receipt(self, file_path: str) -> ExtractedReceipt:
        logger.info(f"Starting unified processing for file: {file_path}")
        
        # Krok 1: OCR
        ocr_result = self.ocr_service.process_file(file_path)
        if not ocr_result.success:
            raise ValueError(f"OCR processing failed: {ocr_result.error_message}")
        
        # Krok 2: Parsing z LLM
        try:
            parsed_data_dict = self.receipt_parser.parse(ocr_result.text)
            extracted_receipt = ExtractedReceipt(**parsed_data_dict)
            logger.info(f"Successfully parsed receipt data for {file_path}")
            return extracted_receipt
        except Exception as e:
            logger.error(f"Parsing failed for {file_path}: {e}")
            raise
```

#### **HybridOCRService** - System OCR z fallback
```python
class HybridOCRService:
    """Hybrydowy OCR z wieloma backend-ami"""
    
    def __init__(self, confidence_threshold=0.7):
        self.confidence_threshold = confidence_threshold
        self.backends = [
            EasyOCRBackend(),      # GPU-accelerated, najlepszy dla receipts
            TesseractBackend(),    # CPU fallback
            PaddleOCRBackend(),    # Dodatkowy fallback
            GoogleVisionBackend()  # Premium opcja
        ]
        self.available_backends = [b for b in self.backends if b.is_available()]
    
    async def extract_text_from_file(self, image_path: str) -> str:
        if not self.available_backends:
            raise RuntimeError("No OCR backends are available")
        
        # Preprocessing obrazu
        processor = get_image_processor()
        processing_result = processor.preprocess_image(image_path)
        ocr_image_path = processing_result.processed_path if processing_result.success else image_path
        
        # Adaptacyjna strategia OCR na podstawie jakości obrazu
        results = []
        for backend in self.available_backends[:self.max_backends]:
            try:
                result = await asyncio.wait_for(
                    backend.extract_text(ocr_image_path),
                    timeout=self.timeout
                )
                results.append(result)
                
                # Zatrzymaj jeśli wysoka pewność
                if result.success and result.confidence >= self.confidence_threshold:
                    break
                    
            except Exception as e:
                logger.warning(f"OCR backend {backend.name} failed: {e}")
                continue
        
        if not results:
            raise RuntimeError("All OCR backends failed")
        
        # Wybierz najlepszy wynik
        best_result = self._select_best_result(results)
        return best_result.text
```

#### **ProductMatcher** - Inteligentne dopasowywanie
```python
class ProductMatcher:
    """Dopasowywanie produktów z fuzzy matching i aliasami"""
    
    def match_product(self, parsed_product, all_parsed_products=None) -> MatchResult:
        normalized_name = self.normalize_product_name(parsed_product.name)
        
        # 1. Exact match
        exact_match = self._find_exact_match(normalized_name)
        if exact_match:
            return MatchResult(
                product=exact_match,
                confidence=1.0,
                match_type="exact",
                normalized_name=normalized_name
            )
        
        # 2. Alias match
        alias_match, matched_alias = self._find_alias_match(normalized_name)
        if alias_match:
            return MatchResult(
                product=alias_match,
                confidence=0.9,
                match_type="alias",
                matched_alias=matched_alias
            )
        
        # 3. Fuzzy match
        fuzzy_match, similarity = self._find_fuzzy_match(normalized_name)
        if fuzzy_match and similarity >= self.fuzzy_match_threshold:
            return MatchResult(
                product=fuzzy_match,
                confidence=similarity,
                match_type="fuzzy"
            )
        
        # 4. Create ghost product
        ghost_product = self._create_ghost_product(parsed_product, normalized_name)
        return MatchResult(
            product=ghost_product,
            confidence=0.5,
            match_type="created",
            category_guess=ghost_product.category
        )
    
    def normalize_product_name(self, name: str) -> str:
        """Normalizacja nazw produktów - usuwa wagi, objętości, marki"""
        normalized = name.lower().strip()
        
        # Usuń informacje o wadze/objętości
        weight_patterns = [
            r'\b\d+\s*(?:kg|g|gram|grams|kilogram|kilograms)\b',
            r'\b\d+\s*(?:l|litr|litry|litrów|ml|millilitr)\b',
            r'\b\d+(?:[.,]\d+)?\s*(?:kg|g|l|ml)\b',
        ]
        
        for pattern in weight_patterns:
            normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)
        
        # Usuń prefiksy marek
        brand_patterns = [
            r'^(?:tesco|carrefour|biedronka|auchan|kaufland|lidl)\s+',
            r'^(?:organic|bio|eco)\s+',
        ]
        
        for pattern in brand_patterns:
            normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)
        
        return " ".join(normalized.split()).strip()
```

### 3. API Endpoints

#### **Receipt Upload API**
```python
# chatbot/api/receipt_views.py
class ReceiptUploadAPIView(APIView):
    def post(self, request):
        serializer = ReceiptUploadSerializer(data=request.data)
        if serializer.is_valid():
            receipt_file = serializer.validated_data['receipt_file']
            
            # Utwórz obiekt Receipt
            receipt = Receipt.objects.create(
                receipt_file=receipt_file,
                status='pending',
                processing_step='uploaded'
            )
            
            # Uruchom asynchroniczne przetwarzanie
            from ..tasks import process_receipt_task
            task = process_receipt_task.delay(receipt.id)
            receipt.task_id = task.id
            receipt.save()
            
            return Response({
                'receipt_id': receipt.id,
                'task_id': task.id,
                'status': 'uploaded',
                'message': 'Receipt uploaded successfully, processing started'
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ReceiptStatusAPIView(APIView):
    def get(self, request, receipt_id):
        try:
            receipt = Receipt.objects.get(id=receipt_id)
            return Response({
                'receipt_id': receipt.id,
                'status': receipt.status,
                'processing_step': receipt.processing_step,
                'error_message': receipt.error_message,
                'progress_percentage': self._calculate_progress(receipt),
            })
        except Receipt.DoesNotExist:
            return Response({'error': 'Receipt not found'}, 
                          status=status.HTTP_404_NOT_FOUND)
```

### 4. Asynchroniczne Zadania (Celery)

#### **Process Receipt Task**
```python
# chatbot/tasks.py
@shared_task(bind=True, max_retries=3)
def process_receipt_task(self, receipt_id):
    """Główne zadanie przetwarzania paragonu"""
    
    try:
        receipt = Receipt.objects.get(id=receipt_id)
        receipt.mark_as_processing('ocr_in_progress')
        
        # Krok 1: OCR
        from .services.hybrid_ocr_service import get_hybrid_ocr_service
        ocr_service = get_hybrid_ocr_service()
        
        raw_text = asyncio.run(
            ocr_service.extract_text_from_file(receipt.receipt_file.path)
        )
        receipt.mark_ocr_done(raw_text)
        
        # Krok 2: Parsing z LLM
        receipt.mark_llm_processing()
        from .services.receipt_parser import get_receipt_parser
        parser = get_receipt_parser()
        
        extracted_data = parser.parse(raw_text)
        receipt.mark_llm_done(extracted_data)
        
        # Krok 3: Product Matching
        receipt.status = 'processing'
        receipt.processing_step = 'matching_in_progress'
        receipt.save()
        
        from .services.product_matcher import get_product_matcher
        matcher = get_product_matcher()
        
        # Convert to ParsedProduct objects
        parsed_products = [
            ParsedProduct(
                name=p['product'],
                quantity=float(p['quantity']),
                price=float(p['price'])
            )
            for p in extracted_data['products']
        ]
        
        match_results = matcher.batch_match_products(parsed_products)
        
        # Krok 4: Tworzenie ReceiptLineItem
        receipt.processing_step = 'matching_completed'
        receipt.save()
        
        for i, (parsed_product, match_result) in enumerate(zip(parsed_products, match_results)):
            ReceiptLineItem.objects.create(
                receipt=receipt,
                product_name=parsed_product.name,
                quantity=Decimal(str(parsed_product.quantity)),
                unit_price=Decimal(str(parsed_product.price)),
                line_total=Decimal(str(parsed_product.total_price)),
                matched_product=match_result.product
            )
        
        # Krok 5: Aktualizacja Inventory
        receipt.processing_step = 'finalizing_inventory'
        receipt.save()
        
        from .services.inventory_service import get_inventory_service
        inventory_service = get_inventory_service()
        
        for line_item in receipt.line_items.all():
            if line_item.matched_product:
                inventory_service.add_inventory_from_receipt_item(line_item)
        
        # Finalizacja
        receipt.mark_as_completed()
        
        # Wyślij notyfikację WebSocket
        from .services.websocket_notifier import notify_receipt_completed
        notify_receipt_completed(receipt_id)
        
        return {
            'status': 'completed',
            'receipt_id': receipt_id,
            'products_processed': len(parsed_products)
        }
        
    except Exception as e:
        logger.error(f"Receipt processing failed for {receipt_id}: {e}")
        receipt.mark_as_error(str(e))
        
        # Retry logic
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2 ** self.request.retries))
        
        return {'status': 'failed', 'error': str(e)}
```

### 5. WebSocket Notifications

#### **Real-time Updates**
```python
# chatbot/consumers.py
class ReceiptProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.receipt_id = self.scope['url_route']['kwargs']['receipt_id']
        self.room_group_name = f'receipt_{self.receipt_id}'
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def receipt_status_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'receipt_id': event['receipt_id'],
            'status': event['status'],
            'processing_step': event['processing_step'],
            'progress_percentage': event['progress_percentage'],
            'message': event['message']
        }))

# chatbot/services/websocket_notifier.py
def notify_receipt_status_update(receipt_id, status, processing_step, message=""):
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    channel_layer = get_channel_layer()
    progress_percentage = calculate_progress_from_step(processing_step)
    
    async_to_sync(channel_layer.group_send)(
        f'receipt_{receipt_id}',
        {
            'type': 'receipt_status_update',
            'receipt_id': receipt_id,
            'status': status,
            'processing_step': processing_step,
            'progress_percentage': progress_percentage,
            'message': message
        }
    )
```

## 🚀 Implementacja w Nowym Projekcie

### Krok 1: Zależności
```bash
pip install django celery redis channels daphne
pip install easyocr pytesseract Pillow
pip install fuzzywuzzy python-levenshtein
pip install ollama-python requests
```

### Krok 2: Konfiguracja Django
```python
# settings.py
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'channels',
    'chatbot',
    'inventory',
]

# Celery Configuration
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

# Channels Configuration
ASGI_APPLICATION = 'core.asgi.application'
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('127.0.0.1', 6379)],
        },
    },
}

# File Upload Settings
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
```

### Krok 3: Uruchomienie Serwisów
```bash
# Terminal 1: Django
python manage.py runserver

# Terminal 2: Celery Worker
celery -A core worker --loglevel=info

# Terminal 3: Celery Beat (jeśli potrzebny)
celery -A core beat --loglevel=info

# Terminal 4: Redis
redis-server

# Terminal 5: Channels (ASGI)
python manage.py runserver --asgi
```

### Krok 4: Frontend Integration
```javascript
// WebSocket connection dla real-time updates
const receiptSocket = new WebSocket(`ws://localhost:8000/ws/receipt/${receiptId}/`);

receiptSocket.onmessage = function(e) {
    const data = JSON.parse(e.data);
    if (data.type === 'status_update') {
        updateProgressBar(data.progress_percentage);
        updateStatusMessage(data.message);
        
        if (data.status === 'completed') {
            showCompletionMessage();
            loadReceiptResults(data.receipt_id);
        }
    }
};

// Upload paragonu
async function uploadReceipt(file) {
    const formData = new FormData();
    formData.append('receipt_file', file);
    
    const response = await fetch('/api/receipts/upload/', {
        method: 'POST',
        body: formData
    });
    
    const data = await response.json();
    return data.receipt_id;
}
```

## 💡 Kluczowe Zalety Systemu

1. **Kompletny Pipeline**: Od zdjęcia do magazynu w jednym procesie
2. **Wysoka Niezawodność**: Wielopoziomowy fallback OCR
3. **Inteligentne Dopasowywanie**: Fuzzy matching z uczeniem się
4. **Real-time Updates**: WebSocket notifications
5. **Asynchroniczność**: Celery dla wydajności
6. **Skalowalność**: Modular architecture
7. **Monitoring**: Szczegółowe logowanie i tracking

## 🔧 Konfiguracja dla Różnych Przypadków

### Dla małych sklepów (podstawowa konfiguracja):
- Tylko EasyOCR + Tesseract
- Podstawowe product matching
- SQLite database

### Dla średnich firm (rozszerzona):
- Pełny hybrid OCR
- PostgreSQL + Redis
- Advanced analytics

### Dla dużych systemów (enterprise):
- Wszystkie backend-y OCR
- Kubernetes deployment
- Advanced monitoring
- Machine learning improvements

Ten system obsługi paragonów zapewnia kompletne rozwiązanie od rozpoznawania tekstu po zarządzanie magazynem, z wysoką dokładnością i możliwością dostosowania do różnych potrzeb biznesowych.