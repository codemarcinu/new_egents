from django.contrib import admin
from .models import Category, Product, Receipt, ReceiptLineItem, InventoryItem, InventoryHistory


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'is_active', 'created_at']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'description']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'brand', 'category', 'is_active', 'created_at']
    list_filter = ['is_active', 'category', 'brand']
    search_fields = ['name', 'brand', 'barcode']
    readonly_fields = ['created_at', 'updated_at']


class ReceiptLineItemInline(admin.TabularInline):
    model = ReceiptLineItem
    extra = 0
    readonly_fields = ['created_at']


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'store_name', 'status', 'processing_step', 'total', 'created_at']
    list_filter = ['status', 'processing_step', 'currency', 'created_at']
    search_fields = ['store_name', 'user__username', 'error_message']
    readonly_fields = ['created_at', 'processed_at', 'task_id']
    inlines = [ReceiptLineItemInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'store_name', 'purchased_at', 'total', 'currency')
        }),
        ('File & Processing', {
            'fields': ('receipt_file', 'status', 'processing_step', 'task_id', 'error_message')
        }),
        ('OCR & Parsing Data', {
            'fields': ('raw_ocr_text', 'extracted_data', 'parsed_data'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'processed_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(ReceiptLineItem)
class ReceiptLineItemAdmin(admin.ModelAdmin):
    list_display = ['receipt', 'product_name', 'quantity', 'unit_price', 'matched_product', 'match_type', 'match_confidence']
    list_filter = ['match_type', 'created_at']
    search_fields = ['product_name', 'matched_product__name']


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ['product', 'quantity', 'unit', 'last_restocked', 'updated_at']
    list_filter = ['unit', 'last_restocked']
    search_fields = ['product__name', 'product__brand']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(InventoryHistory)
class InventoryHistoryAdmin(admin.ModelAdmin):
    list_display = ['inventory_item', 'change_type', 'quantity_change', 'new_quantity', 'created_at']
    list_filter = ['change_type', 'created_at']
    search_fields = ['inventory_item__product__name', 'notes']
    readonly_fields = ['created_at']
