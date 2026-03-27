from __future__ import annotations

from functools import lru_cache

from vl2d.providers.base import ProviderRegistry
from vl2d.providers.mock import EnergyVADProvider, MockOCRProvider, PassthroughEnhancerProvider
from vl2d.providers.paddle_ocr import PaddleOCRProvider
from vl2d.providers.paddleocr_vl import PaddleOCRVLProvider
from vl2d.providers.semamba import SEMambaEnhancerProvider
from vl2d.providers.silero import SileroVADProvider
from vl2d.providers.tesseract_ocr import TesseractOCRProvider


@lru_cache
def get_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register_vad("silero_vad", SileroVADProvider)
    registry.register_vad("energy_vad", EnergyVADProvider)
    registry.register_enhancer("semamba", SEMambaEnhancerProvider)
    registry.register_enhancer("passthrough_enhancer", PassthroughEnhancerProvider)
    registry.register_ocr("tesseract_ocr", TesseractOCRProvider)
    registry.register_ocr("paddle_ocr", PaddleOCRProvider)
    registry.register_ocr("paddleocr_vl", PaddleOCRVLProvider)
    registry.register_ocr("mock_ocr", MockOCRProvider)
    return registry
