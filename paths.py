"""Single place for project paths and environment overrides.

Everything machine- or account-specific is read from environment variables
or from the git-ignored ``config/moodle.local.json``; nothing personal is
hard-coded here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

INFO_DIR = BASE_DIR / "info"
CHECKPOINT_DIR = INFO_DIR / "pipeline_checkpoints"
H5P_CACHE_DIR = BASE_DIR / "h5p_cache"
CREDENTIALS_DIR = BASE_DIR / "credentials"
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
CONFIG_DIR = BASE_DIR / "config"
DOWNLOADS_DIR = BASE_DIR / "downloads"
MOODLE_LOCAL_CONFIG = CONFIG_DIR / "moodle.local.json"


def _read_local_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}


LOCAL_CONFIG = _read_local_config(MOODLE_LOCAL_CONFIG)

INFO_JSON = INFO_DIR / "info.json"
BROWSER_POOL_JSON = INFO_DIR / "browser_pool.json"
CODE_SUBJECT_TXT = INFO_DIR / "code_subject.txt"
DESCRIPTION_TXT = INFO_DIR / "description.txt"
ID_ARTICLE_TXT = INFO_DIR / "id_article.txt"
NAME_ARTICLE_TXT = INFO_DIR / "name_article.txt"
XML_URL_JSON = INFO_DIR / "xml_url.json"

OUTPUT_HTML = BASE_DIR / "output.html"
TEST_OUTPUT_XML = BASE_DIR / "test_output.xml"

SERVICE_ACCOUNT_FILE = Path(
    os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", CREDENTIALS_DIR / "service_account.json")
)
GOOGLE_CLIENT_SECRET_FILE = Path(
    os.environ.get("GOOGLE_CLIENT_SECRET_FILE", CREDENTIALS_DIR / "client_secret.json")
)
GOOGLE_TOKEN_FILE = Path(os.environ.get("GOOGLE_TOKEN_FILE", CREDENTIALS_DIR / "token.json"))
GOOGLE_DRIVE_FILE_SERVICE_ACCOUNT = Path(
    os.environ.get(
        "GOOGLE_DRIVE_FILE_SERVICE_ACCOUNT",
        CREDENTIALS_DIR / "drive_service_account.json",
    )
)
QUESTION_BANK_FILE = Path(
    os.environ.get(
        "QUESTION_BANK_FILE",
        LOCAL_CONFIG.get("question_bank_file", DATA_DIR / "question_bank.txt"),
    )
)
STOCK_IMAGES_DIR = Path(os.environ.get("STOCK_IMAGES_DIR", BASE_DIR / "stock_images"))
INTEGRATION_EXCEL_FILE = Path(
    os.environ.get("INTEGRATION_EXCEL_FILE", DATA_DIR / "lessons_registry.xlsx")
)
SUBJECT_ROUTES_FILE = Path(
    os.environ.get("SUBJECT_ROUTES_FILE", CONFIG_DIR / "subject_routes.json")
)

CHROME_PATH = Path(
    os.environ.get("CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
)
CHROMEDRIVER_PATH = Path(os.environ.get("CHROMEDRIVER_PATH", "chromedriver"))

MOODLE_BASE_URL = os.environ.get(
    "MOODLE_BASE_URL",
    LOCAL_CONFIG.get("moodle_base_url", "https://moodle.example.com"),
)
MOODLE_USERNAME = os.environ.get("MOODLE_USERNAME", LOCAL_CONFIG.get("moodle_username", ""))
MOODLE_PASSWORD = os.environ.get("MOODLE_PASSWORD", LOCAL_CONFIG.get("moodle_password", ""))


def ensure_runtime_dirs() -> None:
    for path in (
        INFO_DIR, CHECKPOINT_DIR, H5P_CACHE_DIR, CREDENTIALS_DIR,
        DATA_DIR, ASSETS_DIR, CONFIG_DIR, DOWNLOADS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
