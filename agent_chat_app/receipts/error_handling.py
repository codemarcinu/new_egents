"""
Enhanced error handling and recovery for receipt processing.
"""

import logging
import traceback
from enum import Enum
from typing import Dict, Optional, Any
from dataclasses import dataclass
from django.utils import timezone
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for better handling."""
    OCR_ERROR = "ocr_error"
    PARSING_ERROR = "parsing_error"
    MATCHING_ERROR = "matching_error"
    INVENTORY_ERROR = "inventory_error"
    FILE_ERROR = "file_error"
    NETWORK_ERROR = "network_error"
    VALIDATION_ERROR = "validation_error"
    TIMEOUT_ERROR = "timeout_error"
    MEMORY_ERROR = "memory_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ErrorInfo:
    """Structured error information."""
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    details: str
    recovery_actions: list
    retry_count: int = 0
    max_retries: int = 3
    recoverable: bool = True
    user_message: str = ""


class ReceiptProcessingErrorHandler:
    """Enhanced error handling for receipt processing."""
    
    def __init__(self):
        self.channel_layer = get_channel_layer()
        self.error_patterns = self._initialize_error_patterns()
    
    def _initialize_error_patterns(self) -> Dict[str, ErrorInfo]:
        """Initialize common error patterns and their handling strategies."""
        return {
            # OCR Errors
            "OCR returned empty text": ErrorInfo(
                category=ErrorCategory.OCR_ERROR,
                severity=ErrorSeverity.HIGH,
                message="OCR failed to extract text from image",
                details="The image may be corrupted, too blurry, or in an unsupported format",
                recovery_actions=["retry_with_different_ocr", "preprocess_image", "manual_review"],
                user_message="We couldn't read the text from your receipt image. Please try uploading a clearer image."
            ),
            "No OCR backends available": ErrorInfo(
                category=ErrorCategory.OCR_ERROR,
                severity=ErrorSeverity.CRITICAL,
                message="OCR service is unavailable",
                details="All OCR backends are down or misconfigured",
                recovery_actions=["check_ocr_services", "restart_services", "alert_admin"],
                recoverable=False,
                user_message="Our text recognition service is temporarily unavailable. Please try again later."
            ),
            
            # Parsing Errors
            "No products found in receipt text": ErrorInfo(
                category=ErrorCategory.PARSING_ERROR,
                severity=ErrorSeverity.MEDIUM,
                message="LLM parsing found no products",
                details="The receipt text may not contain recognizable product information",
                recovery_actions=["retry_parsing", "manual_review", "improve_prompt"],
                user_message="We couldn't find any products in your receipt. Please check if the image is clear and contains product information."
            ),
            "LLM service timeout": ErrorInfo(
                category=ErrorCategory.PARSING_ERROR,
                severity=ErrorSeverity.HIGH,
                message="LLM parsing service timed out",
                details="The AI service took too long to respond",
                recovery_actions=["retry_with_timeout", "use_backup_llm", "queue_for_later"],
                user_message="Processing is taking longer than expected. We'll continue working on your receipt and notify you when it's ready."
            ),
            
            # File Errors
            "File not found": ErrorInfo(
                category=ErrorCategory.FILE_ERROR,
                severity=ErrorSeverity.HIGH,
                message="Receipt file is missing",
                details="The uploaded file cannot be found on the server",
                recovery_actions=["check_file_system", "request_reupload"],
                recoverable=False,
                user_message="Your receipt file seems to be missing. Please try uploading it again."
            ),
            "Unsupported file format": ErrorInfo(
                category=ErrorCategory.FILE_ERROR,
                severity=ErrorSeverity.MEDIUM,
                message="Unsupported file format",
                details="The uploaded file format is not supported",
                recovery_actions=["convert_format", "request_different_format"],
                recoverable=False,
                user_message="Please upload your receipt as a JPG, PNG, or PDF file."
            ),
            
            # Memory Errors
            "MemoryError": ErrorInfo(
                category=ErrorCategory.MEMORY_ERROR,
                severity=ErrorSeverity.HIGH,
                message="Insufficient memory",
                details="The system ran out of memory during processing",
                recovery_actions=["reduce_image_size", "free_memory", "queue_for_later"],
                user_message="Your image is too large to process. Please try uploading a smaller version."
            ),
            
            # Network Errors
            "Connection timeout": ErrorInfo(
                category=ErrorCategory.NETWORK_ERROR,
                severity=ErrorSeverity.MEDIUM,
                message="Network connection timeout",
                details="External service connection timed out",
                recovery_actions=["retry_connection", "use_backup_service"],
                user_message="We're experiencing connectivity issues. We'll retry processing your receipt shortly."
            ),
        }
    
    def handle_error(self, receipt_id: int, error: Exception, context: Dict[str, Any] = None) -> ErrorInfo:
        """
        Handle an error during receipt processing.
        
        Args:
            receipt_id: ID of the receipt being processed
            error: The exception that occurred
            context: Additional context about the error
        
        Returns:
            ErrorInfo object with handling strategy
        """
        error_str = str(error)
        error_type = type(error).__name__
        
        logger.error(
            f"Receipt {receipt_id} processing error: {error_type}: {error_str}",
            extra={
                'receipt_id': receipt_id,
                'error_type': error_type,
                'error_message': error_str,
                'context': context,
                'traceback': traceback.format_exc()
            }
        )
        
        # Find matching error pattern
        error_info = self._classify_error(error_str, error_type, context)
        
        # Execute recovery actions
        self._execute_recovery_actions(receipt_id, error_info, context)
        
        # Notify user if needed
        if error_info.user_message:
            self._notify_user(receipt_id, error_info)
        
        # Alert admins for critical errors
        if error_info.severity == ErrorSeverity.CRITICAL:
            self._alert_admin(receipt_id, error_info, error)
        
        return error_info
    
    def _classify_error(self, error_str: str, error_type: str, context: Dict[str, Any] = None) -> ErrorInfo:
        """Classify error and return appropriate handling strategy."""
        
        # Check for exact matches first
        for pattern, error_info in self.error_patterns.items():
            if pattern.lower() in error_str.lower():
                return error_info
        
        # Check for error type patterns
        if error_type == "MemoryError":
            return self.error_patterns.get("MemoryError", self._get_default_error_info(error_type))
        
        if "timeout" in error_str.lower():
            return ErrorInfo(
                category=ErrorCategory.TIMEOUT_ERROR,
                severity=ErrorSeverity.MEDIUM,
                message="Operation timed out",
                details=error_str,
                recovery_actions=["retry_with_longer_timeout", "queue_for_later"],
                user_message="Processing is taking longer than expected. We'll continue working on your receipt."
            )
        
        if "connection" in error_str.lower() or "network" in error_str.lower():
            return ErrorInfo(
                category=ErrorCategory.NETWORK_ERROR,
                severity=ErrorSeverity.MEDIUM,
                message="Network connection error",
                details=error_str,
                recovery_actions=["retry_connection", "check_network"],
                user_message="We're experiencing connectivity issues. Please try again in a few minutes."
            )
        
        # Default unknown error
        return self._get_default_error_info(error_type, error_str)
    
    def _get_default_error_info(self, error_type: str, error_str: str = "") -> ErrorInfo:
        """Get default error info for unknown errors."""
        return ErrorInfo(
            category=ErrorCategory.UNKNOWN_ERROR,
            severity=ErrorSeverity.MEDIUM,
            message=f"Unexpected error: {error_type}",
            details=error_str,
            recovery_actions=["log_error", "manual_review"],
            user_message="We encountered an unexpected issue while processing your receipt. Our team has been notified."
        )
    
    def _execute_recovery_actions(self, receipt_id: int, error_info: ErrorInfo, context: Dict[str, Any] = None):
        """Execute recovery actions for the error."""
        logger.info(f"Executing recovery actions for receipt {receipt_id}: {error_info.recovery_actions}")
        
        for action in error_info.recovery_actions:
            try:
                if action == "retry_with_different_ocr":
                    self._schedule_ocr_retry(receipt_id)
                elif action == "preprocess_image":
                    self._schedule_image_preprocessing(receipt_id)
                elif action == "manual_review":
                    self._queue_for_manual_review(receipt_id)
                elif action == "check_ocr_services":
                    self._check_ocr_services()
                elif action == "alert_admin":
                    # Already handled in handle_error
                    pass
                elif action == "log_error":
                    # Already logged
                    pass
                else:
                    logger.warning(f"Unknown recovery action: {action}")
                    
            except Exception as e:
                logger.error(f"Failed to execute recovery action {action}: {e}")
    
    def _schedule_ocr_retry(self, receipt_id: int):
        """Schedule receipt for OCR retry with different backend."""
        from .tasks import retry_ocr_task
        logger.info(f"Scheduling OCR retry for receipt {receipt_id}")
        retry_ocr_task.apply_async(args=[receipt_id], countdown=60)
    
    def _schedule_image_preprocessing(self, receipt_id: int):
        """Schedule receipt for image preprocessing."""
        logger.info(f"Scheduling image preprocessing for receipt {receipt_id}")
        # Implementation would depend on your image processing pipeline
    
    def _queue_for_manual_review(self, receipt_id: int):
        """Queue receipt for manual review."""
        from .models import Receipt
        try:
            receipt = Receipt.objects.get(id=receipt_id)
            receipt.status = 'manual_review'
            receipt.processing_step = 'awaiting_manual_review'
            receipt.error_message = "Queued for manual review due to processing errors"
            receipt.save()
            logger.info(f"Receipt {receipt_id} queued for manual review")
        except Receipt.DoesNotExist:
            logger.error(f"Receipt {receipt_id} not found for manual review queueing")
    
    def _check_ocr_services(self):
        """Check OCR service availability."""
        logger.info("Checking OCR service availability")
        # Implementation would check each OCR backend
    
    async def _notify_user(self, receipt_id: int, error_info: ErrorInfo):
        """Notify user about the error."""
        if not self.channel_layer:
            return
        
        try:
            await self.channel_layer.group_send(
                f'receipt_{receipt_id}',
                {
                    'type': 'receipt_status_update',
                    'receipt_id': receipt_id,
                    'status': 'error',
                    'processing_step': 'error_handling',
                    'progress_percentage': 0,
                    'message': error_info.user_message
                }
            )
        except Exception as e:
            logger.error(f"Failed to notify user about error: {e}")
    
    async def _alert_admin(self, receipt_id: int, error_info: ErrorInfo, original_error: Exception):
        """Send alert to administrators for critical errors."""
        if not self.channel_layer:
            return
        
        try:
            await self.channel_layer.group_send(
                'admin_notifications',
                {
                    'type': 'system_notification',
                    'title': 'Critical Receipt Processing Error',
                    'message': f'Receipt {receipt_id}: {error_info.message}',
                    'level': 'error',
                    'timestamp': timezone.now().isoformat(),
                    'details': {
                        'receipt_id': receipt_id,
                        'error_category': error_info.category.value,
                        'error_details': error_info.details,
                        'original_error': str(original_error)
                    }
                }
            )
        except Exception as e:
            logger.error(f"Failed to alert admin: {e}")


# Global error handler instance
error_handler = ReceiptProcessingErrorHandler()


def handle_receipt_error(receipt_id: int, error: Exception, context: Dict[str, Any] = None) -> ErrorInfo:
    """Convenience function to handle receipt processing errors."""
    return error_handler.handle_error(receipt_id, error, context)