from vl2d.text import aggregate_ocr_texts, is_placeholder_ocr_text, normalize_text


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text("  hello \n world  ") == "hello world"


def test_aggregate_ocr_texts_dedupes_adjacent() -> None:
    assert aggregate_ocr_texts(["བོད", "བོད", "ཡིག"]) == "བོད\nཡིག"


def test_placeholder_ocr_text_detection() -> None:
    assert is_placeholder_ocr_text("UNVERIFIED abc 00 55150 roi")
    assert not is_placeholder_ocr_text("བོད་ཡིག")
