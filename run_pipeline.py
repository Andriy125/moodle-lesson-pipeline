from __future__ import annotations

import json
import os
import subprocess
import time
import sys
from dataclasses import dataclass
from pathlib import Path

import msvcrt

from paths import BASE_DIR, CHECKPOINT_DIR, INFO_JSON, ensure_runtime_dirs
from utils import dependency_env, wait_for_key
from lesson_log import init_steps_log, record_step, prompt_and_save_notes


PYTHON = sys.executable
DEFAULT_MOODLE_BROWSER_PORT = int(os.environ.get("MOODLE_BROWSER_PORT", "9222"))
STEP_RESTART_EXIT_CODE = 75


def _lesson_log_dir() -> "Path | None":
    val = os.environ.get("LESSON_LOG_DIR", "")
    return Path(val) if val else None


@dataclass(frozen=True)
class PipelineStep:
    name: str
    script: Path
    browser_port: int | None = None
    requires_confirmation: bool = False
    confirmation_prompt: str = ""
    always_run: bool = False
    preview_output: bool = False


PREPARE_BROWSER_STEP = PipelineStep(
    "pre_launch",
    BASE_DIR / "pre_launch.py",
    always_run=True,
)

ARTICLE_STEPS = [
    PipelineStep(
        "doc_to_html_first",
        BASE_DIR / "doc_to_html.py",
        requires_confirmation=True,
        confirmation_prompt="Перевір HTML -> Enter щоб продовжити",
        preview_output=True,
    ),
    PipelineStep("create_art", BASE_DIR / "create_article.py", browser_port=DEFAULT_MOODLE_BROWSER_PORT),
    PipelineStep("insert_xml", BASE_DIR / "insert_xml_text.py", browser_port=DEFAULT_MOODLE_BROWSER_PORT),
    PipelineStep(
        "doc_to_html_second",
        BASE_DIR / "doc_to_html.py",
        requires_confirmation=True,
        confirmation_prompt="Перевір посилання на тест -> Enter щоб продовжити",
        preview_output=True,
    ),
    PipelineStep(
        "insert_photo",
        BASE_DIR / "insert_photos.py",
        browser_port=DEFAULT_MOODLE_BROWSER_PORT,
        requires_confirmation=True,
        confirmation_prompt="Перевір збережену сторінку -> Enter щоб записати урок в Excel",
    ),
    PipelineStep("insert_done", BASE_DIR / "insert_done_lesson_excel.py"),
]

H5P_STEP = PipelineStep("create_h5p", BASE_DIR / "create_h5p.py", browser_port=DEFAULT_MOODLE_BROWSER_PORT)
MANUAL_STEPS = [
    PipelineStep("export_question_bank", BASE_DIR / "export_question_bank.py", browser_port=DEFAULT_MOODLE_BROWSER_PORT),
]


def pipeline_steps() -> list[PipelineStep]:
    steps = []
    steps.extend([ARTICLE_STEPS[0], H5P_STEP, *ARTICLE_STEPS[1:]])
    return steps


def step_names() -> list[str]:
    return [step.name for step in [*pipeline_steps(), *MANUAL_STEPS]]


def all_steps_by_name() -> dict[str, PipelineStep]:
    return {step.name: step for step in [*pipeline_steps(), *MANUAL_STEPS]}


def checkpoint_path(step_name: str) -> Path:
    return CHECKPOINT_DIR / f"{step_name}.done"


def is_done(step_name: str) -> bool:
    return checkpoint_path(step_name).exists()


def mark_done(step_name: str) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path(step_name).touch()


def reset_from(step_name: str) -> None:
    names = step_names()
    if step_name not in names:
        print(f"Unknown step: '{step_name}'. Available: {', '.join(names)}")
        return

    for name in names[names.index(step_name) :]:
        path = checkpoint_path(name)
        if path.exists():
            path.unlink()
            print(f"  reset: {name}")


def reset_all_checkpoints() -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    for file in CHECKPOINT_DIR.iterdir():
        if file.is_file():
            file.unlink()


def run_step(step: PipelineStep) -> None:
    if is_done(step.name) and not step.always_run:
        print(f"\n[skip] {step.name} - already done")
        return

    log_dir = _lesson_log_dir()

    while True:
        start = time.monotonic()
        result = run_script(step)
        duration = time.monotonic() - start

        if result.returncode == STEP_RESTART_EXIT_CODE:
            print(f"\n{step.script.name} requested restart")
            print("  -> restarting step...\n")
            continue

        if result.returncode != 0:
            if log_dir:
                record_step(log_dir, step.name, "error", duration, f"exit code {result.returncode}")
            print(f"\nERROR: {step.script.name} exited with code {result.returncode}")
        elif not step.requires_confirmation:
            if step.preview_output:
                open_output_preview()
            mark_done(step.name)
            if log_dir:
                record_step(log_dir, step.name, "ok", duration)
            return
        else:
            if step.preview_output:
                open_output_preview()
            print(f"\n{step.confirmation_prompt}")

        print("Enter - continue  |  Ctrl+R - run this step again  |  Ctrl+C - stop")
        action = wait_for_key()
        if action == "restart":
            print("  -> restarting step...\n")
            continue

        if result.returncode == 0:
            mark_done(step.name)
            if log_dir:
                record_step(log_dir, step.name, "ok", duration)
        return


def run_script(step: PipelineStep) -> subprocess.CompletedProcess:
    env = dependency_env()
    if step.browser_port:
        env["BROWSER_PORT"] = str(step.browser_port)

    port_info = f" (port {step.browser_port})" if step.browser_port else ""
    print(f"\n{'=' * 55}")
    print(f"  {step.name}: {step.script.name}{port_info}")
    print("=" * 55)
    sys.stdout.flush()

    return subprocess.run([PYTHON, str(step.script)], env=env, cwd=BASE_DIR)


def open_output_preview() -> None:
    output_html = BASE_DIR / "output.html"
    if not output_html.exists():
        print(f"[preview] output.html not found: {output_html}")
        return

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service as ChromeService
        from paths import CHROMEDRIVER_PATH
        opts = webdriver.ChromeOptions()
        opts.add_experimental_option("debuggerAddress", f"localhost:{DEFAULT_MOODLE_BROWSER_PORT}")
        browser = webdriver.Chrome(service=ChromeService(str(CHROMEDRIVER_PATH)), options=opts)
        browser.get(output_html.as_uri())
        print(f"[preview] opened in existing browser: {output_html}")
    except Exception as error:
        print(f"[preview] selenium failed ({error}), falling back to os.startfile")
        try:
            os.startfile(str(output_html))
        except OSError as fallback_error:
            print(f"[preview] cannot open output.html: {fallback_error}")


def handle_cli_argument() -> None:
    if len(sys.argv) <= 1:
        return

    argument = sys.argv[1].strip().lower()
    names = step_names()

    if argument == "reset":
        reset_all_checkpoints()
        print("All checkpoints were reset. Run pipeline again.")
        raise SystemExit(0)

    if argument == "status":
        print_status()
        raise SystemExit(0)

    if argument in names:
        if argument in {step.name for step in MANUAL_STEPS}:
            run_step(all_steps_by_name()[argument])
            raise SystemExit(0)
        print(f"Resetting '{argument}' and all following steps...")
        reset_from(argument)
        print("Done. Pipeline will start from that step.")
        raise SystemExit(0)

    print(f"Unknown step: '{argument}'")
    print(f"Available: {', '.join(names)}")
    print("Other commands: reset, status")
    raise SystemExit(1)


def reset_when_subject_changed() -> None:
    last_subject_file = CHECKPOINT_DIR / "_last_subject.txt"
    current_subject = read_current_subject()
    last_subject = last_subject_file.read_text(encoding="utf-8").strip() if last_subject_file.exists() else ""

    if not current_subject or current_subject == last_subject:
        return

    print(f"\nNew lesson: {current_subject}  (was: {last_subject or '-'})")
    print("Resetting all checkpoints automatically.")
    reset_all_checkpoints()
    last_subject_file.write_text(current_subject, encoding="utf-8")


def read_current_subject() -> str:
    if not INFO_JSON.exists():
        return ""

    with INFO_JSON.open(encoding="utf-8") as file:
        return json.load(file).get("code_subject", "")


def print_status() -> None:
    print("\nPipeline status:")
    print("  AUTO create_h5p (skips itself when h5p_cache has no lesson file)")
    print(f"  RUN {PREPARE_BROWSER_STEP.name} (always)")

    for step in pipeline_steps():
        mark = "OK" if is_done(step.name) else ".."
        print(f"  {mark} {step.name}")

    print("\nManual steps:")
    for step in MANUAL_STEPS:
        print(f"  run {step.name}: python run_pipeline.py {step.name}")

    todo_steps = [step.name for step in pipeline_steps() if not is_done(step.name)]
    done_steps = [step.name for step in pipeline_steps() if is_done(step.name)]
    if done_steps and todo_steps:
        print(f"\nStart from: {todo_steps[0]}")
        print("Reset from step: python run_pipeline.py <step_name>")
        print("Reset all:       python run_pipeline.py reset")


def main() -> None:
    ensure_runtime_dirs()
    handle_cli_argument()
    reset_when_subject_changed()

    log_dir = _lesson_log_dir()
    if log_dir:
        subject_code = read_current_subject()
        parts = subject_code.split()
        subject = parts[0] if parts else "UNKNOWN"
        lesson = int(parts[1]) if len(parts) > 1 else 0
        init_steps_log(log_dir, lesson, subject)

    print_status()
    run_step(PREPARE_BROWSER_STEP)

    for step in pipeline_steps():
        run_step(step)
        if step.name == "insert_photo" and log_dir:
            prompt_and_save_notes(log_dir, "Після Moodle")

    print("\n" + "=" * 55)
    print("  Pipeline finished")
    print("=" * 55)


if __name__ == "__main__":
    main()
