"""
WebSocket consumers for real-time receipt processing updates.
Implements the ReceiptProgressConsumer from system-paragonow-guide.md
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class ReceiptProgressConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for receipt processing progress updates.
    Implements ReceiptProgressConsumer from system-paragonow-guide.md
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.receipt_id = self.scope['url_route']['kwargs']['receipt_id']
        self.room_group_name = f'receipt_{self.receipt_id}'
        self.user = self.scope.get('user')
        
        # Check authentication
        if isinstance(self.user, AnonymousUser):
            logger.warning(f"Anonymous user attempted to connect to receipt {self.receipt_id}")
            await self.close()
            return
        
        # Verify user owns this receipt
        receipt_exists = await self.verify_receipt_ownership()
        if not receipt_exists:
            logger.warning(f"User {self.user.id} attempted to access receipt {self.receipt_id} without permission")
            await self.close()
            return
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send current status immediately after connection
        current_status = await self.get_current_receipt_status()
        if current_status:
            await self.send(text_data=json.dumps({
                'type': 'status_update',
                'receipt_id': self.receipt_id,
                **current_status
            }))
        
        logger.info(f"User {self.user.id} connected to receipt {self.receipt_id} progress")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        logger.info(f"User disconnected from receipt {self.receipt_id} progress (code: {close_code})")
    
    async def receive(self, text_data):
        """Handle messages from WebSocket."""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            if message_type == 'get_status':
                # Client requesting current status
                current_status = await self.get_current_receipt_status()
                if current_status:
                    await self.send(text_data=json.dumps({
                        'type': 'status_update',
                        'receipt_id': self.receipt_id,
                        **current_status
                    }))
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {text_data}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
    
    async def receipt_status_update(self, event):
        """Handle receipt status update messages from the group."""
        try:
            # Send message to WebSocket
            await self.send(text_data=json.dumps({
                'type': 'status_update',
                'receipt_id': event['receipt_id'],
                'status': event['status'],
                'processing_step': event['processing_step'],
                'progress_percentage': event['progress_percentage'],
                'message': event['message']
            }))
            
        except Exception as e:
            logger.error(f"Error sending status update: {e}")
    
    @database_sync_to_async
    def verify_receipt_ownership(self):
        """Verify that the current user owns the receipt."""
        try:
            from .models import Receipt
            Receipt.objects.get(id=self.receipt_id, user=self.user)
            return True
        except Receipt.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error verifying receipt ownership: {e}")
            return False
    
    @database_sync_to_async
    def get_current_receipt_status(self):
        """Get current receipt status from database."""
        try:
            from .models import Receipt
            from .services.inventory_service import calculate_progress_from_step
            
            receipt = Receipt.objects.get(id=self.receipt_id, user=self.user)
            
            return {
                'status': receipt.status,
                'processing_step': receipt.processing_step,
                'progress_percentage': calculate_progress_from_step(receipt.processing_step),
                'message': receipt.error_message if receipt.status == 'error' else '',
                'created_at': receipt.created_at.isoformat(),
                'processed_at': receipt.processed_at.isoformat() if receipt.processed_at else None
            }
            
        except Exception as e:
            logger.error(f"Error getting receipt status: {e}")
            return None


class InventoryNotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for inventory notifications (low stock alerts, etc.)."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = self.scope.get('user')
        
        # Check authentication
        if isinstance(self.user, AnonymousUser):
            await self.close()
            return
        
        # Join user-specific inventory group
        self.room_group_name = f'inventory_user_{self.user.id}'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"User {self.user.id} connected to inventory notifications")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        logger.info(f"User disconnected from inventory notifications (code: {close_code})")
    
    async def inventory_update(self, event):
        """Handle inventory update notifications."""
        await self.send(text_data=json.dumps({
            'type': 'inventory_update',
            'product_name': event['product_name'],
            'new_quantity': event['new_quantity'],
            'unit': event['unit'],
            'message': event['message']
        }))
    
    async def low_stock_alert(self, event):
        """Handle low stock alert notifications."""
        await self.send(text_data=json.dumps({
            'type': 'low_stock_alert',
            'product_name': event['product_name'],
            'current_quantity': event['current_quantity'],
            'threshold': event['threshold'],
            'message': event['message']
        }))


class GeneralNotificationConsumer(AsyncWebsocketConsumer):
    """General notifications consumer for system-wide updates."""
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = self.scope.get('user')
        
        logger.info(f"GeneralNotificationConsumer connect: user={self.user}, type={type(self.user)}")
        logger.info(f"Scope keys: {list(self.scope.keys())}")
        
        # Check authentication
        if isinstance(self.user, AnonymousUser):
            logger.warning("Anonymous user attempted to connect to general notifications")
            await self.close()
            return
        
        # Join user-specific notifications group
        self.room_group_name = f'notifications_user_{self.user.id}'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"User {self.user.id} connected to general notifications")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        
        logger.info(f"User disconnected from general notifications (code: {close_code})")
    
    async def system_notification(self, event):
        """Handle system notifications."""
        await self.send(text_data=json.dumps({
            'type': 'system_notification',
            'title': event['title'],
            'message': event['message'],
            'level': event.get('level', 'info'),  # info, warning, error, success
            'timestamp': event.get('timestamp')
        }))
    
    async def receipt_completed(self, event):
        """Handle receipt completion notifications."""
        await self.send(text_data=json.dumps({
            'type': 'receipt_completed',
            'receipt_id': event['receipt_id'],
            'store_name': event.get('store_name', 'Unknown'),
            'products_count': event.get('products_count', 0),
            'message': event.get('message', 'Receipt processing completed')
        }))


# Helper functions for sending notifications
async def send_inventory_notification(user_id, product_name, new_quantity, unit, message):
    """Send inventory update notification to user."""
    from channels.layers import get_channel_layer
    
    channel_layer = get_channel_layer()
    if channel_layer:
        await channel_layer.group_send(
            f'inventory_user_{user_id}',
            {
                'type': 'inventory_update',
                'product_name': product_name,
                'new_quantity': str(new_quantity),
                'unit': unit,
                'message': message
            }
        )


async def send_low_stock_alert(user_id, product_name, current_quantity, threshold):
    """Send low stock alert to user."""
    from channels.layers import get_channel_layer
    
    channel_layer = get_channel_layer()
    if channel_layer:
        await channel_layer.group_send(
            f'inventory_user_{user_id}',
            {
                'type': 'low_stock_alert',
                'product_name': product_name,
                'current_quantity': str(current_quantity),
                'threshold': str(threshold),
                'message': f'Low stock alert: {product_name} has only {current_quantity} items left'
            }
        )


async def send_system_notification(user_id, title, message, level='info'):
    """Send system notification to user."""
    from channels.layers import get_channel_layer
    import datetime
    
    channel_layer = get_channel_layer()
    if channel_layer:
        await channel_layer.group_send(
            f'notifications_user_{user_id}',
            {
                'type': 'system_notification',
                'title': title,
                'message': message,
                'level': level,
                'timestamp': datetime.datetime.now().isoformat()
            }
        )