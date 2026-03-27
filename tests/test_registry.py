from vl2d.providers import get_provider_registry


def test_provider_registry_contains_expected_defaults() -> None:
    providers = get_provider_registry().describe()
    assert "energy_vad" in providers.vad
    assert "silero_vad" in providers.vad
    assert "semamba" in providers.enhancer
    assert "mock_ocr" in providers.ocr
    assert "paddle_ocr" in providers.ocr
    assert "paddleocr_vl" in providers.ocr
    assert "tesseract_ocr" in providers.ocr
