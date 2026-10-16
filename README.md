# Moodle lesson pipeline

Turns a lesson written in a **Google Doc** into a finished **Moodle** lesson
page — formatted HTML, embedded images, H5P interactives and an imported quiz —
without copy-pasting anything by hand.

I built this for a school's distance-learning platform, where a lesson used to
take a long manual session of formatting text, uploading pictures, building
H5P activities and importing test questions. The pipeline reduces that to
"write the lesson in the doc, run one command, review each step".

> Written on my own initiative while working in IT support — it was never part of my job description, I built it to remove repetitive manual work.

> The code was used in production on real lessons. Course URLs, credentials and
> lesson content have been removed; `moodle.example.com` is a placeholder.

## What it does

```
Google Doc (table: one row = one lesson block)
      │
      ▼
 doc_to_html.py      parse the doc → styled HTML, collect H5P tasks, build quiz XML
      │
      ▼
 create_h5p.py       Selenium: create the H5P activities in Moodle, cache embed code
      │
      ▼
 create_article.py   Selenium: create the Moodle Page activity
 insert_xml_text.py  Selenium: import the quiz questions, link the quiz
      │
      ▼
 doc_to_html.py      second pass: swap placeholders for real H5P / quiz links
      │
      ▼
 insert_photos.py    upload images from Drive/stock folder into the page editor
      │
      ▼
 insert_done_lesson_excel.py   register the finished lesson in a tracking sheet
```

`run_pipeline.py` orchestrates the steps with **file-based checkpoints**, so a
failed or interrupted run resumes where it stopped, and with **manual review
gates** where a human should look at the result before the next step.

## Highlights

- **Google Docs API parser** that understands nested lists, rich links,
  per-run formatting and special in-document markers, and renders them with
  per-subject style templates (`custom_styles`).
- **Block state machine** (greeting / theory / practice / interactive / test /
  final / additional) that switches styling and numbering rules as it walks
  the table.
- **Resumable orchestrator** — `status`, `reset`, restart from any step,
  Ctrl+R to rerun a step, preview of generated HTML before continuing.
- **Selenium automation attached to a running Chrome** (remote-debugging port),
  so the login session is reused and steps share one browser.
- **Quiz import** — question text → Moodle XML, with question-bank lookup so
  duplicates are not re-imported.
- **Tests** for checkpoints, step logging, artifact collection and the pure
  parsing helpers (`pytest`).

## Setup

Windows + Python 3.11+ + Chrome (the review gates use `msvcrt`, the Excel
step uses COM).

```powershell
pip install -r requirements.txt
copy .env.example .env                       # then fill it in
copy config\moodle.local.example.json config\moodle.local.json
copy config\subject_routes.example.json config\subject_routes.json
```

Put your Google credentials in `credentials/` (git-ignored) — see
`.env.example` for the variable names. `config/subject_routes.json` maps a
subject code to the Moodle course/section URLs used when creating pages and
quizzes (and, optionally, `homework_book_url` — a BookCreator book embedded
under the homework block).

## Run

```powershell
$env:MOODLE_PASSWORD = "..."
python run_pipeline.py            # run all steps, resuming from checkpoints
python run_pipeline.py status     # show what is done / pending
python run_pipeline.py reset      # clear checkpoints
python run_pipeline.py create_art # restart from a specific step
```

The lesson to process (`document_id`, `code_subject`, `current_subject`) is
read from `info/info.json`, or from `GOOGLE_DOC_ID` / `CODE_SUBJECT`.

## Tests

```powershell
pytest
```

## Project layout

| File | Role |
|------|------|
| `run_pipeline.py` | Step orchestration, checkpoints, review gates |
| `doc_to_html.py` | Google Doc → HTML, H5P task extraction, quiz XML |
| `create_article.py`, `create_h5p.py`, `insert_xml_text.py`, `insert_photos.py` | Selenium steps against Moodle |
| `tools_moodle.py` | Shared Selenium helpers (waits, clicks, TinyMCE, uploads) |
| `paths.py` | All paths and env overrides in one place |
| `lesson_log.py`, `pipeline_artifacts.py` | Per-lesson step log and artifact collection |
| `docs/architecture.md` | Detailed walkthrough of the data flow (in Ukrainian) |
| `docs/xpath_changes.md` | Log of locator hardening (absolute XPath → stable ids) |

## Known limitations

Honest list, because this grew organically from a script into a tool:

- `doc_to_html.py` is large and uses module-level state for the current block;
  splitting it into a parser, a style registry and a renderer is the obvious
  next refactor.
- Some Selenium locators still depend on the Moodle theme/version; hardened
  ones are tracked in `docs/xpath_changes.md`.
- Windows-only (`msvcrt`, `pywin32`).
