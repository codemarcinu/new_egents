"""
API views for receipt processing.
Implements the receipt upload and status endpoints from system-paragonow-guide.md
"""

import logging
from decimal import Decimal
from django.db.models import Q, Count, Avg
from django.utils import timezone
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Receipt, Product, InventoryItem, ReceiptLineItem
from ..services.inventory_service import get_inventory_service
from .serializers import (
    ReceiptUploadSerializer, ReceiptSerializer, ReceiptStatusSerializer,
    ProductSerializer, InventoryItemSerializer, InventoryUpdateSerializer,
    ProductSearchSerializer, ReceiptStatsSerializer
)

logger = logging.getLogger(__name__)


class ReceiptUploadAPIView(APIView):
    """
    API endpoint for uploading receipt files.
    Implements ReceiptUploadAPIView from system-paragonow-guide.md
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Upload receipt file and start processing."""
        serializer = ReceiptUploadSerializer(data=request.data)
        
        if serializer.is_valid():
            receipt_file = serializer.validated_data['receipt_file']
            
            try:
                # Create Receipt object
                receipt = Receipt.objects.create(
                    user=request.user,
                    receipt_file=receipt_file,
                    status='pending',
                    processing_step='uploaded'
                )
                
                # Start asynchronous processing
                from ..tasks import process_receipt_task
                task = process_receipt_task.delay(receipt.id)
                receipt.task_id = task.id
                receipt.save()
                
                logger.info(f"Receipt {receipt.id} uploaded by user {request.user.id}, task {task.id} started")
                
                return Response({
                    'receipt_id': receipt.id,
                    'task_id': task.id,
                    'status': 'uploaded',
                    'message': 'Receipt uploaded successfully, processing started'
                }, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                logger.error(f"Failed to create receipt: {e}")
                return Response({
                    'error': 'Failed to process receipt upload'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ReceiptStatusAPIView(APIView):
    """
    API endpoint for checking receipt processing status.
    Implements ReceiptStatusAPIView from system-paragonow-guide.md
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, receipt_id):
        """Get receipt processing status."""
        try:
            receipt = Receipt.objects.get(id=receipt_id, user=request.user)
            serializer = ReceiptStatusSerializer(receipt)
            return Response(serializer.data)
            
        except Receipt.DoesNotExist:
            return Response({
                'error': 'Receipt not found'
            }, status=status.HTTP_404_NOT_FOUND)


class ReceiptDetailAPIView(generics.RetrieveAPIView):
    """Get detailed receipt information including line items."""
    serializer_class = ReceiptSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Receipt.objects.filter(user=self.request.user).prefetch_related(
            'line_items__matched_product__category'
        )


class ReceiptListAPIView(generics.ListAPIView):
    """List user's receipts with filtering and pagination."""
    serializer_class = ReceiptSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = Receipt.objects.filter(user=self.request.user).order_by('-created_at')
        
        # Apply filters
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        store_filter = self.request.query_params.get('store')
        if store_filter:
            queryset = queryset.filter(store_name__icontains=store_filter)
        
        return queryset


class ProductSearchAPIView(APIView):
    """Search for products."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Search products by name."""
        serializer = ProductSearchSerializer(data=request.data)
        
        if serializer.is_valid():
            query = serializer.validated_data['query']
            limit = serializer.validated_data['limit']
            
            # Search in product names and aliases
            products = Product.objects.filter(
                Q(name__icontains=query) |
                Q(brand__icontains=query) |
                Q(aliases__icontains=query),
                is_active=True
            ).distinct()[:limit]
            
            product_serializer = ProductSerializer(products, many=True)
            return Response(product_serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class InventoryListAPIView(generics.ListAPIView):
    """List inventory items."""
    serializer_class = InventoryItemSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = InventoryItem.objects.select_related('product').filter(
            product__is_active=True
        ).order_by('product__name')
        
        # Filter by low stock if requested
        low_stock_only = self.request.query_params.get('low_stock')
        if low_stock_only and low_stock_only.lower() == 'true':
            threshold = Decimal(self.request.query_params.get('threshold', '5.0'))
            queryset = queryset.filter(quantity__lte=threshold)
        
        return queryset


class InventoryUpdateAPIView(APIView):
    """Manually update inventory."""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Update inventory quantity for a product."""
        serializer = InventoryUpdateSerializer(data=request.data)
        
        if serializer.is_valid():
            product_id = serializer.validated_data['product_id']
            new_quantity = serializer.validated_data['quantity']
            notes = serializer.validated_data.get('notes', f'Manual update by user {request.user.username}')
            
            try:
                product = Product.objects.get(id=product_id)
                inventory_service = get_inventory_service()
                
                success = inventory_service.adjust_inventory(
                    product=product,
                    new_quantity=new_quantity,
                    notes=notes
                )
                
                if success:
                    # Return updated inventory item
                    inventory_item = InventoryItem.objects.get(product=product)
                    inventory_serializer = InventoryItemSerializer(inventory_item)
                    return Response(inventory_serializer.data)
                else:
                    return Response({
                        'error': 'Failed to update inventory'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
            except Product.DoesNotExist:
                return Response({
                    'error': 'Product not found'
                }, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                logger.error(f"Inventory update failed: {e}")
                return Response({
                    'error': 'Internal server error'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def receipt_stats_view(request):
    """Get receipt processing statistics for the user."""
    try:
        user_receipts = Receipt.objects.filter(user=request.user)
        
        stats = user_receipts.aggregate(
            total_receipts=Count('id'),
            processed_receipts=Count('id', filter=Q(status='completed')),
            pending_receipts=Count('id', filter=Q(status__in=['pending', 'processing'])),
            failed_receipts=Count('id', filter=Q(status='error'))
        )
        
        # Calculate success rate
        total = stats['total_receipts']
        if total > 0:
            stats['success_rate'] = (stats['processed_receipts'] / total) * 100
        else:
            stats['success_rate'] = 0.0
        
        # Calculate average processing time (for completed receipts)
        completed_receipts = user_receipts.filter(
            status='completed',
            processed_at__isnull=False
        )
        
        if completed_receipts.exists():
            avg_seconds = completed_receipts.extra(
                select={'processing_time': 'extract(epoch from (processed_at - created_at))'}
            ).aggregate(avg_time=Avg('processing_time'))['avg_time']
            
            stats['avg_processing_time'] = round(avg_seconds / 60, 2) if avg_seconds else 0.0
        else:
            stats['avg_processing_time'] = 0.0
        
        serializer = ReceiptStatsSerializer(stats)
        return Response(serializer.data)
        
    except Exception as e:
        logger.error(f"Failed to get receipt stats: {e}")
        return Response({
            'error': 'Failed to retrieve statistics'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inventory_summary_view(request):
    """Get inventory summary statistics."""
    try:
        inventory_service = get_inventory_service()
        summary = inventory_service.get_inventory_summary(user=request.user)
        
        return Response(summary)
        
    except Exception as e:
        logger.error(f"Failed to get inventory summary: {e}")
        return Response({
            'error': 'Failed to retrieve inventory summary'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def receipt_confirm_view(request, receipt_id):
    """Confirm and finalize receipt data with user edits."""
    try:
        receipt = Receipt.objects.get(id=receipt_id, user=request.user)
        
        # Only allow confirmation of receipts pending review
        if receipt.status != 'review_pending':
            return Response({
                'error': f'Cannot confirm receipt with status: {receipt.status}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        confirmed_data = request.data.get('confirmed_data')
        if not confirmed_data:
            return Response({
                'error': 'confirmed_data is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Clear existing line items
        receipt.line_items.all().delete()
        
        # Create new line items from confirmed data
        line_items_created = 0
        inventory_service = get_inventory_service()
        
        for item_data in confirmed_data.get('line_items', []):
            try:
                # Calculate discounted price if not provided
                unit_price = Decimal(str(item_data.get('unit_price', 0)))
                unit_discount = Decimal(str(item_data.get('unit_discount', 0)))
                quantity = Decimal(str(item_data.get('quantity', 1)))
                discounted_price = unit_price - unit_discount
                line_total = discounted_price * quantity
                
                # Create line item
                line_item = ReceiptLineItem.objects.create(
                    receipt=receipt,
                    product_name=item_data.get('product_name', ''),
                    quantity=quantity,
                    unit_price=unit_price,
                    unit_discount=unit_discount,
                    discounted_price=discounted_price,
                    line_total=line_total,
                    expiration_date=item_data.get('expiration_date'),
                    # TODO: Handle matched_product if provided
                    match_confidence=1.0,  # User confirmed
                    match_type='manual'
                )
                
                line_items_created += 1
                
                # Update inventory if product is matched
                if line_item.matched_product:
                    inventory_service.add_inventory_from_receipt_item(line_item)
                
            except Exception as e:
                logger.error(f"Failed to create line item: {item_data}, error: {e}")
                continue
        
        # Update receipt metadata from confirmed data
        if confirmed_data.get('store_name'):
            receipt.store_name = confirmed_data['store_name']
        
        if confirmed_data.get('purchased_at'):
            from django.utils.dateparse import parse_datetime
            receipt.purchased_at = parse_datetime(confirmed_data['purchased_at'])
        
        if confirmed_data.get('total'):
            receipt.total = Decimal(str(confirmed_data['total']))
        
        # Mark as completed
        receipt.mark_as_completed()
        
        logger.info(f"Receipt {receipt_id} confirmed by user with {line_items_created} line items")
        
        return Response({
            'message': 'Receipt confirmed successfully',
            'receipt_id': receipt.id,
            'line_items_created': line_items_created,
            'status': receipt.status
        })
        
    except Receipt.DoesNotExist:
        return Response({
            'error': 'Receipt not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Failed to confirm receipt {receipt_id}: {e}")
        return Response({
            'error': 'Failed to confirm receipt'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def receipt_delete_view(request, receipt_id):
    """Delete a receipt."""
    try:
        receipt = Receipt.objects.get(id=receipt_id, user=request.user)
        
        # Only allow deletion of failed or pending receipts
        if receipt.status in ['processing']:
            return Response({
                'error': 'Cannot delete receipt that is currently processing'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        receipt.delete()
        
        return Response({
            'message': 'Receipt deleted successfully'
        })
        
    except Receipt.DoesNotExist:
        return Response({
            'error': 'Receipt not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Failed to delete receipt {receipt_id}: {e}")
        return Response({
            'error': 'Failed to delete receipt'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)