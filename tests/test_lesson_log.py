import json
import pytest
from lesson_log import (
    gdoc_to_markdown,
    make_lesson_dir,
    append_user_notes,
    init_steps_log,
    record_step,
)


def _paragraph(style: str, text: str) -> dict:
    return {
        "paragraph": {
            "paragraphStyle": {"namedStyleType": style},
            "elements": [{"textRun": {"content": text}}],
        }
    }


def test_gdoc_heading1():
    doc = {"body": {"content": [_paragraph("HEADING_1", "Тема\n")]}}
    assert gdoc_to_markdown(doc) == "# Тема"


def test_gdoc_heading2():
    doc = {"body": {"content": [_paragraph("HEADING_2", "Підрозділ\n")]}}
    assert gdoc_to_markdown(doc) == "## Підрозділ"


def test_gdoc_normal_text():
    doc = {"body": {"content": [_paragraph("NORMAL_TEXT", "Звичайний текст")]}}
    assert gdoc_to_markdown(doc) == "Звичайний текст"


def test_gdoc_skips_empty_paragraphs():
    doc = {"body": {"content": [_paragraph("NORMAL_TEXT", "   \n")]}}
    assert gdoc_to_markdown(doc).strip() == ""


def test_gdoc_multiple_elements():
    doc = {
        "body": {
            "content": [
                _paragraph("HEADING_1", "Заголовок\n"),
                _paragraph("NORMAL_TEXT", "Текст\n"),
            ]
        }
    }
    result = gdoc_to_markdown(doc)
    assert "# Заголовок" in result
    assert "Текст" in result


def test_make_lesson_dir(tmp_path):
    path = make_lesson_dir(tmp_path, "НМ10", 5)
    assert path.exists()
    assert path.name == "НМ10_005"


def test_make_lesson_dir_zero_padded(tmp_path):
    path = make_lesson_dir(tmp_path, "НМ10", 12)
    assert path.name == "НМ10_012"


def test_append_user_notes_with_text(tmp_path):
    append_user_notes(tmp_path, "Після Gemini", "Виправив заголовок")
    content = (tmp_path / "user_notes.md").read_text(encoding="utf-8")
    assert "## Після Gemini" in content
    assert "Виправив заголовок" in content


def test_append_user_notes_empty(tmp_path):
    append_user_notes(tmp_path, "Після Moodle", "")
    content = (tmp_path / "user_notes.md").read_text(encoding="utf-8")
    assert "(без правок)" in content


def test_append_user_notes_accumulates(tmp_path):
    append_user_notes(tmp_path, "Після Gemini", "Перша нотатка")
    append_user_notes(tmp_path, "Після Moodle", "Друга нотатка")
    content = (tmp_path / "user_notes.md").read_text(encoding="utf-8")
    assert "Після Gemini" in content
    assert "Після Moodle" in content


def test_init_steps_log(tmp_path):
    init_steps_log(tmp_path, 5, "НМ10")
    data = json.loads((tmp_path / "steps.json").read_text(encoding="utf-8"))
    assert data["lesson"] == 5
    assert data["subject"] == "НМ10"
    assert data["steps"] == []
    assert "started_at" in data


def test_record_step_ok(tmp_path):
    init_steps_log(tmp_path, 5, "НМ10")
    record_step(tmp_path, "doc_to_html_first", "ok", 12.3)
    data = json.loads((tmp_path / "steps.json").read_text(encoding="utf-8"))
    assert len(data["steps"]) == 1
    step = data["steps"][0]
    assert step["name"] == "doc_to_html_first"
    assert step["status"] == "ok"
    assert step["duration_sec"] == 12.3
    assert "error" not in step


def test_record_step_error(tmp_path):
    init_steps_log(tmp_path, 5, "НМ10")
    record_step(tmp_path, "create_h5p", "error", 3.0, "XPath not found")
    data = json.loads((tmp_path / "steps.json").read_text(encoding="utf-8"))
    assert data["steps"][0]["error"] == "XPath not found"


def test_record_step_multiple(tmp_path):
    init_steps_log(tmp_path, 5, "НМ10")
    record_step(tmp_path, "doc_to_html_first", "ok", 10.0)
    record_step(tmp_path, "create_h5p", "ok", 15.0)
    data = json.loads((tmp_path / "steps.json").read_text(encoding="utf-8"))
    assert len(data["steps"]) == 2


def test_record_step_no_file(tmp_path):
    record_step(tmp_path, "some_step", "ok", 1.0)
