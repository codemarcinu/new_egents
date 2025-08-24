import os
import logging
from typing import Optional

from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.utils import timezone

from .models import Document
from .document_processor import DocumentProcessor
from .rag_service import RAGService

User = get_user_model()
logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_document_task(self, document_id: int) -> Optional[dict]:
    """
    Asynchronously process uploaded document:
    1. Extract text content
    2. Create chunks
    3. Generate embeddings
    4. Store in vector database
    """
    try:
        document = Document.objects.get(id=document_id)
        logger.info(f"Processing document {document.filename} (ID: {document_id})")
        
        # Update document status
        document.mark_as_processing()
        
        # Get full file path
        file_path = document.file_path
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Process document based on file type
        processor = DocumentProcessor()
        
        try:
            # Process document using DocumentProcessor
            documents = processor.process_document(file_path, document.filename)
            
            if not documents:
                raise ValueError("No content extracted from document")
                
            logger.info(f"Created {len(documents)} chunks from {document.filename}")
            
            # Store chunks in RAG system
            rag_service = RAGService()
            success = rag_service.add_document_chunks(document.id, documents)
            
            if success:
                chunks_created = len(documents)
            else:
                raise ValueError("Failed to store document chunks in RAG system")
            
            # Mark document as processed
            document.mark_as_completed(chunk_count=chunks_created)
            
            logger.info(f"Successfully processed document {document.filename} with {chunks_created} chunks")
            
            # Calculate total content length
            total_content_length = sum(len(doc['content']) for doc in documents)
            
            return {
                'status': 'success',
                'document_id': document_id,
                'filename': document.filename,
                'chunks_created': chunks_created,
                'content_length': total_content_length
            }
            
        except Exception as processing_error:
            logger.error(f"Error processing document content: {processing_error}")
            raise
            
    except Document.DoesNotExist:
        logger.error(f"Document with ID {document_id} does not exist")
        return {
            'status': 'error',
            'error': f'Document with ID {document_id} not found'
        }
    
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {e}")
        
        # Retry the task if we haven't exceeded max retries
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying task in 60 seconds (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60, exc=e)
        
        # Mark document as failed if max retries exceeded
        try:
            document = Document.objects.get(id=document_id)
            document.mark_as_failed(error_message=str(e))
        except Document.DoesNotExist:
            pass
        
        return {
            'status': 'error',
            'document_id': document_id,
            'error': str(e),
            'retries_exhausted': True
        }


@shared_task
def delete_document_task(document_id: int, file_path: str) -> dict:
    """
    Asynchronously delete document and clean up related data
    """
    try:
        logger.info(f"Deleting document with ID {document_id}")
        
        # Remove from vector database
        rag_service = RAGService()
        rag_service.remove_document(document_id)
        
        # Remove physical file
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
        
        return {
            'status': 'success',
            'document_id': document_id,
            'message': 'Document deleted successfully'
        }
        
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {e}")
        return {
            'status': 'error',
            'document_id': document_id,
            'error': str(e)
        }


@shared_task
def cleanup_old_documents_task(days_old: int = 30) -> dict:
    """
    Clean up old documents and their associated data
    """
    try:
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=days_old)
        old_documents = Document.objects.filter(uploaded_at__lt=cutoff_date)
        
        deleted_count = 0
        rag_service = RAGService()
        
        for document in old_documents:
            try:
                # Remove from vector database
                rag_service.remove_document(document.id)
                
                # Remove file from storage
                if os.path.exists(document.file_path):
                    os.remove(document.file_path)
                
                # Remove document record
                document.delete()
                deleted_count += 1
                
            except Exception as e:
                logger.error(f"Error deleting document {document.id}: {e}")
                continue
        
        logger.info(f"Cleaned up {deleted_count} old documents")
        return {
            'status': 'success',
            'deleted_count': deleted_count
        }
        
    except Exception as e:
        logger.error(f"Error in cleanup task: {e}")
        return {
            'status': 'error',
            'error': str(e)
        }


@shared_task
def health_check_task() -> dict:
    """
    Health check task for monitoring
    """
    try:
        # Test database connection
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        # Test RAG service
        rag_service = RAGService()
        collection_info = rag_service.get_collection_info()
        
        return {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'database': 'ok',
            'rag_service': 'ok',
            'collection_count': collection_info.get('count', 0)
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e)
        }