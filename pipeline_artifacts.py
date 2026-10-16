from __future__ import annotations

import json
from pathlib import Path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def read_artifacts(info_dir: Path) -> dict:
    """Дешеві верифікаційні сигнали, які пишуть кроки пайплайну в info/."""
    info_dir = Path(info_dir)
    return {
        "id_article": _read_text(info_dir / "id_article.txt"),
        "name_article": _read_text(info_dir / "name_article.txt"),
        "description": _read_text(info_dir / "description.txt"),
        "code_subject": _read_text(info_dir / "code_subject.txt"),
        "xml_url": _read_json(info_dir / "xml_url.json"),
    }


def done_steps(checkpoint_dir: Path) -> set:
    p = Path(checkpoint_dir)
    if not p.exists():
        return set()
    return {f.stem for f in p.glob("*.done")}
