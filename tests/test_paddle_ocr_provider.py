from vl2d.providers.paddle_ocr import _parse_paddle_ocr_result, _summarize_paddle_ocr_result


def test_parse_paddle_ocr_result_flattens_lines() -> None:
    result = [
        [
            [[[0, 0], [1, 0], [1, 1], [0, 1]], ("第一行", 0.98)],
            [[[0, 2], [1, 2], [1, 3], [0, 3]], ("第二行", 0.88)],
        ]
    ]

    text, confidence = _parse_paddle_ocr_result(result)

    assert text == "第一行\n第二行"
    assert round(confidence, 2) == 0.93


def test_parse_paddle_ocr_result_supports_modern_dict_payload() -> None:
    result = [
        {
            "input_path": "sample.png",
            "rec_texts": ["唐蕃会盟碑"],
            "rec_scores": [0.9982],
            "dt_polys": [],
        }
    ]

    text, confidence = _parse_paddle_ocr_result(result)

    assert text == "唐蕃会盟碑"
    assert round(confidence, 4) == 0.9982


def test_summarize_paddle_ocr_result_records_modern_keys() -> None:
    result = [{"rec_texts": ["中文"], "rec_scores": [0.99], "dt_polys": []}]
    summary = _summarize_paddle_ocr_result(result)

    assert summary["result_container_type"] == "list"
    assert summary["page_count"] == 1
    assert "dict" in summary["page_types"]
    assert "rec_texts" in summary["first_page_keys"]
