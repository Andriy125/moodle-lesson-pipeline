from __future__ import annotations

import json
import time
from pathlib import Path


def gdoc_to_markdown(doc: dict) -> str:
    """Convert Google Docs API response to plain markdown text."""
    heading_prefix = {"HEADING_1": "# ", "HEADING_2": "## ", "HEADING_3": "### "}
    lines = []
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        style = paragraph.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")
        parts = [
            run.get("textRun", {}).get("content", "")
            for run in paragraph.get("elements", [])
        ]
        text = "".join(parts).rstrip("\n")
        if not text.strip():
            lines.append("")
            continue
        lines.append(heading_prefix.get(style, "") + text)
    return "\n".join(lines)


def make_lesson_dir(base: Path, subject: str, lesson: int) -> Path:
    path = base / "lessons" / f"{subject}_{lesson:03d}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_gdoc(doc_id: str, dest: Path, service_account_file: str) -> None:
    from google.oauth2 import service_account as sa
    from googleapiclient.discovery import build

    creds = sa.Credentials.from_service_account_file(
        service_account_file,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    drive = build("drive", "v3", credentials=creds)
    content = drive.files().export_media(fileId=doc_id, mimeType="text/plain").execute()
    dest.write_text(content.decode("utf-8"), encoding="utf-8")
    print(f"[log] GDoc snapshot -> {dest.name}")


def append_user_notes(lesson_dir: Path, section: str, text: str) -> None:
    notes = lesson_dir / "user_notes.md"
    with notes.open("a", encoding="utf-8") as f:
        f.write(f"\n## {section}\n{text if text.strip() else '(без правок)'}\n")


def prompt_and_save_notes(lesson_dir: Path, section: str) -> None:
    print(f"\n[log] {section} — що правив? (просто Enter = пропустити; 'END' на новому рядку = зберегти):")
    lines: list[str] = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        if not lines and not line.strip():
            break
        lines.append(line)
    append_user_notes(lesson_dir, section, "\n".join(lines))
    print(f"[log] збережено -> user_notes.md")


def init_steps_log(lesson_dir: Path, lesson: int, subject: str) -> None:
    steps_file = lesson_dir / "steps.json"
    data = {
        "lesson": lesson,
        "subject": subject,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "steps": [],
    }
    steps_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_step(lesson_dir: Path, name: str, status: str, duration_sec: float, error: str = "") -> None:
    steps_file = lesson_dir / "steps.json"
    if not steps_file.exists():
        return
    data = json.loads(steps_file.read_text(encoding="utf-8"))
    entry: dict = {"name": name, "status": status, "duration_sec": round(duration_sec, 1)}
    if error:
        entry["error"] = error
    data["steps"].append(entry)
    steps_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
