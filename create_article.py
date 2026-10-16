from __future__ import annotations

import json
import re
from time import sleep
from urllib.parse import parse_qs, urlparse

from paths import DESCRIPTION_TXT, ID_ARTICLE_TXT, INFO_JSON, NAME_ARTICLE_TXT, SUBJECT_ROUTES_FILE
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


WAIT_SECONDS = 30


def load_article_config() -> dict:
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


def wait_for_first(browser, locators: list[tuple[str, str]], timeout: int = WAIT_SECONDS):
    last_error = None
    for by, selector in locators:
        try:
            return WebDriverWait(browser, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
        except TimeoutException as error:
            last_error = error

    tried = ", ".join(f"{by}={selector}" for by, selector in locators)
    raise TimeoutException(f"None of the locators matched: {tried}") from last_error


def click_first(browser, locators: list[tuple[str, str]], timeout: int = WAIT_SECONDS) -> None:
    last_error = None
    for by, selector in locators:
        try:
            button = WebDriverWait(browser, timeout).until(
                EC.element_to_be_clickable((by, selector))
            )
            browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            # JS-клік замість native .click(): не залежить від фокуса/видимості вікна.
            # Native-клік через ChromeDriver флапає, коли вікно Chrome не у foreground
            # (Windows) → "зберегти" не давало навігації. JS-клік працює у фоні.
            browser.execute_script("arguments[0].click();", button)
            return
        except TimeoutException as error:
            last_error = error

    tried = ", ".join(f"{by}={selector}" for by, selector in locators)
    raise TimeoutException(f"None of the clickable locators matched: {tried}") from last_error


def set_text_input(browser, value: str) -> None:
    title_input = wait_for_first(
        browser,
        [
            (By.ID, "id_name"),
            (By.NAME, "name"),
            (By.CSS_SELECTOR, "input[name='name']"),
            (By.XPATH, "//label[contains(., 'Name') or contains(., 'Назва')]/following::input[1]"),
            (By.XPATH, "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input"),
        ],
    )
    browser.execute_script(
        """
        arguments[0].value = arguments[1];
        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
        arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
        """,
        title_input,
        value,
    )

    if not title_input.get_attribute("value"):
        raise RuntimeError("Moodle page title field stayed empty after fill")


def set_description(browser, html: str) -> None:
    if not html.strip():
        return

    inserted = browser.execute_script(
        """
        const html = arguments[0];
        const editorIds = ['id_introeditor', 'id_introeditoreditable', 'introeditor'];

        for (const id of editorIds) {
            const editor = window.tinymce && tinymce.get(id);
            if (editor) {
                editor.setContent(html);
                editor.save();
                editor.fire('input');
                editor.fire('change');
                return `tinymce:${id}`;
            }
        }

        const editable = document.querySelector(
            '#id_introeditoreditable, [contenteditable="true"][id*="intro"]'
        );
        if (editable) {
            editable.innerHTML = html;
            editable.dispatchEvent(new Event('input', {bubbles: true}));
            editable.dispatchEvent(new Event('change', {bubbles: true}));
            return 'contenteditable';
        }

        const textarea = document.querySelector(
            '#id_introeditor, textarea[name="intro[text]"], textarea[name="intro"], textarea[id*="intro"]'
        );
        if (textarea) {
            textarea.value = html;
            textarea.dispatchEvent(new Event('input', {bubbles: true}));
            textarea.dispatchEvent(new Event('change', {bubbles: true}));
            return 'textarea';
        }

        return '';
        """,
        html,
    )
    if inserted:
        print(f"[create_art] description set via {inserted}")
        return

    iframe_locators = [
        (By.ID, "id_introeditor_ifr"),
        (By.CSS_SELECTOR, "#id_introeditor iframe"),
        (By.CSS_SELECTOR, "iframe[id^='id_introeditor']"),
        (By.CSS_SELECTOR, "iframe.tox-edit-area__iframe"),
        (By.CSS_SELECTOR, "iframe.cke_wysiwyg_frame"),
        (By.XPATH, "//textarea[@name='intro']/ancestor::*[contains(@class, 'feditor') or contains(@class, 'editor_atto')]//iframe"),
        (By.XPATH, "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div/div[2]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/iframe"),
    ]

    try:
        iframe = wait_for_first(browser, iframe_locators, timeout=2)
        browser.switch_to.frame(iframe)
        browser.execute_script(
            """
            document.body.innerHTML = arguments[0];
            document.body.dispatchEvent(new Event('input', {bubbles: true}));
            document.body.dispatchEvent(new Event('change', {bubbles: true}));
            """,
            html,
        )
        browser.switch_to.default_content()
        return
    except TimeoutException:
        browser.switch_to.default_content()

    textarea = wait_for_first(
        browser,
        [
            (By.ID, "id_introeditoreditable"),
            (By.NAME, "intro"),
            (By.CSS_SELECTOR, "textarea[name='intro']"),
        ],
        timeout=2,
    )
    browser.execute_script(
        """
        arguments[0].value = arguments[1];
        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
        arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
        """,
        textarea,
        html,
    )


def set_placeholder_page_content(browser) -> None:
    browser.execute_script(
        """
        const html = '<p>.</p>';
        if (window.tinymce && tinymce.get('id_page')) {
            tinymce.get('id_page').setContent(html);
        }
        const pageTextarea = document.querySelector('#id_page, textarea[name="page[text]"], textarea[name="content"]');
        if (pageTextarea) {
            pageTextarea.value = html;
            pageTextarea.dispatchEvent(new Event('change', {bubbles: true}));
        }
        """
    )


def save_page(browser) -> None:
    click_first(
        browser,
        [
            (By.ID, "id_submitbutton"),
            (By.ID, "id_submitbutton2"),
            (By.CSS_SELECTOR, "input[type='submit'][name='submitbutton']"),
            (By.CSS_SELECTOR, "input[type='submit'][name='submitbutton2']"),
            (By.CSS_SELECTOR, "button[type='submit'][name='submitbutton']"),
            (By.CSS_SELECTOR, "button[type='submit'][name='submitbutton2']"),
            (By.XPATH, "//input[@type='submit' and (contains(@value, 'Save') or contains(@value, 'Зберегти'))]"),
            (By.XPATH, "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/div[4]/div[2]/div[1]/div/div[2]"),
        ],
    )


def extract_article_id(url: str) -> str:
    if "/mod/page/view.php" not in url:
        raise RuntimeError(f"Expected Moodle page view URL, got: {url}")
    query_params = parse_qs(urlparse(url).query)
    article_id = query_params.get("id", [None])[0]
    if not article_id:
        raise RuntimeError(f"Could not extract article id from URL: {url}")
    return article_id


def main() -> None:
    import tools_moodle

    config = load_article_config()
    subject_route = load_subject_route(config.get("code_subject", ""))
    create_page_url = (
        config.get("url_create_page")
        or subject_route.get("create_page_url")
    )
    if not create_page_url:
        raise RuntimeError(
            f"create_page_url не задано для '{config.get('code_subject', '')}': "
            "додай його в subject_routes.json або url_create_page в info.json"
        )

    browser = tools_moodle.browser
    print(f"[create_art] відкриваємо {create_page_url}")
    browser.get(create_page_url)

    name_page = NAME_ARTICLE_TXT.read_text(encoding="utf-8")
    description_html = DESCRIPTION_TXT.read_text(encoding="utf-8")

    print("[create_art] wait: поле назви...")
    set_text_input(browser, name_page)
    print("[create_art] поле назви знайдено")

    print("[create_art] вставляємо опис")
    set_description(browser, description_html)

    set_placeholder_page_content(browser)
    sleep(0.5)

    print("[create_art] зберігаємо сторінку")
    save_page(browser)
    sleep(1)

    id_article = extract_article_id(browser.current_url)
    print(f"id_article - {id_article}")
    ID_ARTICLE_TXT.write_text(id_article, encoding="utf-8")


if __name__ == "__main__":
    main()
