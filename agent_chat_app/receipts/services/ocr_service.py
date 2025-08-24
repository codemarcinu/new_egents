"""
OCR services for receipt processing.
Implements hybrid OCR with multiple backends as described in system-paragonow-guide.md
"""

import asyncio
import logging
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from PIL import Image, ImageEnhance, ImageFilter
import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Result from OCR processing."""
    success: bool
    text: str
    confidence: float = 0.0
    error_message: str = ""
    backend_name: str = ""


@dataclass
class ImageProcessingResult:
    """Result from image preprocessing."""
    success: bool
    processed_path: str
    original_path: str
    error_message: str = ""


class OCRBackend(ABC):
    """Abstract base class for OCR backends."""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this OCR backend is available."""
        pass
    
    @abstractmethod
    async def extract_text(self, image_path: str) -> OCRResult:
        """Extract text from image."""
        pass


class TesseractBackend(OCRBackend):
    """Tesseract OCR backend."""
    
    def __init__(self):
        super().__init__("Tesseract")
    
    def is_available(self) -> bool:
        """Check if Tesseract is available."""
        try:
            import pytesseract
            return True
        except ImportError:
            logger.warning("pytesseract not available")
            return False
    
    async def extract_text(self, image_path: str) -> OCRResult:
        """Extract text using Tesseract."""
        try:
            import pytesseract
            from PIL import Image
            
            # Configure Tesseract for receipts
            config = '--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,!@#$%^&*()_+-=[]{}|;:\'\"<>?/~ '
            
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image, config=config)
            
            # Calculate confidence (Tesseract doesn't provide it directly)
            confidence = 0.7 if text.strip() else 0.1
            
            return OCRResult(
                success=True,
                text=text.strip(),
                confidence=confidence,
                backend_name=self.name
            )
            
        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            return OCRResult(
                success=False,
                text="",
                confidence=0.0,
                error_message=str(e),
                backend_name=self.name
            )


class EasyOCRBackend(OCRBackend):
    """EasyOCR backend for improved accuracy."""
    
    def __init__(self):
        super().__init__("EasyOCR")
        self._reader = None
    
    def is_available(self) -> bool:
        """Check if EasyOCR is available."""
        try:
            import easyocr
            return True
        except ImportError:
            logger.warning("easyocr not available")
            return False
    
    async def extract_text(self, image_path: str) -> OCRResult:
        """Extract text using EasyOCR."""
        try:
            import easyocr
            
            if self._reader is None:
                # Initialize with Polish and English
                self._reader = easyocr.Reader(['pl', 'en'], gpu=False)  # Set gpu=True if CUDA is available
            
            results = self._reader.readtext(image_path)
            
            # Combine all text results
            text_parts = []
            confidence_scores = []
            
            for (bbox, text, conf) in results:
                text_parts.append(text)
                confidence_scores.append(conf)
            
            combined_text = '\n'.join(text_parts)
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
            
            return OCRResult(
                success=True,
                text=combined_text.strip(),
                confidence=avg_confidence,
                backend_name=self.name
            )
            
        except Exception as e:
            logger.error(f"EasyOCR failed: {e}")
            return OCRResult(
                success=False,
                text="",
                confidence=0.0,
                error_message=str(e),
                backend_name=self.name
            )


class PaddleOCRBackend(OCRBackend):
    """PaddleOCR backend as additional fallback."""
    
    def __init__(self):
        super().__init__("PaddleOCR")
    
    def is_available(self) -> bool:
        """Check if PaddleOCR is available."""
        try:
            from paddleocr import PaddleOCR
            return True
        except ImportError:
            logger.warning("paddleocr not available")
            return False
    
    async def extract_text(self, image_path: str) -> OCRResult:
        """Extract text using PaddleOCR."""
        try:
            from paddleocr import PaddleOCR
            
            ocr = PaddleOCR(use_angle_cls=True, lang='en', use_gpu=False)
            result = ocr.ocr(image_path, cls=True)
            
            text_parts = []
            confidence_scores = []
            
            for line in result[0] or []:
                bbox, (text, conf) = line
                text_parts.append(text)
                confidence_scores.append(conf)
            
            combined_text = '\n'.join(text_parts)
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
            
            return OCRResult(
                success=True,
                text=combined_text.strip(),
                confidence=avg_confidence,
                backend_name=self.name
            )
            
        except Exception as e:
            logger.error(f"PaddleOCR failed: {e}")
            return OCRResult(
                success=False,
                text="",
                confidence=0.0,
                error_message=str(e),
                backend_name=self.name
            )


class GoogleVisionBackend(OCRBackend):
    """Google Vision API backend (requires API key)."""
    
    def __init__(self):
        super().__init__("Google Vision")
    
    def is_available(self) -> bool:
        """Check if Google Vision API is available."""
        try:
            from google.cloud import vision
            return bool(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))
        except ImportError:
            logger.warning("google-cloud-vision not available")
            return False
    
    async def extract_text(self, image_path: str) -> OCRResult:
        """Extract text using Google Vision API."""
        try:
            from google.cloud import vision
            
            client = vision.ImageAnnotatorClient()
            
            with open(image_path, 'rb') as image_file:
                content = image_file.read()
            
            image = vision.Image(content=content)
            response = client.text_detection(image=image)
            
            if response.error.message:
                raise Exception(response.error.message)
            
            texts = response.text_annotations
            if texts:
                combined_text = texts[0].description
                confidence = 0.9  # Google Vision typically has high confidence
            else:
                combined_text = ""
                confidence = 0.0
            
            return OCRResult(
                success=True,
                text=combined_text.strip(),
                confidence=confidence,
                backend_name=self.name
            )
            
        except Exception as e:
            logger.error(f"Google Vision OCR failed: {e}")
            return OCRResult(
                success=False,
                text="",
                confidence=0.0,
                error_message=str(e),
                backend_name=self.name
            )


class MistralOCRBackend(OCRBackend):
    """Mistral OCR backend (paid service - limited usage)."""
    
    def __init__(self):
        super().__init__("Mistral OCR")
    
    def is_available(self) -> bool:
        """Check if Mistral OCR API is available."""
        try:
            return bool(os.environ.get('MISTRAL_API_KEY'))
        except Exception:
            logger.warning("Mistral API key not available")
            return False
    
    async def extract_text(self, image_path: str) -> OCRResult:
        """Extract text using Mistral OCR API."""
        try:
            import httpx
            
            api_key = os.environ.get('MISTRAL_API_KEY')
            if not api_key:
                raise Exception("MISTRAL_API_KEY not found in environment")
            
            # TODO: Replace with actual Mistral OCR API call
            # This is a placeholder implementation
            # According to Mistral documentation, you would need to:
            # 1. Upload image to their service
            # 2. Call OCR endpoint
            # 3. Parse response
            
            async with httpx.AsyncClient() as client:
                # Placeholder - implement actual Mistral OCR API call
                logger.warning("Mistral OCR API call not implemented - placeholder only")
                
                # For now, return a high-confidence empty result to indicate "attempted"
                return OCRResult(
                    success=False,
                    text="",
                    confidence=0.0,
                    error_message="Mistral OCR implementation pending",
                    backend_name=self.name
                )
            
        except Exception as e:
            logger.error(f"Mistral OCR failed: {e}")
            return OCRResult(
                success=False,
                text="",
                confidence=0.0,
                error_message=str(e),
                backend_name=self.name
            )


class ImageProcessor:
    """Image preprocessing for better OCR results."""
    
    @staticmethod
    def preprocess_image(image_path: str) -> ImageProcessingResult:
        """Preprocess image to improve OCR accuracy."""
        try:
            # Create output path
            base, ext = os.path.splitext(image_path)
            processed_path = f"{base}_processed{ext}"
            
            # Open and process image
            image = Image.open(image_path)
            
            # Convert to grayscale
            if image.mode != 'L':
                image = image.convert('L')
            
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.5)
            
            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(2.0)
            
            # Apply filters to reduce noise
            image = image.filter(ImageFilter.MedianFilter(size=3))
            
            # Convert to OpenCV format for advanced processing
            opencv_image = cv2.cvtColor(np.array(image), cv2.COLOR_GRAY2BGR)
            opencv_image = cv2.cvtColor(opencv_image, cv2.COLOR_BGR2GRAY)
            
            # Apply adaptive threshold
            processed_cv = cv2.adaptiveThreshold(
                opencv_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )
            
            # Convert back to PIL
            processed_image = Image.fromarray(processed_cv)
            
            # Save processed image
            processed_image.save(processed_path, optimize=True, quality=95)
            
            return ImageProcessingResult(
                success=True,
                processed_path=processed_path,
                original_path=image_path
            )
            
        except Exception as e:
            logger.error(f"Image preprocessing failed: {e}")
            return ImageProcessingResult(
                success=False,
                processed_path=image_path,
                original_path=image_path,
                error_message=str(e)
            )


class AdaptiveHybridOCRService:
    """
    Adaptive hybrid OCR service with multiple backends and cost-aware fallback strategy.
    Implements the adaptive OCR management from the enhanced workflow.
    """
    
    def __init__(self, confidence_threshold=0.75, max_backends=3, timeout=30):
        self.confidence_threshold = confidence_threshold
        self.max_backends = max_backends
        self.timeout = timeout
        
        # Initialize local (free) backends first - priority order
        self.local_backends = [
            EasyOCRBackend(),      # GPU-accelerated, best for receipts  
            TesseractBackend(),    # CPU fallback
            PaddleOCRBackend(),    # Additional CPU fallback
        ]
        
        # Initialize paid backends - used sparingly
        self.paid_backends = [
            MistralOCRBackend(),   # Paid Mistral OCR
            GoogleVisionBackend()  # Paid Google Vision
        ]
        
        # Filter to only available backends
        self.available_local_backends = [b for b in self.local_backends if b.is_available()]
        self.available_paid_backends = [b for b in self.paid_backends if b.is_available()]
        
        if not self.available_local_backends and not self.available_paid_backends:
            logger.warning("No OCR backends available!")
        else:
            local_names = [b.name for b in self.available_local_backends]
            paid_names = [b.name for b in self.available_paid_backends]
            logger.info(f"Available local OCR backends: {local_names}")
            logger.info(f"Available paid OCR backends: {paid_names}")

    async def extract_text_from_file_with_receipt(self, image_path: str, receipt) -> str:
        """
        Extract text from image file using adaptive OCR approach with receipt tracking.
        
        Args:
            image_path: Path to the image file
            receipt: Receipt instance for tracking attempts_mistral
            
        Returns:
            Extracted text as string
        """
        if not self.available_local_backends and not self.available_paid_backends:
            raise RuntimeError("No OCR backends are available")
        
        # Preprocess image
        processor = ImageProcessor()
        processing_result = processor.preprocess_image(image_path)
        ocr_image_path = processing_result.processed_path if processing_result.success else image_path
        
        logger.info(f"Starting adaptive OCR processing for receipt {receipt.id}")
        
        results = []
        best_local_confidence = 0.0
        
        # Step 1: Always try local backends first (free)
        for backend in self.available_local_backends:
            try:
                logger.info(f"Trying local OCR backend: {backend.name}")
                
                result = await asyncio.wait_for(
                    backend.extract_text(ocr_image_path),
                    timeout=self.timeout
                )
                
                results.append(result)
                logger.info(f"{backend.name} result: success={result.success}, confidence={result.confidence:.2f}")
                
                if result.success:
                    best_local_confidence = max(best_local_confidence, result.confidence)
                
                # Stop if we have high confidence result from local backend
                if result.success and result.confidence >= self.confidence_threshold:
                    logger.info(f"High confidence result from local {backend.name}, stopping")
                    break
                    
            except asyncio.TimeoutError:
                logger.warning(f"Local OCR backend {backend.name} timed out")
                continue
            except Exception as e:
                logger.warning(f"Local OCR backend {backend.name} failed: {e}")
                continue
        
        # Step 2: Use paid backends only if local confidence is low AND attempts_mistral < 1
        if (best_local_confidence < self.confidence_threshold and 
            receipt.attempts_mistral < 1 and 
            self.available_paid_backends):
            
            logger.info(f"Local confidence {best_local_confidence:.2f} < threshold {self.confidence_threshold:.2f}, trying paid backends")
            
            for backend in self.available_paid_backends[:1]:  # Only try first paid backend
                try:
                    logger.info(f"Trying paid OCR backend: {backend.name}")
                    
                    result = await asyncio.wait_for(
                        backend.extract_text(ocr_image_path),
                        timeout=self.timeout * 2  # More time for paid services
                    )
                    
                    results.append(result)
                    logger.info(f"{backend.name} result: success={result.success}, confidence={result.confidence:.2f}")
                    
                    # Increment attempts counter for paid services  
                    if backend.name == "Mistral OCR":
                        receipt.attempts_mistral += 1
                        receipt.save(update_fields=['attempts_mistral'])
                        logger.info(f"Incremented attempts_mistral to {receipt.attempts_mistral} for receipt {receipt.id}")
                    
                    # Stop after first paid attempt
                    break
                    
                except asyncio.TimeoutError:
                    logger.warning(f"Paid OCR backend {backend.name} timed out")
                    continue
                except Exception as e:
                    logger.warning(f"Paid OCR backend {backend.name} failed: {e}")
                    continue
        else:
            if best_local_confidence >= self.confidence_threshold:
                logger.info(f"Local confidence {best_local_confidence:.2f} sufficient, skipping paid backends")
            elif receipt.attempts_mistral >= 1:
                logger.info(f"Already attempted Mistral OCR {receipt.attempts_mistral} times, skipping paid backends")
        
        if not results:
            raise RuntimeError("All OCR backends failed")
        
        # Select best result
        best_result = self._select_best_result(results)
        logger.info(f"Selected best result from {best_result.backend_name} with confidence {best_result.confidence:.2f}")
        
        # Clean up processed image
        if processing_result.success and os.path.exists(processing_result.processed_path):
            try:
                os.remove(processing_result.processed_path)
            except OSError:
                pass
        
        return best_result.text
    
    async def extract_text_from_file(self, image_path: str) -> str:
        """
        Extract text from image file using hybrid OCR approach.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Extracted text as string
            
        Raises:
            RuntimeError: If no backends are available or all fail
        """
        if not self.available_backends:
            raise RuntimeError("No OCR backends are available")
        
        # Preprocess image
        processor = ImageProcessor()
        processing_result = processor.preprocess_image(image_path)
        ocr_image_path = processing_result.processed_path if processing_result.success else image_path
        
        logger.info(f"Starting OCR processing for: {image_path}")
        
        results = []
        for backend in self.available_backends[:self.max_backends]:
            try:
                logger.info(f"Trying OCR backend: {backend.name}")
                
                result = await asyncio.wait_for(
                    backend.extract_text(ocr_image_path),
                    timeout=self.timeout
                )
                
                results.append(result)
                logger.info(f"{backend.name} result: success={result.success}, confidence={result.confidence:.2f}")
                
                # Stop if we have high confidence result
                if result.success and result.confidence >= self.confidence_threshold:
                    logger.info(f"High confidence result from {backend.name}, stopping")
                    break
                    
            except asyncio.TimeoutError:
                logger.warning(f"OCR backend {backend.name} timed out")
                continue
            except Exception as e:
                logger.warning(f"OCR backend {backend.name} failed: {e}")
                continue
        
        if not results:
            raise RuntimeError("All OCR backends failed")
        
        # Select best result
        best_result = self._select_best_result(results)
        logger.info(f"Selected best result from {best_result.backend_name} with confidence {best_result.confidence:.2f}")
        
        # Clean up processed image
        if processing_result.success and os.path.exists(processing_result.processed_path):
            try:
                os.remove(processing_result.processed_path)
            except OSError:
                pass
        
        return best_result.text
    
    def _select_best_result(self, results: List[OCRResult]) -> OCRResult:
        """Select the best OCR result based on confidence and text quality."""
        # Filter successful results
        successful_results = [r for r in results if r.success and r.text.strip()]
        
        if not successful_results:
            # Return first result even if failed
            return results[0] if results else OCRResult(
                success=False, 
                text="", 
                error_message="No successful OCR results"
            )
        
        # Sort by confidence descending
        successful_results.sort(key=lambda x: x.confidence, reverse=True)
        
        # Return highest confidence result
        return successful_results[0]


# Service factory functions
def get_image_processor() -> ImageProcessor:
    """Get image processor instance."""
    return ImageProcessor()


def get_hybrid_ocr_service(confidence_threshold=0.75) -> AdaptiveHybridOCRService:
    """Get adaptive hybrid OCR service instance."""
    return AdaptiveHybridOCRService(confidence_threshold=confidence_threshold)


def get_legacy_hybrid_ocr_service(confidence_threshold=0.7) -> 'HybridOCRService':
    """Get legacy hybrid OCR service instance (for backward compatibility)."""
    # Keep old class name for any existing references
    class HybridOCRService(AdaptiveHybridOCRService):
        pass
    return HybridOCRService(confidence_threshold=confidence_threshold)


# For backward compatibility with the guide
ocr_service = get_hybrid_ocr_service()