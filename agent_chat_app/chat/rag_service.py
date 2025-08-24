import chromadb
from chromadb.config import Settings
import os
import logging
from typing import List, Dict, Any, Tuple
from django.conf import settings
from .embeddings import EmbeddingService
from .models import DocumentChunk, Document
import numpy as np

# Disable ChromaDB telemetry completely
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_CLIENT_AUTH_PROVIDER"] = ""
os.environ["CHROMA_SERVER_AUTHN_PROVIDER"] = ""

# Import telemetry fix
from . import chromadb_fix

logger = logging.getLogger(__name__)

class RAGService:
    """RAG service using ChromaDB for vector storage and retrieval"""
    
    def __init__(self, collection_name: str = "documents"):
        self.collection_name = collection_name
        self.embedding_service = EmbeddingService()
        
        # Initialize ChromaDB with persistent storage
        db_path = os.path.join(settings.BASE_DIR, "chromadb")
        os.makedirs(db_path, exist_ok=True)
        
        try:
            self.client = chromadb.PersistentClient(
                path=db_path,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                    is_persistent=True,
                    telemetry_endpoint="",  # Disable telemetry endpoint
                )
            )
        except Exception as telemetry_error:
            # Fallback: ignore telemetry errors
            logger.warning(f"ChromaDB telemetry initialization warning: {telemetry_error}")
            self.client = chromadb.PersistentClient(
                path=db_path,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                    is_persistent=True
                )
            )
        
        # Get or create collection
        try:
            self.collection = self.client.get_collection(name=collection_name)
        except Exception:  # Handle both ValueError and InvalidCollectionException
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"description": "Document chunks for RAG"}
            )
    
    def add_document_chunks(self, document_id: int, chunks: List[Dict[str, Any]]) -> bool:
        """Add document chunks to ChromaDB and update Django models"""
        try:
            document = Document.objects.get(id=document_id)
            
            # Prepare data for ChromaDB
            chunk_ids = []
            chunk_embeddings = []
            chunk_metadatas = []
            chunk_documents = []
            
            # Process each chunk
            for i, chunk_data in enumerate(chunks):
                content = chunk_data['content']
                metadata = chunk_data['metadata']
                
                # Generate embedding
                embedding = self.embedding_service.generate_embedding(content)
                if not embedding:
                    logger.warning(f"Failed to generate embedding for chunk {i}")
                    continue
                
                # Create Django DocumentChunk
                chunk_obj = DocumentChunk.objects.create(
                    document=document,
                    content=content,
                    chunk_index=i,
                    total_chunks=len(chunks)
                )
                chunk_obj.set_embedding(embedding)
                chunk_obj.save()
                
                # Prepare for ChromaDB
                chunk_id = f"doc_{document_id}_chunk_{i}"
                chunk_ids.append(chunk_id)
                chunk_embeddings.append(embedding)
                chunk_metadatas.append({
                    'document_id': document_id,
                    'filename': metadata.get('filename', ''),
                    'file_type': metadata.get('file_type', ''),
                    'chunk_index': i,
                    'django_chunk_id': chunk_obj.id
                })
                chunk_documents.append(content)
            
            if chunk_ids:
                # Add to ChromaDB
                self.collection.add(
                    ids=chunk_ids,
                    embeddings=chunk_embeddings,
                    metadatas=chunk_metadatas,
                    documents=chunk_documents
                )
                
                # Mark document as processed
                document.mark_as_completed(chunk_count=len(chunk_ids))
                
                logger.info(f"Added {len(chunk_ids)} chunks for document {document.filename}")
                return True
                
        except Exception as e:
            logger.error(f"Error adding document chunks: {e}")
            return False
        
        return False
    
    def search_similar_chunks(self, query: str, n_results: int = 5, user_id: int = None) -> List[Dict[str, Any]]:
        """Search for similar document chunks"""
        try:
            # Generate query embedding
            query_embedding = self.embedding_service.generate_embedding(query)
            if not query_embedding:
                logger.warning("Failed to generate embedding for query")
                return []
            
            # Search in ChromaDB
            where_filter = {}
            if user_id:
                # Filter by user's documents
                user_doc_ids = list(Document.objects.filter(user_id=user_id).values_list('id', flat=True))
                if not user_doc_ids:
                    return []
                where_filter = {"document_id": {"$in": user_doc_ids}}
            
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_filter if where_filter else None
            )
            
            # Format results
            similar_chunks = []
            if results['ids'] and results['ids'][0]:
                for i, chunk_id in enumerate(results['ids'][0]):
                    similar_chunks.append({
                        'id': chunk_id,
                        'content': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': results['distances'][0][i] if results.get('distances') else 0.0
                    })
            
            return similar_chunks
            
        except Exception as e:
            logger.error(f"Error searching similar chunks: {e}")
            return []
    
    def generate_rag_context(self, query: str, user_id: int = None, max_chunks: int = 3) -> str:
        """Generate context from relevant document chunks for RAG"""
        similar_chunks = self.search_similar_chunks(query, n_results=max_chunks, user_id=user_id)
        
        if not similar_chunks:
            return ""
        
        context_parts = []
        context_parts.append("Based on the following information from your documents:")
        
        for i, chunk in enumerate(similar_chunks, 1):
            filename = chunk['metadata'].get('filename', 'Unknown')
            content = chunk['content']
            context_parts.append(f"\n[Document {i}: {filename}]")
            context_parts.append(content)
        
        context_parts.append("\nPlease answer the question based on this information:")
        
        return "\n".join(context_parts)
    
    def get_document_stats(self, user_id: int = None) -> Dict[str, int]:
        """Get statistics about stored documents"""
        try:
            if user_id:
                docs_count = Document.objects.filter(user_id=user_id, processing_status='completed').count()
                chunks_count = DocumentChunk.objects.filter(document__user_id=user_id).count()
            else:
                docs_count = Document.objects.filter(processing_status='completed').count()
                chunks_count = DocumentChunk.objects.count()
            
            # Get ChromaDB collection count
            collection_count = self.collection.count()
            
            return {
                'documents': docs_count,
                'chunks': chunks_count,
                'chromadb_items': collection_count
            }
        except Exception as e:
            logger.error(f"Error getting document stats: {e}")
            return {'documents': 0, 'chunks': 0, 'chromadb_items': 0}
    
    def delete_document(self, document_id: int) -> bool:
        """Delete document and its chunks from both Django and ChromaDB"""
        try:
            document = Document.objects.get(id=document_id)
            
            # Get chunk IDs for ChromaDB deletion
            chunk_ids = [f"doc_{document_id}_chunk_{chunk.chunk_index}" 
                        for chunk in document.chunks.all()]
            
            # Delete from ChromaDB
            if chunk_ids:
                self.collection.delete(ids=chunk_ids)
            
            # Delete from Django
            document.delete()  # This will cascade delete chunks
            
            logger.info(f"Deleted document {document.filename} and its chunks")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return False
    
    def remove_document(self, document_id: int) -> bool:
        """Remove document from ChromaDB collection (alias for delete_document)"""
        return self.delete_document(document_id)
    
    def get_collection_info(self) -> dict:
        """Get information about the ChromaDB collection"""
        try:
            if not hasattr(self, 'chroma_client') or self.chroma_client is None:
                self._init_chroma()
            
            collection = self.chroma_client.get_collection(name=self.collection_name)
            count = collection.count()
            return {
                'count': count,
                'collection_name': self.collection_name,
                'status': 'ok'
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {
                'count': 0,
                'collection_name': self.collection_name,
                'status': 'error',
                'error': str(e)
            }