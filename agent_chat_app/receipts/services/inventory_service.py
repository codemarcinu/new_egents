"""
Inventory management service for receipt processing.
Handles inventory updates from receipt line items.
"""

import logging
from decimal import Decimal
from typing import Optional
from django.db import transaction

logger = logging.getLogger(__name__)


class InventoryService:
    """Service for managing inventory from receipt processing."""
    
    def add_inventory_from_receipt_item(self, receipt_line_item) -> Optional['InventoryItem']:
        """
        Add inventory quantity from a receipt line item.
        
        Args:
            receipt_line_item: ReceiptLineItem instance
            
        Returns:
            Updated or created InventoryItem
        """
        from ..models import InventoryItem
        
        if not receipt_line_item.matched_product:
            logger.warning(f"No matched product for line item: {receipt_line_item}")
            return None
        
        try:
            with transaction.atomic():
                # Get or create inventory item
                inventory_item, created = InventoryItem.objects.get_or_create(
                    product=receipt_line_item.matched_product,
                    defaults={
                        'quantity': 0,
                        'unit': 'szt'
                    }
                )
                
                # Add quantity from receipt
                quantity_to_add = receipt_line_item.quantity
                inventory_item.add_quantity(
                    amount=quantity_to_add,
                    source_receipt=receipt_line_item.receipt
                )
                
                logger.info(
                    f"Added {quantity_to_add} {inventory_item.unit} of "
                    f"{inventory_item.product.name} to inventory"
                )
                
                return inventory_item
                
        except Exception as e:
            logger.error(f"Failed to add inventory from receipt item {receipt_line_item.id}: {e}")
            return None
    
    def consume_inventory(self, product, quantity: Decimal, notes: str = "") -> bool:
        """
        Consume inventory for a product.
        
        Args:
            product: Product instance
            quantity: Quantity to consume
            notes: Optional notes
            
        Returns:
            True if successful, False otherwise
        """
        from ..models import InventoryItem, InventoryHistory
        
        try:
            with transaction.atomic():
                inventory_item = InventoryItem.objects.get(product=product)
                
                if inventory_item.quantity < quantity:
                    logger.warning(
                        f"Insufficient inventory for {product.name}: "
                        f"requested {quantity}, available {inventory_item.quantity}"
                    )
                    return False
                
                # Update inventory
                new_quantity = inventory_item.quantity - quantity
                inventory_item.quantity = new_quantity
                inventory_item.save()
                
                # Create history record
                InventoryHistory.objects.create(
                    inventory_item=inventory_item,
                    change_type='consumption',
                    quantity_change=-quantity,
                    new_quantity=new_quantity,
                    notes=notes
                )
                
                logger.info(f"Consumed {quantity} of {product.name}")
                return True
                
        except InventoryItem.DoesNotExist:
            logger.error(f"No inventory found for product: {product}")
            return False
        except Exception as e:
            logger.error(f"Failed to consume inventory: {e}")
            return False
    
    def adjust_inventory(self, product, new_quantity: Decimal, notes: str = "") -> bool:
        """
        Manually adjust inventory to a specific quantity.
        
        Args:
            product: Product instance
            new_quantity: New quantity to set
            notes: Reason for adjustment
            
        Returns:
            True if successful, False otherwise
        """
        from ..models import InventoryItem, InventoryHistory
        
        try:
            with transaction.atomic():
                inventory_item, created = InventoryItem.objects.get_or_create(
                    product=product,
                    defaults={
                        'quantity': 0,
                        'unit': 'szt'
                    }
                )
                
                old_quantity = inventory_item.quantity
                quantity_change = new_quantity - old_quantity
                
                inventory_item.quantity = new_quantity
                inventory_item.save()
                
                # Create history record
                InventoryHistory.objects.create(
                    inventory_item=inventory_item,
                    change_type='adjustment',
                    quantity_change=quantity_change,
                    new_quantity=new_quantity,
                    notes=notes
                )
                
                logger.info(
                    f"Adjusted inventory for {product.name}: "
                    f"{old_quantity} -> {new_quantity} (change: {quantity_change})"
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to adjust inventory: {e}")
            return False
    
    def get_low_stock_products(self, threshold: Decimal = Decimal('5.0')):
        """
        Get products with low stock.
        
        Args:
            threshold: Stock level threshold
            
        Returns:
            QuerySet of InventoryItem objects with low stock
        """
        from ..models import InventoryItem
        
        try:
            return InventoryItem.objects.filter(
                quantity__lte=threshold,
                product__is_active=True
            ).select_related('product')
        except Exception as e:
            logger.error(f"Failed to get low stock products: {e}")
            return InventoryItem.objects.none()
    
    def get_inventory_summary(self, user=None):
        """
        Get inventory summary statistics.
        
        Args:
            user: Optional user filter
            
        Returns:
            Dictionary with inventory statistics
        """
        from ..models import InventoryItem, Product
        from django.db.models import Sum, Count, Q
        
        try:
            # Base queryset
            inventory_qs = InventoryItem.objects.select_related('product')
            products_qs = Product.objects.filter(is_active=True)
            
            # Apply user filter if provided (could filter by receipts)
            if user:
                # This would require additional logic to filter by user's receipts/products
                pass
            
            # Calculate statistics
            total_products = products_qs.count()
            tracked_products = inventory_qs.count()
            total_items = inventory_qs.aggregate(
                total=Sum('quantity')
            )['total'] or 0
            
            low_stock_count = inventory_qs.filter(
                quantity__lte=5,
                product__is_active=True
            ).count()
            
            return {
                'total_products': total_products,
                'tracked_products': tracked_products,
                'total_items': total_items,
                'low_stock_count': low_stock_count,
                'coverage_percentage': (tracked_products / total_products * 100) if total_products > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get inventory summary: {e}")
            return {
                'total_products': 0,
                'tracked_products': 0,
                'total_items': 0,
                'low_stock_count': 0,
                'coverage_percentage': 0
            }


# Service factory function
def get_inventory_service() -> InventoryService:
    """Get inventory service instance."""
    return InventoryService()


class WebSocketNotifier:
    """Service for sending WebSocket notifications."""
    
    @staticmethod
    def notify_receipt_status_update(receipt_id, status, processing_step, message=""):
        """Send receipt status update via WebSocket."""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            if not channel_layer:
                logger.warning("No channel layer configured for WebSocket notifications")
                return
            
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
            
            logger.info(f"Sent WebSocket notification for receipt {receipt_id}: {status}")
            
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification: {e}")
    
    @staticmethod
    def notify_receipt_completed(receipt_id):
        """Send receipt completion notification."""
        WebSocketNotifier.notify_receipt_status_update(
            receipt_id=receipt_id,
            status="completed",
            processing_step="done",
            message="Receipt processing completed successfully"
        )


def calculate_progress_from_step(processing_step: str) -> int:
    """Calculate progress percentage from processing step."""
    step_progress = {
        "uploaded": 10,
        "ocr_in_progress": 25,
        "ocr_completed": 40,
        "parsing_in_progress": 55,
        "parsing_completed": 70,
        "matching_in_progress": 80,
        "matching_completed": 90,
        "finalizing_inventory": 95,
        "done": 100,
        "failed": 0,
        "review_pending": 85,
    }
    
    return step_progress.get(processing_step, 0)


# Factory function for notifier
def get_websocket_notifier() -> WebSocketNotifier:
    """Get WebSocket notifier instance."""
    return WebSocketNotifier()