"""
Serializers for Receipt API endpoints.
"""

from rest_framework import serializers
from ..models import Receipt, ReceiptLineItem, Product, Category, InventoryItem


class ReceiptUploadSerializer(serializers.Serializer):
    """Serializer for receipt file upload."""
    receipt_file = serializers.FileField()
    
    def validate_receipt_file(self, value):
        """Validate uploaded file."""
        # Check file size (max 10MB)
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("File too large. Maximum size is 10MB.")
        
        # Check file type
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/bmp', 'image/tiff']
        if value.content_type.lower() not in allowed_types:
            raise serializers.ValidationError(
                "Invalid file type. Only JPEG, PNG, BMP, and TIFF images are allowed."
            )
        
        return value


class CategorySerializer(serializers.ModelSerializer):
    """Serializer for Category model."""
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'parent', 'is_active', 'created_at']


class ProductSerializer(serializers.ModelSerializer):
    """Serializer for Product model."""
    category = CategorySerializer(read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'brand', 'barcode', 'category',
            'aliases', 'is_active', 'created_at', 'updated_at'
        ]


class ReceiptLineItemSerializer(serializers.ModelSerializer):
    """Serializer for ReceiptLineItem model."""
    matched_product = ProductSerializer(read_only=True)
    
    class Meta:
        model = ReceiptLineItem
        fields = [
            'id', 'product_name', 'quantity', 'unit_price', 'line_total',
            'matched_product', 'match_confidence', 'match_type', 'created_at'
        ]


class ReceiptSerializer(serializers.ModelSerializer):
    """Serializer for Receipt model."""
    line_items = ReceiptLineItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Receipt
        fields = [
            'id', 'user', 'store_name', 'purchased_at', 'total', 'currency',
            'receipt_file', 'status', 'processing_step', 'error_message',
            'created_at', 'processed_at', 'line_items'
        ]
        read_only_fields = ['user', 'status', 'processing_step', 'error_message', 'created_at', 'processed_at']


class ReceiptStatusSerializer(serializers.ModelSerializer):
    """Lightweight serializer for receipt status updates."""
    progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = Receipt
        fields = [
            'id', 'status', 'processing_step', 'error_message',
            'progress_percentage', 'created_at'
        ]
    
    def get_progress_percentage(self, obj):
        """Calculate progress percentage based on processing step."""
        from ..services.inventory_service import calculate_progress_from_step
        return calculate_progress_from_step(obj.processing_step)


class InventoryItemSerializer(serializers.ModelSerializer):
    """Serializer for InventoryItem model."""
    product = ProductSerializer(read_only=True)
    
    class Meta:
        model = InventoryItem
        fields = [
            'id', 'product', 'quantity', 'unit', 'last_restocked',
            'created_at', 'updated_at'
        ]


class InventoryUpdateSerializer(serializers.Serializer):
    """Serializer for manual inventory updates."""
    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=3)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    
    def validate_product_id(self, value):
        """Validate that product exists."""
        try:
            Product.objects.get(id=value, is_active=True)
            return value
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or inactive.")


class ProductSearchSerializer(serializers.Serializer):
    """Serializer for product search queries."""
    query = serializers.CharField(max_length=200)
    limit = serializers.IntegerField(min_value=1, max_value=50, default=10)


class ReceiptStatsSerializer(serializers.Serializer):
    """Serializer for receipt processing statistics."""
    total_receipts = serializers.IntegerField()
    processed_receipts = serializers.IntegerField()
    pending_receipts = serializers.IntegerField()
    failed_receipts = serializers.IntegerField()
    success_rate = serializers.FloatField()
    avg_processing_time = serializers.FloatField()  # in minutes