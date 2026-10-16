import json
from pipeline_artifacts import read_artifacts, done_steps


def test_read_artifacts_reads_known_files(tmp_path):
    (tmp_path / "id_article.txt").write_text("14377", encoding="utf-8")
    (tmp_path / "name_article.txt").write_text("Урок 23. Test", encoding="utf-8")
    (tmp_path / "xml_url.json").write_text(json.dumps({"url": "http://x/quiz"}), encoding="utf-8")
    art = read_artifacts(tmp_path)
    assert art["id_article"] == "14377"
    assert art["name_article"] == "Урок 23. Test"
    assert art["xml_url"] == {"url": "http://x/quiz"}


def test_read_artifacts_missing_files(tmp_path):
    art = read_artifacts(tmp_path)
    assert art["id_article"] == ""
    assert art["xml_url"] == {}


def test_done_steps(tmp_path):
    (tmp_path / "create_art.done").touch()
    (tmp_path / "insert_xml.done").touch()
    assert done_steps(tmp_path) == {"create_art", "insert_xml"}


def test_done_steps_empty(tmp_path):
    assert done_steps(tmp_path) == set()
