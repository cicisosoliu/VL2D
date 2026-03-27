from __future__ import annotations

from pathlib import Path

from vl2d.doctor import collect_doctor_report


def test_collect_doctor_report_flags_missing_default_tesseract_language(
    app_env, monkeypatch, tmp_path: Path
) -> None:
    app_env.default_ocr_provider = "tesseract_ocr"
    fake_tesseract = tmp_path / "tesseract"
    fake_tesseract.write_text("", encoding="utf-8")

    def fake_which(command: str) -> str | None:
        if command == "ffmpeg":
            return "/opt/homebrew/bin/ffmpeg"
        if command == "tesseract":
            return str(fake_tesseract)
        return None

    class FakeCompletedProcess:
        stdout = 'List of available languages in "/tmp/tessdata/" (2):\neng\nosd\n'

    def fake_run(command, **kwargs):
        assert command == [str(fake_tesseract), "--list-langs"]
        return FakeCompletedProcess()

    monkeypatch.setattr("vl2d.doctor.shutil.which", fake_which)
    monkeypatch.setattr("vl2d.doctor.subprocess.run", fake_run)
    monkeypatch.setattr("vl2d.doctor.importlib.util.find_spec", lambda name: None)

    report = collect_doctor_report(app_env)

    assert report.is_ready is False
    tesseract_check = next(check for check in report.checks if check.name == "tesseract_ocr")
    assert tesseract_check.status == "fail"
    assert tesseract_check.blocking is True
    assert "chi_sim" in tesseract_check.summary


def test_collect_doctor_report_accepts_ready_paddle_default(app_env, monkeypatch) -> None:
    app_env.default_ocr_provider = "paddle_ocr"

    monkeypatch.setattr("vl2d.doctor.shutil.which", lambda command: "/opt/homebrew/bin/ffmpeg" if command == "ffmpeg" else None)
    monkeypatch.setattr(
        "vl2d.doctor.importlib.util.find_spec",
        lambda name: object() if name in {"paddleocr", "paddle"} else None,
    )

    report = collect_doctor_report(app_env)

    assert report.is_ready is True
    paddle_check = next(check for check in report.checks if check.name == "paddle_ocr")
    assert paddle_check.status == "pass"
