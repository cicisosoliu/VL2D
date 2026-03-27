from vl2d.providers.tesseract_ocr import _parse_tesseract_languages, _parse_tesseract_tsv


def test_parse_tesseract_languages() -> None:
    output = 'List of available languages in "/tmp/tessdata/" (3):\nchi_sim\neng\nosd\n'
    assert _parse_tesseract_languages(output) == {"chi_sim", "eng", "osd"}


def test_parse_tesseract_tsv_groups_words_by_line() -> None:
    output = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t92.0\t中文\n"
        "5\t1\t1\t1\t1\t2\t10\t0\t10\t10\t88.0\t字幕\n"
        "5\t1\t1\t1\t2\t1\t0\t12\t10\t10\t85.0\t样本\n"
    )
    text, confidence = _parse_tesseract_tsv(output)
    assert text == "中文 字幕\n样本"
    assert round(confidence, 2) == 88.33
