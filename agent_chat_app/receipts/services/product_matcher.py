"""
Product matching service with fuzzy matching and automatic alias creation.
Implements the ProductMatcher described in system-paragonow-guide.md
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from django.db.models import Q
from fuzzywuzzy import fuzz, process

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of product matching."""
    product: 'Product'  # Will be resolved at runtime
    confidence: float
    match_type: str  # "exact", "alias", "fuzzy", "created"
    normalized_name: str = ""
    matched_alias: str = ""
    category_guess: Optional['Category'] = None


class ProductMatcher:
    """
    Intelligent product matching with fuzzy matching and alias learning.
    Implements the ProductMatcher from system-paragonow-guide.md
    """
    
    def __init__(self, fuzzy_match_threshold: float = 0.75, auto_create_products: bool = True):
        self.fuzzy_match_threshold = fuzzy_match_threshold
        self.auto_create_products = auto_create_products
    
    def match_product(self, parsed_product, all_parsed_products=None) -> MatchResult:
        """
        Match a single parsed product to existing products in database.
        
        Args:
            parsed_product: ParsedProduct object from receipt parsing
            all_parsed_products: Optional list of all products from same receipt (for context)
            
        Returns:
            MatchResult with matched or created product
        """
        from ..models import Product, Category
        
        normalized_name = self.normalize_product_name(parsed_product.name)
        logger.debug(f"Matching product: '{parsed_product.name}' -> '{normalized_name}'")
        
        # 1. Exact match by normalized name
        exact_match = self._find_exact_match(normalized_name)
        if exact_match:
            logger.debug(f"Found exact match: {exact_match}")
            return MatchResult(
                product=exact_match,
                confidence=1.0,
                match_type="exact",
                normalized_name=normalized_name
            )
        
        # 2. Alias match
        alias_match, matched_alias = self._find_alias_match(normalized_name)
        if alias_match:
            logger.debug(f"Found alias match: {alias_match} (alias: {matched_alias})")
            # Update alias usage statistics
            alias_match.add_alias(normalized_name)
            return MatchResult(
                product=alias_match,
                confidence=0.9,
                match_type="alias",
                normalized_name=normalized_name,
                matched_alias=matched_alias
            )
        
        # 3. Fuzzy match against product names
        fuzzy_match, similarity = self._find_fuzzy_match(normalized_name)
        if fuzzy_match and similarity >= self.fuzzy_match_threshold:
            logger.debug(f"Found fuzzy match: {fuzzy_match} (similarity: {similarity:.2f})")
            # Add as alias for future matching
            fuzzy_match.add_alias(normalized_name)
            return MatchResult(
                product=fuzzy_match,
                confidence=similarity,
                match_type="fuzzy",
                normalized_name=normalized_name
            )
        
        # 4. Create new "ghost" product if enabled
        if self.auto_create_products:
            ghost_product = self._create_ghost_product(parsed_product, normalized_name)
            logger.debug(f"Created ghost product: {ghost_product}")
            return MatchResult(
                product=ghost_product,
                confidence=0.5,
                match_type="created",
                normalized_name=normalized_name,
                category_guess=ghost_product.category
            )
        
        # If we can't create products, return None (should not happen in normal flow)
        raise ValueError(f"Could not match product: {parsed_product.name}")
    
    def batch_match_products(self, parsed_products: List) -> List[MatchResult]:
        """
        Match multiple products efficiently.
        
        Args:
            parsed_products: List of ParsedProduct objects
            
        Returns:
            List of MatchResult objects
        """
        logger.info(f"Batch matching {len(parsed_products)} products")
        
        results = []
        for parsed_product in parsed_products:
            try:
                result = self.match_product(parsed_product, parsed_products)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to match product {parsed_product.name}: {e}")
                # Create a fallback result
                from ..models import Product
                fallback_product = self._create_ghost_product(parsed_product, parsed_product.name)
                results.append(MatchResult(
                    product=fallback_product,
                    confidence=0.1,
                    match_type="created",
                    normalized_name=parsed_product.name
                ))
        
        logger.info(f"Batch matching completed: {len(results)} results")
        return results
    
    def normalize_product_name(self, name: str) -> str:
        """
        Normalize product name for better matching.
        Removes weights, volumes, brands, and other variations.
        """
        if not name:
            return ""
        
        normalized = name.lower().strip()
        
        # Remove weight/volume information
        weight_patterns = [
            r'\b\d+\s*(?:kg|g|gram|grams|kilogram|kilograms)\b',
            r'\b\d+\s*(?:l|litr|litry|litrów|ml|millilitr)\b',
            r'\b\d+(?:[.,]\d+)?\s*(?:kg|g|l|ml)\b',
            r'\b\d+\s*x\s*\d+\s*(?:g|ml|kg|l)\b',  # "2 x 500g" format
        ]
        
        for pattern in weight_patterns:
            normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)
        
        # Remove brand prefixes
        brand_patterns = [
            r'^(?:tesco|carrefour|biedronka|auchan|kaufland|lidl|żabka)\s+',
            r'^(?:organic|bio|eco|fresh)\s+',
            r'^(?:premium|deluxe|extra)\s+',
        ]
        
        for pattern in brand_patterns:
            normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)
        
        # Remove common modifiers
        modifiers = [
            r'\b(?:naturalny|naturalna|naturalne)\b',
            r'\b(?:świeży|świeża|świeże)\b',
            r'\b(?:mrożony|mrożona|mrożone)\b',
            r'\b(?:suszony|suszona|suszone)\b',
        ]
        
        for pattern in modifiers:
            normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)
        
        # Clean up extra spaces and punctuation
        normalized = re.sub(r'[^\w\s]', ' ', normalized)  # Replace punctuation with spaces
        normalized = re.sub(r'\s+', ' ', normalized)      # Collapse multiple spaces
        
        return normalized.strip()
    
    def _find_exact_match(self, normalized_name: str) -> Optional['Product']:
        """Find exact match by normalized name."""
        from ..models import Product
        
        try:
            # Try to find by normalized name (stored in name field)
            product = Product.objects.filter(
                name__iexact=normalized_name,
                is_active=True
            ).first()
            
            return product
        except Exception as e:
            logger.error(f"Error in exact match: {e}")
            return None
    
    def _find_alias_match(self, normalized_name: str) -> Tuple[Optional['Product'], str]:
        """Find match in product aliases."""
        from ..models import Product
        
        try:
            products = Product.objects.filter(is_active=True).exclude(aliases=[])
            
            for product in products:
                for alias_entry in product.aliases:
                    if isinstance(alias_entry, dict):
                        alias_name = alias_entry.get('name', '').lower()
                    else:
                        # Handle simple string aliases
                        alias_name = str(alias_entry).lower()
                    
                    if alias_name == normalized_name.lower():
                        return product, alias_name
            
            return None, ""
            
        except Exception as e:
            logger.error(f"Error in alias match: {e}")
            return None, ""
    
    def _find_fuzzy_match(self, normalized_name: str) -> Tuple[Optional['Product'], float]:
        """Find fuzzy match using string similarity."""
        from ..models import Product
        
        try:
            # Get all active products
            products = Product.objects.filter(is_active=True)
            
            if not products.exists():
                return None, 0.0
            
            # Prepare choices for fuzzy matching
            choices = []
            product_map = {}
            
            for product in products:
                normalized_product_name = self.normalize_product_name(product.name)
                choices.append(normalized_product_name)
                product_map[normalized_product_name] = product
            
            # Find best match
            if not choices:
                return None, 0.0
            
            # Use fuzzywuzzy to find best match
            best_match, score = process.extractOne(
                normalized_name, 
                choices, 
                scorer=fuzz.ratio
            )
            
            # Convert score to 0-1 range
            similarity = score / 100.0
            
            if similarity >= self.fuzzy_match_threshold:
                return product_map[best_match], similarity
            
            return None, similarity
            
        except Exception as e:
            logger.error(f"Error in fuzzy match: {e}")
            return None, 0.0
    
    def _create_ghost_product(self, parsed_product, normalized_name: str) -> 'Product':
        """Create a new 'ghost' product for unmatched items."""
        from ..models import Product, Category
        
        try:
            # Try to guess category based on product name
            category = self._guess_category(normalized_name)
            
            # Create new product
            product = Product.objects.create(
                name=normalized_name,
                brand="",
                category=category,
                is_active=False,  # Mark as ghost product
                aliases=[]
            )
            
            logger.info(f"Created ghost product: {product}")
            return product
            
        except Exception as e:
            logger.error(f"Failed to create ghost product: {e}")
            # Return a minimal product object (this might cause issues in production)
            return Product(
                name=normalized_name,
                brand="",
                is_active=False
            )
    
    def _guess_category(self, product_name: str) -> Optional['Category']:
        """Guess product category based on name keywords."""
        from ..models import Category
        
        # Category keywords mapping
        category_keywords = {
            'Warzywa i Owoce': [
                'jabłko', 'gruszka', 'banan', 'pomarańcza', 'cytryna',
                'ziemniaki', 'marchew', 'cebula', 'czosnek', 'pomidor',
                'ogórek', 'papryka', 'sałata', 'kapusta', 'brokuł'
            ],
            'Nabiał': [
                'mleko', 'ser', 'jogurt', 'kefir', 'śmietana', 'masło',
                'twaróg', 'żółty ser', 'biały ser', 'jajka'
            ],
            'Mięso i Wędliny': [
                'mięso', 'kiełbasa', 'szynka', 'boczek', 'kurczak',
                'wołowina', 'wieprzowina', 'salami', 'parówki'
            ],
            'Pieczywo': [
                'chleb', 'bułka', 'bagietka', 'pączek', 'drożdżówka',
                'ciastko', 'tort', 'ciasto'
            ],
            'Napoje': [
                'woda', 'sok', 'cola', 'piwo', 'wino', 'kawa', 'herbata',
                'napój', 'juice'
            ],
            'Artykuły Chemiczne': [
                'proszek', 'szampon', 'mydło', 'pasta', 'deterget',
                'płyn', 'środek czyszczący'
            ],
            'Inne': []
        }
        
        product_lower = product_name.lower()
        
        # Try to match keywords
        for category_name, keywords in category_keywords.items():
            for keyword in keywords:
                if keyword in product_lower:
                    try:
                        category, created = Category.objects.get_or_create(
                            name=category_name,
                            defaults={'description': f'Auto-created category for {category_name}'}
                        )
                        return category
                    except Exception as e:
                        logger.error(f"Failed to get/create category {category_name}: {e}")
                        continue
        
        # Default category
        try:
            category, created = Category.objects.get_or_create(
                name='Inne',
                defaults={'description': 'Pozostałe produkty'}
            )
            return category
        except Exception as e:
            logger.error(f"Failed to create default category: {e}")
            return None


# Service factory function
def get_product_matcher(fuzzy_threshold: float = 0.75) -> ProductMatcher:
    """Get product matcher instance."""
    return ProductMatcher(fuzzy_match_threshold=fuzzy_threshold)