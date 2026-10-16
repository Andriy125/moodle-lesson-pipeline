from __future__ import annotations

import json
import os
import socket
import subprocess
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from paths import (
    BROWSER_POOL_JSON,
    CHROME_PATH,
    CHROMEDRIVER_PATH,
    INFO_JSON,
    MOODLE_BASE_URL,
    MOODLE_PASSWORD,
    MOODLE_USERNAME,
    SUBJECT_ROUTES_FILE,
    ensure_runtime_dirs,
)


MOODLE_BROWSER_PORT = int(os.environ.get("MOODLE_BROWSER_PORT", "9222"))
BROWSER_PORTS = [MOODLE_BROWSER_PORT]
DEFAULT_COURSE_URL = f"{MOODLE_BASE_URL}/my/courses.php"
WAIT_SECONDS = 20


def attach_chrome(port: int):
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", f"localhost:{port}")
    browser = webdriver.Chrome(service=Service(str(CHROMEDRIVER_PATH)), options=options)
    browser.quit = lambda: None
    return browser


def chrome_is_ready(port: int) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=1):
            pass
    except OSError:
        return False
    try:
        browser = attach_chrome(port)
        browser.title
        return True
    except WebDriverException:
        return False


def start_chrome(port: int) -> dict[str, int]:
    if chrome_is_ready(port):
        print(f"Chrome already running on port {port}")
        return {"port": port, "pid": 0}

    user_data_dir = f"C:/tmp/chrome-debug-{port}"
    process = subprocess.Popen(
        [
            str(CHROME_PATH),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
    )
    print(f"Chrome started on port {port} (PID {process.pid})")
    return {"port": port, "pid": process.pid}


def _load_info() -> dict:
    if not INFO_JSON.exists():
        return {}
    try:
        with INFO_JSON.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}


def course_url_from_info() -> str:
    """course_url живий, резолвиться з subject_routes.json за поточним code_subject
    (як в create_article.py) — а НЕ з закешованого info.json["url_course"], яке
    ніхто в актуальному пайплайні не оновлює і яке лишається від попереднього предмету
    (напр. НМ10) після перемикання на новий предмет."""
    info = _load_info()
    code_subject = info.get("code_subject", "")
    head = code_subject.split()[0] if code_subject else ""

    if head and SUBJECT_ROUTES_FILE.exists():
        try:
            routes = json.loads(SUBJECT_ROUTES_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            routes = {}
        route = routes.get(head, {})
        if route.get("course_url"):
            return route["course_url"]

    return info.get("url_course") or DEFAULT_COURSE_URL


def wait_until_loaded(browser) -> None:
    try:
        WebDriverWait(browser, WAIT_SECONDS).until(
            lambda driver: driver.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        pass


def login_if_needed(browser, port: int) -> None:
    if "login" not in browser.current_url:
        return

    if not MOODLE_PASSWORD:
        print(f"[pre_launch:{port}] Moodle login page is open. Log in manually, then press Enter here.")
        input()
        return

    username = WebDriverWait(browser, WAIT_SECONDS).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[name='username'], input[type='email'], #username")
        )
    )
    if not username.get_attribute("value"):
        username.clear()
        username.send_keys(MOODLE_USERNAME)

    password_set = browser.execute_script(
        """
        const fields = [...document.querySelectorAll("input[name='password'], input[type='password'], #password")];
        const field = fields.find((item) => {
            const rect = item.getBoundingClientRect();
            const style = window.getComputedStyle(item);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
        }) || fields[0];
        if (!field) {
            return false;
        }
        field.focus();
        field.value = arguments[0];
        field.dispatchEvent(new Event('input', {bubbles: true}));
        field.dispatchEvent(new Event('change', {bubbles: true}));
        return true;
        """,
        MOODLE_PASSWORD,
    )
    if not password_set:
        raise RuntimeError("Moodle password field not found")

    browser.execute_script(
        """
        const buttons = [...document.querySelectorAll("button[type='submit'], input[type='submit']")];
        const button = buttons.find((item) => {
            const rect = item.getBoundingClientRect();
            const style = window.getComputedStyle(item);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
        }) || buttons[0];
        if (!button) {
            return false;
        }
        button.click();
        return true;
        """
    )
    wait_until_loaded(browser)


def page_is_in_edit_mode(browser) -> bool:
    body_classes = browser.find_element(By.TAG_NAME, "body").get_attribute("class") or ""
    if "editing" in body_classes:
        return True

    state = browser.execute_script(
        """
        const controls = [
            ...document.querySelectorAll("input[name='setmode'], input[name='edit'], input[type='checkbox']"),
            ...document.querySelectorAll("[role='switch'], [aria-checked]")
        ];
        for (const control of controls) {
            const text = (control.innerText || control.labels?.[0]?.innerText || '').toLowerCase();
            const name = (control.name || '').toLowerCase();
            const id = (control.id || '').toLowerCase();
            if (!text.includes('edit') && !text.includes('редаг') && !name.includes('mode') && !id.includes('mode')) {
                continue;
            }
            if (control.checked || control.getAttribute('aria-checked') === 'true') {
                return true;
            }
        }
        return false;
        """
    )
    return bool(state)


def find_edit_mode_toggle(browser):
    candidates = browser.find_elements(
        By.CSS_SELECTOR,
        "input[name='setmode'], form[action*='setmode'] input[type='checkbox'], "
        "form[action*='setmode'] label, [role='switch'][aria-checked], label[for*='setmode']",
    )
    if candidates:
        return candidates[0]

    labels = browser.find_elements(
        By.XPATH,
        "//label[contains(., 'Режим редагування') or contains(., 'Edit mode') or contains(., 'редагування')]",
    )
    return labels[0] if labels else None


def enable_edit_mode_if_available(browser, port: int) -> None:
    if page_is_in_edit_mode(browser):
        print(f"[pre_launch:{port}] edit mode already enabled")
        return

    toggle = find_edit_mode_toggle(browser)
    if toggle is None:
        print(f"[pre_launch:{port}] edit mode toggle not found")
        return

    browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", toggle)
    try:
        toggle.click()
    except WebDriverException:
        browser.execute_script("arguments[0].click();", toggle)

    try:
        WebDriverWait(browser, WAIT_SECONDS).until(
            lambda driver: page_is_in_edit_mode(driver)
        )
        print(f"[pre_launch:{port}] edit mode enabled")
    except TimeoutException:
        print(f"[pre_launch:{port}] edit mode was clicked, but body class did not confirm it")


def prepare_moodle_session(port: int, course_url: str) -> None:
    browser = attach_chrome(port)
    browser.get(course_url)
    wait_until_loaded(browser)
    login_if_needed(browser, port)

    if "login" in browser.current_url:
        return

    if browser.current_url != course_url:
        browser.get(course_url)
        wait_until_loaded(browser)

    enable_edit_mode_if_available(browser, port)


def session_already_ready() -> bool:
    """Швидкий guard: усі порти живі й браузер уже на Moodle (не login).
    Дозволяє pre_launch (always_run) НЕ ре-навігувати курс щокроку, але
    лишитись запобіжником — якщо сесія відвалилась, повертаємо False → повна підготовка."""
    if not BROWSER_POOL_JSON.exists():
        return False
    if not all(chrome_is_ready(port) for port in BROWSER_PORTS):
        return False
    try:
        browser = attach_chrome(BROWSER_PORTS[0])
        url = browser.current_url
        return "example.com" in url and "login" not in url
    except Exception:
        return False


def main() -> None:
    ensure_runtime_dirs()
    if session_already_ready():
        print("[pre_launch] сесія вже готова — пропускаю підготовку")
        return
    processes = [start_chrome(port) for port in BROWSER_PORTS]
    deadline = time.time() + 15
    for port in BROWSER_PORTS:
        while not chrome_is_ready(port):
            if time.time() > deadline:
                print(f"[pre_launch] Chrome on port {port} не відповів за 15 с")
                break
            time.sleep(0.5)

    course_url = course_url_from_info()
    for port in BROWSER_PORTS:
        prepare_moodle_session(port, course_url)

    BROWSER_POOL_JSON.write_text(
        json.dumps(processes, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )
    print(f"\nBrowser pool saved: {BROWSER_POOL_JSON}")
    print("All browser sessions are ready.")


if __name__ == "__main__":
    main()
