import unittest
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from .hybrid_rag_service import (
    HybridRAGService, 
    KnowledgeSource, 
    ConfidenceScore, 
    ResponseMetadata
)
from .models import Document, DocumentChunk, UserSettings

User = get_user_model()


class TestConfidenceScore(unittest.TestCase):
    """Test ConfidenceScore dataclass"""
    
    def test_confidence_score_creation(self):
        confidence = ConfidenceScore(
            overall=0.8,
            rag_relevance=0.7,
            knowledge_coverage=0.9,
            source_reliability=0.8
        )
        
        self.assertEqual(confidence.overall, 0.8)
        self.assertEqual(confidence.rag_relevance, 0.7)
        self.assertEqual(confidence.knowledge_coverage, 0.9)
        self.assertEqual(confidence.source_reliability, 0.8)
    
    def test_confidence_score_bounds(self):
        # Test that values are clamped between 0.0 and 1.0
        confidence = ConfidenceScore(
            overall=1.5,  # Should be clamped to 1.0
            rag_relevance=-0.5,  # Should be clamped to 0.0
            knowledge_coverage=0.5,
            source_reliability=2.0  # Should be clamped to 1.0
        )
        
        self.assertEqual(confidence.overall, 1.0)
        self.assertEqual(confidence.rag_relevance, 0.0)
        self.assertEqual(confidence.knowledge_coverage, 0.5)
        self.assertEqual(confidence.source_reliability, 1.0)


class TestHybridRAGService(TestCase):
    """Test HybridRAGService functionality"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.hybrid_rag = HybridRAGService()
    
    def test_should_use_rag_no_user(self):
        # Should not use RAG when no user provided
        should_use, confidence = self.hybrid_rag.should_use_rag("test query")
        self.assertFalse(should_use)
        self.assertEqual(confidence, 1.0)
    
    def test_should_use_rag_document_reference(self):
        # Create test document
        Document.objects.create(
            user=self.user,
            filename='test.pdf',
            file_type='pdf',
            file_path='/tmp/test.pdf',
            file_size=1000,
            processed=True
        )
        
        # Should use RAG when document is referenced
        should_use, confidence = self.hybrid_rag.should_use_rag(
            "What does my document say about testing?", 
            user_id=self.user.id
        )
        self.assertTrue(should_use)
        self.assertGreater(confidence, 0.8)
    
    def test_should_use_rag_specialized_terms(self):
        # Create test document
        Document.objects.create(
            user=self.user,
            filename='api_docs.pdf',
            file_type='pdf',
            file_path='/tmp/api_docs.pdf',
            file_size=1000,
            processed=True
        )
        
        # Should use RAG for specialized technical queries
        should_use, confidence = self.hybrid_rag.should_use_rag(
            "How to implement the API specification?", 
            user_id=self.user.id
        )
        self.assertTrue(should_use)
        self.assertGreater(confidence, 0.6)
    
    def test_should_not_use_rag_no_documents(self):
        # Should not use RAG when user has no documents
        should_use, confidence = self.hybrid_rag.should_use_rag(
            "What's the weather like?", 
            user_id=self.user.id
        )
        self.assertFalse(should_use)
        self.assertGreater(confidence, 0.7)
    
    def test_calculate_confidence_score_with_rag(self):
        # Mock RAG results with good similarity
        rag_results = [
            {'distance': 0.2, 'content': 'test content 1'},
            {'distance': 0.3, 'content': 'test content 2'}
        ]
        
        confidence = self.hybrid_rag.calculate_confidence_score(
            "short query", rag_results, has_rag_context=True
        )
        
        self.assertIsInstance(confidence, ConfidenceScore)
        self.assertGreater(confidence.overall, 0.6)
        self.assertGreater(confidence.rag_relevance, 0.6)  # Good similarity (low distance)
    
    def test_calculate_confidence_score_without_rag(self):
        confidence = self.hybrid_rag.calculate_confidence_score(
            "simple question", [], has_rag_context=False
        )
        
        self.assertIsInstance(confidence, ConfidenceScore)
        self.assertEqual(confidence.rag_relevance, 0.0)
        self.assertEqual(confidence.source_reliability, 0.7)
    
    def test_generate_transparency_info(self):
        # Test with RAG chunks
        rag_chunks = [
            {
                'metadata': {'filename': 'test.pdf', 'chunk_index': 0},
                'distance': 0.25
            }
        ]
        
        confidence = ConfidenceScore(0.8, 0.7, 0.9, 0.8)
        
        info = self.hybrid_rag.generate_transparency_info(
            KnowledgeSource.RAG, rag_chunks, confidence
        )
        
        self.assertEqual(info['knowledge_source'], 'rag')
        self.assertEqual(info['confidence_level'], 'high')
        self.assertEqual(len(info['sources_used']), 1)
        self.assertEqual(info['sources_used'][0]['filename'], 'test.pdf')
    
    def test_handle_knowledge_uncertainty_low_confidence(self):
        low_confidence = ConfidenceScore(0.2, 0.1, 0.3, 0.2)
        
        uncertainty_response = self.hybrid_rag.handle_knowledge_uncertainty(
            "complex query", low_confidence, []
        )
        
        self.assertIsNotNone(uncertainty_response)
        self.assertIn("nie mam wystarczających informacji", uncertainty_response)
    
    def test_handle_knowledge_uncertainty_good_confidence(self):
        good_confidence = ConfidenceScore(0.8, 0.7, 0.9, 0.8)
        
        uncertainty_response = self.hybrid_rag.handle_knowledge_uncertainty(
            "simple query", good_confidence, []
        )
        
        self.assertIsNone(uncertainty_response)
    
    def test_format_response_with_transparency_rag(self):
        # Test transparency formatting for RAG response
        response = "This is the AI response."
        
        confidence = ConfidenceScore(0.8, 0.7, 0.9, 0.8)
        rag_chunks = [{'metadata': {'filename': 'test.pdf'}}]
        
        metadata = ResponseMetadata(
            knowledge_source=KnowledgeSource.RAG,
            confidence=confidence,
            rag_chunks_used=rag_chunks,
            fallback_used=False,
            transparency_info={}
        )
        
        formatted = self.hybrid_rag.format_response_with_transparency(response, metadata)
        
        self.assertIn("This is the AI response.", formatted)
        self.assertIn("📚 *Odpowiedź oparta na Twoich dokumentach*", formatted)
        self.assertIn("✅ *Wysoka pewność odpowiedzi*", formatted)
        self.assertIn("📄 *Źródła: test.pdf*", formatted)
    
    def test_format_response_with_transparency_built_in(self):
        # Test transparency formatting for built-in knowledge response
        response = "This is the AI response."
        
        confidence = ConfidenceScore(0.6, 0.0, 0.7, 0.7)
        
        metadata = ResponseMetadata(
            knowledge_source=KnowledgeSource.BUILT_IN,
            confidence=confidence,
            rag_chunks_used=[],
            fallback_used=False,
            transparency_info={}
        )
        
        formatted = self.hybrid_rag.format_response_with_transparency(response, metadata)
        
        self.assertIn("🧠 *Odpowiedź oparta na wiedzy wbudowanej*", formatted)
        self.assertIn("⚠️ *Średnia pewność odpowiedzi*", formatted)
    
    @patch('agent_chat_app.chat.hybrid_rag_service.OllamaService')
    @patch.object(HybridRAGService, 'should_use_rag')
    def test_get_enhanced_response_no_rag(self, mock_should_use_rag, mock_ollama):
        # Test response generation without RAG
        mock_should_use_rag.return_value = (False, 0.8)
        mock_ollama.get_response.return_value = "AI response without RAG"
        
        response, metadata = self.hybrid_rag.get_enhanced_response(
            "simple question", user_id=self.user.id
        )
        
        self.assertEqual(response, "AI response without RAG")
        self.assertEqual(metadata.knowledge_source, KnowledgeSource.BUILT_IN)
        self.assertEqual(len(metadata.rag_chunks_used), 0)
        self.assertFalse(metadata.fallback_used)
    
    @patch('agent_chat_app.chat.hybrid_rag_service.OllamaService')
    @patch.object(HybridRAGService, 'should_use_rag')
    def test_get_enhanced_response_with_rag(self, mock_should_use_rag, mock_ollama):
        # Create test document and chunk
        doc = Document.objects.create(
            user=self.user,
            filename='test.pdf',
            file_type='pdf',
            file_path='/tmp/test.pdf',
            file_size=1000,
            processed=True
        )
        
        # Mock RAG service methods
        mock_should_use_rag.return_value = (True, 0.9)
        
        with patch.object(self.hybrid_rag.rag_service, 'search_similar_chunks') as mock_search, \
             patch.object(self.hybrid_rag.rag_service, 'generate_rag_context') as mock_context:
            
            mock_search.return_value = [
                {
                    'id': 'test_chunk',
                    'content': 'test content',
                    'metadata': {'filename': 'test.pdf', 'chunk_index': 0},
                    'distance': 0.2
                }
            ]
            mock_context.return_value = "RAG context with test content"
            mock_ollama.get_response.return_value = "AI response with RAG"
            
            response, metadata = self.hybrid_rag.get_enhanced_response(
                "question about document", user_id=self.user.id
            )
            
            self.assertEqual(response, "AI response with RAG")
            self.assertEqual(metadata.knowledge_source, KnowledgeSource.HYBRID)
            self.assertEqual(len(metadata.rag_chunks_used), 1)
            self.assertFalse(metadata.fallback_used)
    
    @patch('agent_chat_app.chat.hybrid_rag_service.OllamaService')
    def test_get_enhanced_response_uncertainty_handling(self, mock_ollama):
        # Test uncertainty handling with very low confidence
        with patch.object(self.hybrid_rag, 'calculate_confidence_score') as mock_confidence, \
             patch.object(self.hybrid_rag, 'handle_knowledge_uncertainty') as mock_uncertainty:
            
            mock_confidence.return_value = ConfidenceScore(0.2, 0.1, 0.2, 0.3)
            mock_uncertainty.return_value = "Nie mam wystarczających informacji"
            
            response, metadata = self.hybrid_rag.get_enhanced_response(
                "very complex query", user_id=self.user.id
            )
            
            self.assertEqual(response, "Nie mam wystarczających informacji")
            self.assertEqual(metadata.knowledge_source, KnowledgeSource.UNKNOWN)


if __name__ == '__main__':
    unittest.main()