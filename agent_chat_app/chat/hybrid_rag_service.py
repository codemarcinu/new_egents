import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import numpy as np
from .rag_service import RAGService
from .models import UserSettings
import requests
import json

logger = logging.getLogger(__name__)


class KnowledgeSource(Enum):
    """Sources of knowledge for responses"""
    BUILT_IN = "built_in"  # Agent's internal knowledge
    RAG = "rag"  # Retrieved from documents
    HYBRID = "hybrid"  # Combination of both
    UNKNOWN = "unknown"  # Cannot determine or insufficient info


@dataclass
class ConfidenceScore:
    """Confidence scoring for responses"""
    overall: float  # 0.0 - 1.0, overall confidence
    rag_relevance: float  # How relevant RAG results are
    knowledge_coverage: float  # How well the topic is covered
    source_reliability: float  # Reliability of information sources
    
    def __post_init__(self):
        # Ensure all scores are between 0.0 and 1.0
        self.overall = max(0.0, min(1.0, self.overall))
        self.rag_relevance = max(0.0, min(1.0, self.rag_relevance))
        self.knowledge_coverage = max(0.0, min(1.0, self.knowledge_coverage))
        self.source_reliability = max(0.0, min(1.0, self.source_reliability))


@dataclass
class ResponseMetadata:
    """Metadata about the response generation"""
    knowledge_source: KnowledgeSource
    confidence: ConfidenceScore
    rag_chunks_used: List[Dict[str, Any]]
    fallback_used: bool
    transparency_info: Dict[str, Any]


class HybridRAGService:
    """
    Enhanced RAG service implementing hybrid approach with confidence scoring
    and transparency features
    """
    
    def __init__(self, confidence_threshold: float = 0.7, max_rag_chunks: int = 3):
        self.rag_service = RAGService()
        self.confidence_threshold = confidence_threshold
        self.max_rag_chunks = max_rag_chunks
        
        # Knowledge domain keywords for determining when to use RAG
        self.specialized_domains = [
            'technical', 'documentation', 'code', 'api', 'specification',
            'manual', 'tutorial', 'guide', 'reference', 'implementation'
        ]
    
    def should_use_rag(self, query: str, user_id: int = None) -> Tuple[bool, float]:
        """
        Determine if RAG should be used based on query analysis
        Returns: (should_use, confidence_in_decision)
        """
        if not user_id:
            return False, 1.0
        
        query_lower = query.lower()
        
        # Check for specific document references
        doc_indicators = ['document', 'file', 'pdf', 'my notes', 'uploaded']
        has_doc_reference = any(indicator in query_lower for indicator in doc_indicators)
        
        # Check for specialized domain keywords
        has_specialized_terms = any(domain in query_lower for domain in self.specialized_domains)
        
        # Check if user has documents
        stats = self.rag_service.get_document_stats(user_id=user_id)
        has_documents = stats.get('documents', 0) > 0
        
        # Decision logic
        if has_doc_reference and has_documents:
            return True, 0.9
        elif has_specialized_terms and has_documents:
            return True, 0.7
        elif has_documents and len(query.split()) > 10:  # Complex queries
            return True, 0.6
        else:
            return False, 0.8
    
    def calculate_confidence_score(self, query: str, rag_results: List[Dict], 
                                 has_rag_context: bool) -> ConfidenceScore:
        """Calculate confidence score based on various factors"""
        
        # RAG relevance score
        rag_relevance = 0.0
        if rag_results:
            # Use average distance/similarity score
            distances = [chunk.get('distance', 1.0) for chunk in rag_results]
            avg_distance = sum(distances) / len(distances) if distances else 1.0
            # Convert distance to similarity (lower distance = higher relevance)
            rag_relevance = max(0.0, 1.0 - avg_distance)
        
        # Knowledge coverage - simple heuristic based on query complexity
        query_words = len(query.split())
        if query_words <= 5:
            knowledge_coverage = 0.8  # Simple queries usually well covered
        elif query_words <= 15:
            knowledge_coverage = 0.6  # Medium complexity
        else:
            knowledge_coverage = 0.4  # Complex queries harder to cover
        
        # Source reliability
        source_reliability = 0.9 if has_rag_context else 0.7
        
        # Overall confidence - weighted average
        if has_rag_context and rag_results:
            overall = (rag_relevance * 0.4 + knowledge_coverage * 0.3 + source_reliability * 0.3)
        else:
            overall = (knowledge_coverage * 0.6 + source_reliability * 0.4)
        
        return ConfidenceScore(
            overall=overall,
            rag_relevance=rag_relevance,
            knowledge_coverage=knowledge_coverage,
            source_reliability=source_reliability
        )
    
    def generate_transparency_info(self, knowledge_source: KnowledgeSource, 
                                 rag_chunks: List[Dict], confidence: ConfidenceScore) -> Dict[str, Any]:
        """Generate transparency information about response generation"""
        info = {
            'knowledge_source': knowledge_source.value,
            'confidence_level': 'high' if confidence.overall >= 0.8 else 'medium' if confidence.overall >= 0.6 else 'low',
            'sources_used': []
        }
        
        if knowledge_source in [KnowledgeSource.RAG, KnowledgeSource.HYBRID]:
            for chunk in rag_chunks:
                metadata = chunk.get('metadata', {})
                info['sources_used'].append({
                    'filename': metadata.get('filename', 'Unknown'),
                    'relevance': f"{chunk.get('distance', 1.0):.2f}",
                    'chunk_index': metadata.get('chunk_index', 0)
                })
        
        return info
    
    def format_response_with_transparency(self, response: str, metadata: ResponseMetadata) -> str:
        """Add transparency information to the response"""
        transparency_parts = []
        
        # Add source information
        if metadata.knowledge_source == KnowledgeSource.RAG:
            transparency_parts.append("📚 *Odpowiedź oparta na Twoich dokumentach*")
        elif metadata.knowledge_source == KnowledgeSource.HYBRID:
            transparency_parts.append("🔄 *Odpowiedź łączy wiedzę wbudowaną z Twoimi dokumentami*")
        elif metadata.knowledge_source == KnowledgeSource.BUILT_IN:
            transparency_parts.append("🧠 *Odpowiedź oparta na wiedzy wbudowanej*")
        
        # Add confidence indicator
        confidence_level = metadata.confidence.overall
        if confidence_level >= 0.8:
            transparency_parts.append("✅ *Wysoka pewność odpowiedzi*")
        elif confidence_level >= 0.6:
            transparency_parts.append("⚠️ *Średnia pewność odpowiedzi*")
        else:
            transparency_parts.append("❓ *Niska pewność odpowiedzi - mogę się mylić*")
        
        # Add document sources if used
        if metadata.rag_chunks_used:
            source_files = list(set(
                chunk['metadata'].get('filename', 'Unknown') 
                for chunk in metadata.rag_chunks_used
            ))
            if source_files:
                transparency_parts.append(f"📄 *Źródła: {', '.join(source_files)}*")
        
        # Add fallback indicator
        if metadata.fallback_used:
            transparency_parts.append("🔄 *Użyto strategii fallback*")
        
        # Combine response with transparency info
        if transparency_parts:
            transparency_section = "\n\n---\n" + "\n".join(transparency_parts)
            return response + transparency_section
        
        return response
    
    def handle_knowledge_uncertainty(self, query: str, confidence: ConfidenceScore, 
                                   rag_results: List[Dict]) -> Optional[str]:
        """Handle cases where knowledge is uncertain or insufficient"""
        
        if confidence.overall < 0.3:
            return (
                "Przepraszam, ale nie mam wystarczających informacji, aby odpowiedzieć "
                "na to pytanie z pewnością. Możesz:\n\n"
                "• Przesłać dodatkowe dokumenty związane z tym tematem\n"
                "• Zadać pytanie w inny sposób\n"
                "• Sprawdzić czy masz odpowiednie dokumenty w systemie"
            )
        
        if confidence.rag_relevance < 0.4 and rag_results:
            return (
                "Znalazłem informacje w Twoich dokumentach, ale nie wydają się "
                "bezpośrednio związane z pytaniem. Mogę odpowiedzieć na podstawie "
                "ogólnej wiedzy, ale zalecam sprawdzenie czy masz bardziej "
                "specyficzne dokumenty na ten temat."
            )
        
        return None
    
    def get_enhanced_response(self, prompt: str, model: str = None, user_id: int = None, 
                            custom_instruction: str = None, force_rag: bool = False, conversation_id: int = None) -> Tuple[str, ResponseMetadata]:
        """
        Get enhanced response using hybrid RAG approach with confidence scoring
        """
        try:
            # Determine if RAG should be used
            should_use_rag, decision_confidence = self.should_use_rag(prompt, user_id)
            use_rag = should_use_rag or force_rag
            
            # Initialize response metadata
            rag_chunks = []
            fallback_used = False
            knowledge_source = KnowledgeSource.BUILT_IN
            
            # Try RAG approach if determined necessary
            enhanced_prompt = prompt
            if use_rag and user_id:
                try:
                    rag_chunks = self.rag_service.search_similar_chunks(
                        prompt, n_results=self.max_rag_chunks, user_id=user_id
                    )
                    
                    if rag_chunks:
                        rag_context = self.rag_service.generate_rag_context(
                            prompt, user_id=user_id, max_chunks=self.max_rag_chunks
                        )
                        if rag_context:
                            enhanced_prompt = f"{rag_context}\n\nUser question: {prompt}"
                            knowledge_source = KnowledgeSource.HYBRID if not force_rag else KnowledgeSource.RAG
                            logger.info(f"Enhanced prompt with RAG context for user {user_id}")
                    
                except Exception as e:
                    logger.warning(f"RAG enhancement failed, using fallback: {e}")
                    fallback_used = True
            
            # Calculate confidence score
            confidence = self.calculate_confidence_score(prompt, rag_chunks, use_rag and bool(rag_chunks))
            
            # Check for knowledge uncertainty
            uncertainty_response = self.handle_knowledge_uncertainty(prompt, confidence, rag_chunks)
            if uncertainty_response:
                metadata = ResponseMetadata(
                    knowledge_source=KnowledgeSource.UNKNOWN,
                    confidence=confidence,
                    rag_chunks_used=rag_chunks,
                    fallback_used=fallback_used,
                    transparency_info=self.generate_transparency_info(KnowledgeSource.UNKNOWN, rag_chunks, confidence)
                )
                return uncertainty_response, metadata
            
            # Get response from language model
            from .services import OllamaService
            response = OllamaService.get_response(
                prompt=enhanced_prompt,
                model=model,
                user_id=user_id,
                use_rag=False,  # We've already handled RAG
                custom_instruction=custom_instruction,
                conversation_id=conversation_id
            )
            
            # Create response metadata
            transparency_info = self.generate_transparency_info(knowledge_source, rag_chunks, confidence)
            metadata = ResponseMetadata(
                knowledge_source=knowledge_source,
                confidence=confidence,
                rag_chunks_used=rag_chunks,
                fallback_used=fallback_used,
                transparency_info=transparency_info
            )
            
            return response, metadata
            
        except Exception as e:
            logger.error(f"Error in hybrid RAG response generation: {e}")
            # Fallback to basic response
            from .services import OllamaService
            response = OllamaService.get_response(
                prompt=prompt,
                model=model,
                user_id=user_id,
                use_rag=False,
                custom_instruction=custom_instruction,
                conversation_id=conversation_id
            )
            
            fallback_confidence = ConfidenceScore(
                overall=0.5, rag_relevance=0.0, knowledge_coverage=0.5, source_reliability=0.7
            )
            
            metadata = ResponseMetadata(
                knowledge_source=KnowledgeSource.BUILT_IN,
                confidence=fallback_confidence,
                rag_chunks_used=[],
                fallback_used=True,
                transparency_info={'knowledge_source': 'built_in', 'fallback_reason': str(e)}
            )
            
            return response, metadata