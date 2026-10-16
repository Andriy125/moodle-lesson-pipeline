from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import tools_moodle
from paths import DOWNLOADS_DIR, INFO_JSON, MOODLE_BASE_URL, QUESTION_BANK_FILE, SUBJECT_ROUTES_FILE
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


DEFAULT_EXPORT_URL = f"{MOODLE_BASE_URL}/question/bank/exportquestions/export.php?cmid=14368"
WAIT_SECONDS = 30


browser = tools_moodle.browser


def wait() -> WebDriverWait:
    return WebDriverWait(browser, WAIT_SECONDS)


def load_info() -> dict:
    if not INFO_JSON.exists():
        return {}
    with INFO_JSON.open(encoding="utf-8") as file:
        return json.load(file)


def subject_route_key(code_subject: str) -> str:
    head = code_subject.split()[0] if code_subject else ""
    return re.sub(r"[\d_]+$", "", head) if head else ""


def load_subject_route(code_subject: str) -> dict:
    if not SUBJECT_ROUTES_FILE.exists():
        return {}

    routes = json.loads(SUBJECT_ROUTES_FILE.read_text(encoding="utf-8"))
    candidates = []
    head = code_subject.split()[0] if code_subject else ""
    if head:
        candidates.append(head)
    prefix = subject_route_key(code_subject)
    if prefix and prefix not in candidates:
        candidates.append(prefix)

    for key in candidates:
        if key in routes:
            return routes[key]
    return {}


def export_url_for(info: dict) -> str:
    route = load_subject_route(info.get("code_subject", ""))
    return (
        info.get("question_bank_export_url")
        or route.get("question_bank_export_url")
        or DEFAULT_EXPORT_URL
    )


def url_with_format(url: str, question_format: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["format"] = [question_format]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def prepare_download_dir() -> None:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    for file in DOWNLOADS_DIR.glob("question-bank-export-*"):
        if file.is_file():
            file.unlink()

    browser.execute_cdp_cmd(
        "Page.setDownloadBehavior",
        {"behavior": "allow", "downloadPath": str(DOWNLOADS_DIR)},
    )


def click_checkbox_if_needed(selector: str) -> None:
    checkbox = wait().until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
    if not checkbox.is_selected():
        browser.execute_script("arguments[0].click();", checkbox)


def select_gift_format() -> None:
    gift = wait().until(EC.presence_of_element_located((By.ID, "id_format_gift")))
    if not gift.is_selected():
        browser.execute_script("arguments[0].click();", gift)


def submit_export() -> None:
    submit = wait().until(EC.element_to_be_clickable((By.ID, "id_submitbutton")))
    browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit)
    browser.execute_script("arguments[0].click();", submit)


def wait_for_download(start_time: float) -> Path:
    deadline = time.time() + 60
    while time.time() < deadline:
        partials = list(DOWNLOADS_DIR.glob("*.crdownload")) + list(DOWNLOADS_DIR.glob("*.tmp"))
        files = [
            file
            for file in DOWNLOADS_DIR.iterdir()
            if file.is_file()
            and file.suffix.lower() not in {".crdownload", ".tmp"}
            and file.stat().st_mtime >= start_time
        ]
        if files and not partials:
            return max(files, key=lambda file: file.stat().st_mtime)
        time.sleep(0.5)

    raise TimeoutException(f"Question bank export did not finish in {DOWNLOADS_DIR}")


def copy_to_question_bank(downloaded_file: Path) -> None:
    text = downloaded_file.read_text(encoding="utf-8-sig")
    if "::" not in text or "$CATEGORY:" not in text:
        raise RuntimeError(
            f"Downloaded file does not look like a GIFT question bank: {downloaded_file}"
        )

    QUESTION_BANK_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUESTION_BANK_FILE.write_text(text, encoding="utf-8")

    archive = QUESTION_BANK_FILE.with_name("question_bank_latest.gift")
    shutil.copyfile(downloaded_file, archive)

    print(f"[export_bank] downloaded: {downloaded_file}")
    print(f"[export_bank] updated: {QUESTION_BANK_FILE}")
    print(f"[export_bank] archived: {archive}")


def main() -> int:
    info = load_info()
    url = url_with_format(export_url_for(info), "gift")

    prepare_download_dir()
    print(f"[export_bank] open: {url}")
    browser.get(url)
    wait().until(lambda driver: driver.execute_script("return document.readyState") == "complete")

    select_gift_format()
    click_checkbox_if_needed("#id_cattofile")
    click_checkbox_if_needed("#id_contexttofile")

    start_time = time.time()
    submit_export()
    downloaded_file = wait_for_download(start_time)
    copy_to_question_bank(downloaded_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
