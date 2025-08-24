import requests
import json
from typing import List
import logging

logger = logging.getLogger(__name__)

class EmbeddingService:
    """Service for generating embeddings using Ollama mxbai-embed-large model"""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.model = "mxbai-embed-large"
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text"""
        try:
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text
                },
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get("embedding", [])
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error generating embedding: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON response: {e}")
            return []
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        embeddings = []
        for text in texts:
            embedding = self.generate_embedding(text)
            embeddings.append(embedding)
        return embeddings