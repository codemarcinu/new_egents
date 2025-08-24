"""
Celery tasks for asynchronous receipt processing.
Implements the process_receipt_task from system-paragonow-guide.md
"""

import asyncio
import logging
from decimal import Decimal
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_receipt_task(self, receipt_id):
    """
    Main receipt processing task.
    Implements the complete pipeline: OCR -> Parse -> Match -> Inventory
    """
    
    try:
        from .models import Receipt, ReceiptLineItem
        from .services.ocr_service import get_hybrid_ocr_service
        from .services.receipt_parser import get_receipt_parser
        from .services.product_matcher import get_product_matcher
        from .services.inventory_service import get_inventory_service, get_websocket_notifier
        from .services.receipt_parser import ParsedProduct
        
        logger.info(f"Starting receipt processing for receipt {receipt_id}")
        
        # Get receipt object
        try:
            receipt = Receipt.objects.get(id=receipt_id)
        except Receipt.DoesNotExist:
            logger.error(f"Receipt {receipt_id} not found")
            return {'status': 'failed', 'error': 'Receipt not found'}
        
        # Initialize services
        ocr_service = get_hybrid_ocr_service()
        receipt_parser = get_receipt_parser()
        product_matcher = get_product_matcher()
        inventory_service = get_inventory_service()
        notifier = get_websocket_notifier()
        
        # Step 1: OCR Processing
        logger.info(f"Starting OCR for receipt {receipt_id}")
        receipt.mark_as_processing('ocr_in_progress')
        notifier.notify_receipt_status_update(
            receipt_id, 'processing', 'ocr_in_progress',
            'Extracting text from receipt image...'
        )
        
        try:
            # Use adaptive OCR service with receipt tracking
            raw_text = asyncio.run(
                ocr_service.extract_text_from_file_with_receipt(receipt.receipt_file.path, receipt)
            )
            
            if not raw_text.strip():
                raise ValueError("OCR returned empty text")
                
            receipt.mark_ocr_done(raw_text)
            
            notifier.notify_receipt_status_update(
                receipt_id, 'processing', 'ocr_completed',
                'Text extraction completed successfully'
            )
            
            logger.info(f"OCR completed for receipt {receipt_id}")
            
        except Exception as e:
            logger.error(f"OCR failed for receipt {receipt_id}: {e}")
            receipt.mark_as_error(f"OCR processing failed: {str(e)}")
            return {'status': 'failed', 'error': f'OCR failed: {str(e)}'}
        
        # Step 2: LLM Parsing
        logger.info(f"Starting parsing for receipt {receipt_id}")
        receipt.mark_llm_processing()
        notifier.notify_receipt_status_update(
            receipt_id, 'processing', 'parsing_in_progress',
            'Parsing receipt data with AI...'
        )
        
        try:
            extracted_data = receipt_parser.parse(raw_text)
            receipt.mark_llm_done(extracted_data)
            
            notifier.notify_receipt_status_update(
                receipt_id, 'processing', 'parsing_completed',
                f'Found {len(extracted_data.get("products", []))} products'
            )
            
            logger.info(f"Parsing completed for receipt {receipt_id}")
            
        except Exception as e:
            logger.error(f"Parsing failed for receipt {receipt_id}: {e}")
            receipt.mark_as_error(f"Parsing failed: {str(e)}")
            return {'status': 'failed', 'error': f'Parsing failed: {str(e)}'}
        
        # Step 3: Product Matching
        logger.info(f"Starting product matching for receipt {receipt_id}")
        receipt.status = 'processing'
        receipt.processing_step = 'matching_in_progress'
        receipt.save()
        
        notifier.notify_receipt_status_update(
            receipt_id, 'processing', 'matching_in_progress',
            'Matching products in database...'
        )
        
        try:
            # Convert extracted data to ParsedProduct objects
            parsed_products = []
            for p in extracted_data.get('products', []):
                try:
                    parsed_product = ParsedProduct(
                        name=p.get('name', ''),
                        quantity=float(p.get('quantity', 1.0)),
                        price=float(p.get('price', 0.0)),
                        total_price=float(p.get('total_price', 0.0)) if p.get('total_price') else None,
                        unit=p.get('unit', 'szt')
                    )
                    parsed_products.append(parsed_product)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Skipping invalid product data: {p}, error: {e}")
                    continue
            
            if not parsed_products:
                raise ValueError("No valid products found in parsed data")
            
            # Batch match products
            match_results = product_matcher.batch_match_products(parsed_products)
            
            receipt.processing_step = 'matching_completed'
            receipt.save()
            
            notifier.notify_receipt_status_update(
                receipt_id, 'processing', 'matching_completed',
                f'Matched {len(match_results)} products'
            )
            
            logger.info(f"Product matching completed for receipt {receipt_id}")
            
        except Exception as e:
            logger.error(f"Product matching failed for receipt {receipt_id}: {e}")
            receipt.mark_as_error(f"Product matching failed: {str(e)}")
            return {'status': 'failed', 'error': f'Product matching failed: {str(e)}'}
        
        # Step 4: Create ReceiptLineItems
        logger.info(f"Creating line items for receipt {receipt_id}")
        
        try:
            for i, (parsed_product, match_result) in enumerate(zip(parsed_products, match_results)):
                ReceiptLineItem.objects.create(
                    receipt=receipt,
                    product_name=parsed_product.name,
                    quantity=Decimal(str(parsed_product.quantity)),
                    unit_price=Decimal(str(parsed_product.price)),
                    line_total=Decimal(str(parsed_product.total_price or (parsed_product.quantity * parsed_product.price))),
                    matched_product=match_result.product,
                    match_confidence=match_result.confidence,
                    match_type=match_result.match_type
                )
            
            logger.info(f"Created {len(parsed_products)} line items for receipt {receipt_id}")
            
        except Exception as e:
            logger.error(f"Failed to create line items for receipt {receipt_id}: {e}")
            receipt.mark_as_error(f"Failed to create line items: {str(e)}")
            return {'status': 'failed', 'error': f'Line item creation failed: {str(e)}'}
        
        # Step 5: Update Inventory
        logger.info(f"Updating inventory for receipt {receipt_id}")
        receipt.processing_step = 'finalizing_inventory'
        receipt.save()
        
        notifier.notify_receipt_status_update(
            receipt_id, 'processing', 'finalizing_inventory',
            'Updating inventory...'
        )
        
        try:
            inventory_updates = 0
            for line_item in receipt.line_items.all():
                if line_item.matched_product:
                    result = inventory_service.add_inventory_from_receipt_item(line_item)
                    if result:
                        inventory_updates += 1
            
            logger.info(f"Updated inventory for {inventory_updates} items from receipt {receipt_id}")
            
        except Exception as e:
            logger.error(f"Inventory update failed for receipt {receipt_id}: {e}")
            # Don't fail the entire process for inventory issues
            logger.warning("Continuing despite inventory update failure")
        
        # Step 6: Finalization
        logger.info(f"Finalizing receipt {receipt_id}")
        
        # Update receipt totals if not already set
        if not receipt.total and extracted_data.get('total'):
            receipt.total = Decimal(str(extracted_data['total']))
        
        if not receipt.store_name and extracted_data.get('store_name'):
            receipt.store_name = extracted_data['store_name']
        
        if not receipt.purchased_at and extracted_data.get('date'):
            try:
                from django.utils.dateparse import parse_date
                date_obj = parse_date(extracted_data['date'])
                if date_obj:
                    receipt.purchased_at = timezone.make_aware(
                        timezone.datetime.combine(date_obj, timezone.datetime.min.time())
                    )
            except Exception as e:
                logger.warning(f"Failed to parse date: {e}")
        
        # Set status to review_pending instead of completed
        receipt.status = 'review_pending'
        receipt.processing_step = 'review_pending'
        receipt.save()
        
        # Send review notification
        notifier.notify_receipt_status_update(
            receipt_id, 'review_pending', 'review_pending',
            'Receipt processing completed - ready for your review!'
        )
        
        logger.info(f"Receipt {receipt_id} processing completed successfully")
        
        return {
            'status': 'completed',
            'receipt_id': receipt_id,
            'products_processed': len(parsed_products),
            'inventory_updates': inventory_updates if 'inventory_updates' in locals() else 0
        }
        
    except Exception as e:
        logger.error(f"Receipt processing failed for {receipt_id}: {e}")
        
        # Try to mark receipt as failed
        try:
            from .models import Receipt
            receipt = Receipt.objects.get(id=receipt_id)
            receipt.mark_as_error(str(e))
            
            # Send failure notification
            from .services.inventory_service import get_websocket_notifier
            notifier = get_websocket_notifier()
            notifier.notify_receipt_status_update(
                receipt_id, 'error', 'failed',
                f'Processing failed: {str(e)}'
            )
            
        except Exception as mark_error_e:
            logger.error(f"Failed to mark receipt as failed: {mark_error_e}")
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying receipt processing for {receipt_id} (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60 * (2 ** self.request.retries))
        
        return {'status': 'failed', 'error': str(e)}


@shared_task
def cleanup_old_processed_images():
    """Clean up old processed images from OCR preprocessing."""
    import os
    import glob
    from django.conf import settings
    
    try:
        # Find processed images older than 1 day
        media_root = getattr(settings, 'MEDIA_ROOT', '/tmp')
        pattern = os.path.join(media_root, '**/*_processed.*')
        
        import time
        current_time = time.time()
        cleanup_count = 0
        
        for filepath in glob.glob(pattern, recursive=True):
            try:
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > 86400:  # 1 day in seconds
                    os.remove(filepath)
                    cleanup_count += 1
            except OSError:
                continue
        
        logger.info(f"Cleaned up {cleanup_count} old processed images")
        return {'cleaned_files': cleanup_count}
        
    except Exception as e:
        logger.error(f"Image cleanup failed: {e}")
        return {'error': str(e)}


@shared_task
def generate_inventory_report():
    """Generate periodic inventory report."""
    try:
        from .services.inventory_service import get_inventory_service
        from .models import InventoryItem
        
        inventory_service = get_inventory_service()
        summary = inventory_service.get_inventory_summary()
        low_stock = inventory_service.get_low_stock_products()
        
        logger.info(f"Inventory report generated: {summary}")
        logger.info(f"Low stock items: {low_stock.count()}")
        
        return {
            'summary': summary,
            'low_stock_count': low_stock.count(),
            'low_stock_products': [
                {'name': item.product.name, 'quantity': float(item.quantity)}
                for item in low_stock[:10]  # Top 10 low stock items
            ]
        }
        
    except Exception as e:
        logger.error(f"Inventory report generation failed: {e}")
        return {'error': str(e)}