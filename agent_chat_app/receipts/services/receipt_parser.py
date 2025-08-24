"""
Receipt parsing service using LLM for structured data extraction.
Implements the parser described in system-paragonow-guide.md
"""

import json
import logging
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
import requests

logger = logging.getLogger(__name__)


@dataclass
class ParsedProduct:
    """Parsed product from receipt."""
    name: str
    quantity: float
    price: float
    total_price: Optional[float] = None
    unit: Optional[str] = None
    
    def __post_init__(self):
        if self.total_price is None:
            self.total_price = self.quantity * self.price


@dataclass 
class ExtractedReceipt:
    """Complete extracted receipt data."""
    store_name: str
    date: Optional[str]
    total: float
    currency: str = "PLN"
    products: List[ParsedProduct] = None
    raw_data: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.products is None:
            self.products = []


class ReceiptParser:
    """LLM-based receipt parser for structured data extraction."""
    
    def __init__(self, model_name: str = "llama3.2", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
        self.api_url = f"{base_url}/api/generate"
    
    def parse(self, receipt_text: str) -> Dict[str, Any]:
        """
        Parse receipt text into structured data using LLM.
        
        Args:
            receipt_text: Raw OCR text from receipt
            
        Returns:
            Dictionary with structured receipt data
        """
        try:
            logger.info("Starting LLM-based receipt parsing")
            
            # Create structured prompt for the LLM
            prompt = self._create_parsing_prompt(receipt_text)
            
            # Call LLM API
            response = self._call_llm_api(prompt)
            
            # Parse LLM response
            parsed_data = self._parse_llm_response(response)
            
            # Validate and clean data
            validated_data = self._validate_parsed_data(parsed_data)
            
            logger.info(f"Successfully parsed receipt with {len(validated_data.get('products', []))} products")
            return asdict(validated_data)
            
        except Exception as e:
            logger.error(f"Receipt parsing failed: {e}")
            raise
    
    def _create_parsing_prompt(self, receipt_text: str) -> str:
        """Create structured prompt for LLM parsing."""
        prompt = f"""
Jesteś ekspertem w analizowaniu paragonów. Twoim zadaniem jest wyekstraktowanie strukturalnych danych z tekstu paragonu.

TEKST PARAGONU:
{receipt_text}

INSTRUKCJE:
1. Wyekstraktuj nazwę sklepu
2. Znajdź datę zakupu (format: YYYY-MM-DD)
3. Znajdź sumę całkowitą
4. Wyekstraktuj wszystkie produkty z cenami i ilościami
5. Określ walutę (domyślnie PLN)

WYMAGANY FORMAT ODPOWIEDZI (JSON):
{{
  "store_name": "nazwa sklepu",
  "date": "YYYY-MM-DD lub null",
  "total": liczba,
  "currency": "PLN",
  "products": [
    {{
      "name": "nazwa produktu",
      "quantity": liczba,
      "price": cena_jednostkowa,
      "total_price": cena_całkowita_za_produkt,
      "unit": "szt" 
    }}
  ]
}}

WAŻNE ZASADY:
- Nazwy produktów powinny być czyste (bez wag, kodów, cen)
- Jeśli nie możesz znaleźć jakiejś informacji, użyj null
- Ceny jako liczby dziesiętne
- Ilości jako liczby (domyślnie 1.0 jeśli nie podane)
- Waluta domyślnie "PLN"
- Odpowiadaj TYLKO w formacie JSON, bez dodatkowych komentarzy

JSON:"""

        return prompt
    
    def _call_llm_api(self, prompt: str) -> str:
        """Call Ollama LLM API."""
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "max_tokens": 2000
                }
            }
            
            response = requests.post(
                self.api_url,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            return result.get('response', '')
            
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM API call failed: {e}")
            raise RuntimeError(f"Failed to connect to LLM API: {e}")
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM JSON response."""
        try:
            # Clean response - remove any non-JSON content
            response = response.strip()
            
            # Find JSON block
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
            else:
                json_str = response
            
            # Parse JSON
            parsed = json.loads(json_str)
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Raw response: {response}")
            
            # Fallback: try to extract basic information using regex
            return self._fallback_parsing(response)
    
    def _fallback_parsing(self, text: str) -> Dict[str, Any]:
        """Fallback parsing using regex patterns."""
        logger.warning("Using fallback regex parsing")
        
        # Basic patterns for Polish receipts
        store_patterns = [
            r'(?i)(biedronka|kaufland|carrefour|tesco|auchan|lidl|żabka)',
            r'(?i)([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\s]+(?:sp\.|s\.a\.|spółka))',
        ]
        
        total_patterns = [
            r'(?i)(?:suma|razem|total|do zapłaty)[\s:]*(\d+[,.]?\d*)',
            r'(?i)(\d+[,.]?\d*)\s*(?:pln|zł)',
        ]
        
        # Try to extract store name
        store_name = "Unknown Store"
        for pattern in store_patterns:
            match = re.search(pattern, text)
            if match:
                store_name = match.group(1).strip().title()
                break
        
        # Try to extract total
        total = 0.0
        for pattern in total_patterns:
            match = re.search(pattern, text)
            if match:
                total_str = match.group(1).replace(',', '.')
                try:
                    total = float(total_str)
                    break
                except ValueError:
                    continue
        
        return {
            "store_name": store_name,
            "date": None,
            "total": total,
            "currency": "PLN",
            "products": []
        }
    
    def _validate_parsed_data(self, data: Dict[str, Any]) -> ExtractedReceipt:
        """Validate and clean parsed data."""
        # Ensure required fields
        store_name = data.get('store_name', 'Unknown Store')
        if not store_name or store_name.lower() in ['null', 'none', '']:
            store_name = 'Unknown Store'
        
        # Parse date
        date_str = data.get('date')
        if date_str and date_str.lower() not in ['null', 'none']:
            # Validate date format
            try:
                datetime.fromisoformat(date_str)
            except (ValueError, TypeError):
                date_str = None
        else:
            date_str = None
        
        # Validate total
        total = data.get('total', 0.0)
        if isinstance(total, str):
            try:
                total = float(total.replace(',', '.'))
            except (ValueError, AttributeError):
                total = 0.0
        
        # Validate currency
        currency = data.get('currency', 'PLN')
        if not currency or currency.lower() in ['null', 'none']:
            currency = 'PLN'
        
        # Parse products
        products = []
        raw_products = data.get('products', [])
        
        for item in raw_products:
            if not isinstance(item, dict):
                continue
                
            try:
                name = item.get('name', '').strip()
                if not name:
                    continue
                
                quantity = float(item.get('quantity', 1.0))
                price = float(str(item.get('price', 0.0)).replace(',', '.'))
                total_price = item.get('total_price')
                
                if total_price:
                    total_price = float(str(total_price).replace(',', '.'))
                else:
                    total_price = quantity * price
                
                unit = item.get('unit', 'szt')
                
                product = ParsedProduct(
                    name=name,
                    quantity=quantity,
                    price=price,
                    total_price=total_price,
                    unit=unit
                )
                
                products.append(product)
                
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping invalid product: {item}, error: {e}")
                continue
        
        return ExtractedReceipt(
            store_name=store_name,
            date=date_str,
            total=total,
            currency=currency,
            products=products,
            raw_data=data
        )


class MistralReceiptParser(ReceiptParser):
    """Alternative parser using Mistral API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api.mistral.ai/v1/chat/completions"
    
    def _call_llm_api(self, prompt: str) -> str:
        """Call Mistral API."""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "mistral-tiny",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 2000
            }
            
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            return result['choices'][0]['message']['content']
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Mistral API call failed: {e}")
            raise RuntimeError(f"Failed to connect to Mistral API: {e}")


# Service factory function
def get_receipt_parser(parser_type: str = "ollama") -> ReceiptParser:
    """
    Get receipt parser instance.
    
    Args:
        parser_type: Type of parser to use ("ollama" or "mistral")
        
    Returns:
        ReceiptParser instance
    """
    if parser_type == "mistral":
        # Get API key from environment or settings
        import os
        api_key = os.environ.get('MISTRAL_API_KEY')
        if not api_key:
            logger.warning("MISTRAL_API_KEY not found, falling back to Ollama")
            return ReceiptParser()
        return MistralReceiptParser(api_key)
    else:
        return ReceiptParser()


# Unified processor that combines OCR and parsing
class UnifiedReceiptProcessor:
    """
    Unified processor that combines OCR and parsing.
    Implements the UnifiedReceiptProcessor from system-paragonow-guide.md
    """
    
    def __init__(self, parser_type: str = "ollama"):
        from .ocr_service import get_hybrid_ocr_service
        
        self.ocr_service = get_hybrid_ocr_service()
        self.receipt_parser = get_receipt_parser(parser_type)
    
    def process_receipt(self, file_path: str) -> ExtractedReceipt:
        """
        Process receipt file through complete OCR + parsing pipeline.
        
        Args:
            file_path: Path to receipt image file
            
        Returns:
            ExtractedReceipt object with structured data
        """
        logger.info(f"Starting unified processing for file: {file_path}")
        
        # Step 1: OCR
        try:
            import asyncio
            ocr_text = asyncio.run(self.ocr_service.extract_text_from_file(file_path))
            if not ocr_text.strip():
                raise ValueError("OCR returned empty text")
            
        except Exception as e:
            logger.error(f"OCR processing failed: {e}")
            raise ValueError(f"OCR processing failed: {e}")
        
        # Step 2: Parsing with LLM  
        try:
            parsed_data_dict = self.receipt_parser.parse(ocr_text)
            extracted_receipt = ExtractedReceipt(**parsed_data_dict)
            logger.info(f"Successfully processed receipt: {extracted_receipt.store_name}")
            return extracted_receipt
            
        except Exception as e:
            logger.error(f"Parsing failed: {e}")
            raise ValueError(f"Parsing failed: {e}")


# Factory function
def get_unified_processor(parser_type: str = "ollama") -> UnifiedReceiptProcessor:
    """Get unified receipt processor instance."""
    return UnifiedReceiptProcessor(parser_type)