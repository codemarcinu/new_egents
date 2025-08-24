"""
Receipt processing models for the agent chat app.
Implements the models described in system-paragonow-guide.md
"""

import json
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model


User = get_user_model()


class Category(models.Model):
    """Product category model."""
    name = models.CharField(max_length=200, unique=True, db_index=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='subcategories'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Product(models.Model):
    """Product catalog with aliases for fuzzy matching."""
    name = models.CharField(max_length=300, db_index=True)
    brand = models.CharField(max_length=100, blank=True)
    barcode = models.CharField(max_length=50, blank=True, db_index=True)
    category = models.ForeignKey(
        Category, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # Aliases for fuzzy matching - stored as JSON
    aliases = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)  # False for "ghost" products
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['barcode']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.brand})" if self.brand else self.name
    
    def add_alias(self, alias_name):
        """Add alias with metadata (count, first_seen, last_seen, status)"""
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


class Receipt(models.Model):
    """Main receipt model for processing pipeline."""
    
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
    
    CURRENCY_CHOICES = [
        ("PLN", "Polish Złoty"),
        ("EUR", "Euro"),
        ("USD", "US Dollar"),
        ("GBP", "British Pound"),
    ]
    
    # Basic fields
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='receipts')
    store_name = models.CharField(max_length=200, blank=True, default="")
    purchased_at = models.DateTimeField(null=True, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="PLN")
    
    # Technical fields
    receipt_file = models.FileField(upload_to="receipt_files/")
    raw_ocr_text = models.TextField(blank=True)
    raw_text = models.JSONField(default=dict, blank=True)
    extracted_data = models.JSONField(null=True, blank=True)
    parsed_data = models.JSONField(default=dict, blank=True)
    
    # Status and tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    processing_step = models.CharField(
        max_length=30, 
        choices=PROCESSING_STEP_CHOICES, 
        default="uploaded"
    )
    error_message = models.TextField(blank=True)
    task_id = models.CharField(max_length=255, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['status', 'processing_step']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Receipt {self.id} - {self.store_name} ({self.status})"
    
    def mark_as_processing(self, step=None):
        """Mark receipt as processing with optional step."""
        self.status = 'processing'
        if step:
            self.processing_step = step
        self.save()
    
    def mark_as_completed(self):
        """Mark receipt as completed."""
        self.status = "completed"
        self.processing_step = "done"
        self.processed_at = timezone.now()
        self.save()
    
    def mark_as_error(self, error_message):
        """Mark receipt as failed with error message."""
        self.status = "error"
        self.processing_step = "failed"
        self.error_message = error_message
        self.save()
    
    def mark_ocr_done(self, raw_text):
        """Mark OCR processing as complete."""
        self.raw_ocr_text = raw_text
        self.processing_step = "ocr_completed"
        self.save()
    
    def mark_llm_processing(self):
        """Mark LLM parsing as in progress."""
        self.processing_step = "parsing_in_progress"
        self.save()
    
    def mark_llm_done(self, extracted_data):
        """Mark LLM parsing as complete."""
        self.extracted_data = extracted_data
        self.processing_step = "parsing_completed"
        self.save()


class ReceiptLineItem(models.Model):
    """Individual line items from a receipt."""
    receipt = models.ForeignKey(
        Receipt, 
        on_delete=models.CASCADE, 
        related_name='line_items'
    )
    
    # Product information from receipt
    product_name = models.CharField(max_length=300)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Matched product
    matched_product = models.ForeignKey(
        Product, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='receipt_line_items'
    )
    
    # Matching metadata
    match_confidence = models.FloatField(default=0.0)
    match_type = models.CharField(
        max_length=20, 
        choices=[
            ('exact', 'Exact Match'),
            ('alias', 'Alias Match'),
            ('fuzzy', 'Fuzzy Match'),
            ('created', 'Created Product'),
            ('manual', 'Manual Match'),
        ],
        default='exact'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['id']
    
    def __str__(self):
        return f"{self.product_name} - {self.quantity} x {self.unit_price}"


class InventoryItem(models.Model):
    """Inventory tracking for products."""
    product = models.OneToOneField(
        Product, 
        on_delete=models.CASCADE, 
        related_name='inventory'
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=0)
    unit = models.CharField(max_length=20, default="pcs")
    
    # Tracking
    last_restocked = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['product__name']
    
    def __str__(self):
        return f"{self.product.name} - {self.quantity} {self.unit}"
    
    def add_quantity(self, amount, source_receipt=None):
        """Add quantity to inventory from receipt."""
        self.quantity += Decimal(str(amount))
        self.last_restocked = timezone.now()
        self.save()
        
        # Create history record
        InventoryHistory.objects.create(
            inventory_item=self,
            change_type='purchase',
            quantity_change=amount,
            source_receipt=source_receipt,
            new_quantity=self.quantity
        )


class InventoryHistory(models.Model):
    """History of inventory changes."""
    inventory_item = models.ForeignKey(
        InventoryItem, 
        on_delete=models.CASCADE, 
        related_name='history'
    )
    
    change_type = models.CharField(
        max_length=20,
        choices=[
            ('purchase', 'Purchase'),
            ('consumption', 'Consumption'), 
            ('adjustment', 'Manual Adjustment'),
            ('expired', 'Expired'),
        ]
    )
    
    quantity_change = models.DecimalField(max_digits=10, decimal_places=3)
    new_quantity = models.DecimalField(max_digits=10, decimal_places=3)
    source_receipt = models.ForeignKey(
        Receipt, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.inventory_item.product.name} - {self.change_type} - {self.quantity_change}"
