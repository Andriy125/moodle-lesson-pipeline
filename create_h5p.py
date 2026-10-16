from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import tools_moodle
from paths import H5P_CACHE_DIR, INFO_JSON, SUBJECT_ROUTES_FILE
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


browser = tools_moodle.browser
WAIT_SECONDS = 40


@dataclass(frozen=True)
class H5PLibrary:
    marker: str
    library: str


H5P_LIBRARIES = [
    H5PLibrary("=DT=", "H5P.DragText%201.10"),
    H5PLibrary("=FT=", "H5P.Blanks%201.14"),
    H5PLibrary("=SCT=", "H5P.SingleChoiceSet%201.11"),
    H5PLibrary("=MCT=", "H5P.MultiChoice%201.16"),
    H5PLibrary("=CW=", "H5P.Crossword%200.4"),
]


def wait() -> WebDriverWait:
    return WebDriverWait(browser, WAIT_SECONDS)


def load_info() -> dict:
    with INFO_JSON.open(encoding="utf-8") as file:
        return json.load(file)


def cache_file(code_subject: str) -> Path:
    return H5P_CACHE_DIR / f"{code_subject}.json"


def load_h5p_items(path: Path) -> list[dict]:
    if not path.exists():
        print(f"[create_h5p] H5P cache not found: {path}")
        return []
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def save_h5p_items(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=4)


def _subject_route_key(code_subject: str) -> str:
    import re
    head = code_subject.split()[0] if code_subject else ""
    return re.sub(r"[\d_]+$", "", head) if head else ""


def content_bank_url(info: dict) -> str:
    if info.get("url_content_bank"):
        return info["url_content_bank"]

    code_subject = info.get("code_subject", "")
    if SUBJECT_ROUTES_FILE.exists():
        import json as _json
        routes = _json.loads(SUBJECT_ROUTES_FILE.read_text(encoding="utf-8"))
        for key in (code_subject.split()[0] if code_subject else "", _subject_route_key(code_subject)):
            if key and routes.get(key, {}).get("content_bank_url"):
                return routes[key]["content_bank_url"]

    raise RuntimeError(
        f"content_bank_url не знайдено: ні в info.json, ні в subject_routes.json для '{code_subject}'"
    )


def detect_library(type_h5p: str) -> H5PLibrary:
    for library in H5P_LIBRARIES:
        if library.marker in type_h5p:
            return library
    raise RuntimeError(f"Unsupported H5P type: {type_h5p}")


def create_url(bank_url: str, library: H5PLibrary) -> str:
    separator = "&" if "?" in bank_url else "?"
    url = f"{bank_url}{separator}plugin=h5p&library={library.library}"
    return url.replace("index.php", "edit.php")


def open_content_bank(bank_url: str) -> None:
    browser.get(bank_url)
    wait().until(lambda driver: driver.execute_script("return document.readyState") == "complete")
    wait().until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-region='filearea']")))


def content_exists(title: str) -> bool:
    filearea = browser.find_element(By.CSS_SELECTOR, "[data-region='filearea']")
    return title in filearea.text


def open_h5p_editor(url: str) -> None:
    browser.get(url)
    wait().until(lambda driver: driver.execute_script("return document.readyState") == "complete")
    iframe = wait().until(EC.presence_of_element_located((By.CSS_SELECTOR, ".h5p-editor-iframe")))
    browser.switch_to.frame(iframe)
    wait().until(EC.presence_of_element_located((By.ID, "field-extratitle--1")))


def set_input_value(selector: str, value: str) -> None:
    element = wait().until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
    browser.execute_script(
        """
        arguments[0].value = arguments[1];
        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
        arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
        """,
        element,
        value,
    )


def set_textarea_value(field_id: str, value: str) -> None:
    field = wait().until(EC.presence_of_element_located((By.ID, field_id)))
    browser.execute_script(
        """
        arguments[0].value = arguments[1];
        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
        arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
        """,
        field,
        value,
    )


def set_ckeditor_text(field_id: str, value: str) -> None:
    field = wait().until(EC.presence_of_element_located((By.ID, field_id)))
    # HTML-методи не розуміють \n — конвертуємо у <br>; textarea-fallback отримує оригінал
    value_html = value.replace('\n', '<br>')

    if (field.get_attribute("contenteditable") or "").lower() == "true":
        browser.execute_script(
            """
            arguments[0].scrollIntoView({block: 'center'});
            arguments[0].innerHTML = arguments[1];
            arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
            arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
            arguments[0].blur();
            """,
            field,
            value_html,
        )
        return

    changed = browser.execute_script(
        """
        if (window.CKEDITOR && CKEDITOR.instances && CKEDITOR.instances[arguments[0]]) {
            CKEDITOR.instances[arguments[0]].setData(arguments[1]);
            CKEDITOR.instances[arguments[0]].fire('change');
            return true;
        }
        return false;
        """,
        field_id,
        value_html,
    )
    if changed:
        return

    iframe_selector = f"#cke_{field_id} iframe.cke_wysiwyg_frame"
    if browser.find_elements(By.CSS_SELECTOR, iframe_selector):
        iframe = browser.find_element(By.CSS_SELECTOR, iframe_selector)
        browser.switch_to.frame(iframe)
        body = wait().until(EC.presence_of_element_located((By.CSS_SELECTOR, "body.cke_editable")))
        browser.execute_script(
            """
            arguments[0].innerHTML = arguments[1];
            arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
            arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
            """,
            body,
            value_html,
        )
        browser.switch_to.default_content()
        browser.switch_to.frame(browser.find_element(By.CSS_SELECTOR, ".h5p-editor-iframe"))
        return

    set_textarea_value(field_id, value)


def clean_header(header: str) -> str:
    header = (header or "").strip()
    return header[3:].strip() if header.lower().startswith("h: ") else header


def _sct_click_widget(name: str) -> bool:
    """Клік вкладки режиму SingleChoiceSet («Текстовий» / «По умовчанню») за текстом."""
    return browser.execute_script(
        """
        const li = [...document.querySelectorAll('li.h5peditor-widget-option')]
            .find(x => (x.textContent || '').includes(arguments[0]));
        if (li) { li.click(); return true; }
        return false;
        """,
        name,
    )


def fill_single_choice(item: dict) -> None:
    set_input_value("#field-extratitle--1", item["title"])

    # 1) Перемикаємо у «Текстовий» режим (textarea-формат: питання, далі варіанти,
    #    ПЕРШИЙ = правильний, порожній рядок між питаннями).
    if not _sct_click_widget("Текстовий"):
        raise RuntimeError("SCT: не знайдено вкладку «Текстовий»")
    time.sleep(1)

    wait().until(EC.presence_of_element_located((By.CSS_SELECTOR, "textarea")))
    ok = browser.execute_script(
        """
        const ta = [...document.querySelectorAll('textarea')].find(t => t.offsetParent !== null);
        if (!ta) return false;
        ta.value = arguments[0];
        ta.dispatchEvent(new Event('input', {bubbles: true}));
        ta.dispatchEvent(new Event('change', {bubbles: true}));
        return true;
        """,
        item["text_task"],
    )
    if not ok:
        raise RuntimeError("SCT: не знайдено textarea у режимі «Текстовий»")
    time.sleep(0.5)

    # 2) КРИТИЧНО: перемикаємо назад у «По умовчанню» — це ЗМУШУЄ H5P розпарсити
    #    textarea у модель. Без цього збереження з textarea-режиму давало криву/порожню
    #    розмітку (питання без варіантів).
    _sct_click_widget("умовчанню")
    time.sleep(1)


def fill_drag_text(item: dict) -> None:
    set_input_value("#field-extratitle--1", item["title"])

    header = clean_header(item.get("header", ""))
    if header:
        set_ckeditor_text("field-taskdescription-16", header)

    set_input_value("#field-textfield-17", item["text_task"])


def fill_blanks(item: dict) -> None:
    set_input_value("#field-extratitle--1", item["title"])

    header = clean_header(item.get("header", ""))
    if header:
        set_ckeditor_text("field-text-16", header)

    set_ckeditor_text("field-question-18", item["text_task"])


def _mc_field_ids() -> dict:
    """Рантайм-дискаверинг id у редакторі MultiChoice (суфікси field-*-N плавають)."""
    return browser.execute_script(
        """
        const q = document.querySelector('div.ckeditor[id^="field-question-"]');
        return {
            question: q ? q.id : null,
            texts:    [...document.querySelectorAll('div.ckeditor[id^="field-text-"]')].map(e => e.id),
            corrects: [...document.querySelectorAll('input[id^="field-correct-"]')].map(e => e.id),
        };
        """
    )


def _mc_click_add_answer() -> bool:
    """Клік «ADD ПАРАМЕТР» (додати відповідь), НЕ «Add Діапазон». Через JS+textContent,
    бо у DIV-кнопки Selenium .text буває порожній (text-transform/видимість)."""
    return browser.execute_script(
        """
        const btns = [...document.querySelectorAll('div.h5peditor-button-textual')];
        const b = btns.find(x => (x.textContent || '').toUpperCase().includes('ПАРАМЕТР'));
        if (b) { b.scrollIntoView({block: 'center'}); b.click(); return true; }
        return false;
        """
    )


def fill_multi_choice(item: dict) -> None:
    set_input_value("#field-extratitle--1", item["title"])

    lines = [ln.strip() for ln in item["text_task"].split("\n") if ln.strip()]
    question_line = lines[0] if lines else ""
    answers = []  # (text, is_correct)
    for ln in lines[1:]:
        if ln.startswith("+"):
            answers.append((ln[1:].strip(), True))
        else:  # «-» або без маркера → неправильна (безпечно)
            answers.append((ln.lstrip("-").strip(), False))

    header = clean_header(item.get("header", ""))
    question = f"{header} {question_line}".strip() if header else question_line

    # Додати рядки відповідей до потрібної кількості (стартово їх 2)
    while len(_mc_field_ids()["corrects"]) < len(answers):
        if not _mc_click_add_answer():
            break
        time.sleep(0.4)

    ids = _mc_field_ids()
    if ids["question"]:
        set_ckeditor_text(ids["question"], question)

    for index, (text, is_correct) in enumerate(answers):
        if index < len(ids["texts"]):
            set_ckeditor_text(ids["texts"][index], text)
        if is_correct and index < len(ids["corrects"]):
            checkbox = browser.find_element(By.ID, ids["corrects"][index])
            if not checkbox.is_selected():
                browser.execute_script("arguments[0].click();", checkbox)


def fill_h5p_editor(library: H5PLibrary, item: dict) -> None:
    if library.marker == "=DT=":
        fill_drag_text(item)
        return
    if library.marker == "=FT=":
        fill_blanks(item)
        return
    if library.marker == "=SCT=":
        fill_single_choice(item)
        return
    if library.marker == "=MCT=":
        fill_multi_choice(item)
        return
    raise RuntimeError(f"{library.marker} is recognized, but live creation is not implemented yet")


def submit_and_read_result() -> tuple[str, str]:
    browser.switch_to.default_content()
    submit = wait().until(EC.element_to_be_clickable((By.ID, "id_submitbutton")))
    browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit)
    browser.execute_script("arguments[0].click();", submit)

    view = wait().until(EC.visibility_of_element_located((By.CSS_SELECTOR, "[data-region='viewcontent-content']")))
    html_code = view.get_attribute("outerHTML").replace('<div class="d-flex justify-content-end mb-3">\n</div>', "")
    return html_code, browser.current_url


def create_h5p_item(bank_url: str, item: dict) -> dict:
    library = detect_library(item["type"])

    open_content_bank(bank_url)
    if content_exists(item["title"]):
        print(f"[create_h5p] already exists: {item['title']}")
        return item

    open_h5p_editor(create_url(bank_url, library))
    fill_h5p_editor(library, item)
    html_code, url_task = submit_and_read_result()

    item["html_code"] = html_code
    item["url_task"] = url_task
    print(f"[create_h5p] created: {item['title']}")
    print(f"[create_h5p] url_task: {url_task}")
    return item


def main() -> int:
    start_time = time.time()
    info = load_info()
    code_subject = info["code_subject"]
    path = cache_file(code_subject)
    items = load_h5p_items(path)
    if not items:
        return 0

    bank_url = content_bank_url(info)
    updated_items = []
    failed = []

    for item in items:
        try:
            updated_items.append(create_h5p_item(bank_url, item))
        except Exception as error:
            # Один проблемний H5P (напр. ще не дороблений тип) НЕ валить весь крок/урок.
            # Лишаємо item без html_code, гучно попереджаємо, йдемо далі.
            print(f"[create_h5p] ⚠️  ПОМИЛКА на '{item.get('title')}' ({item.get('type')}): {error}")
            failed.append(item.get("title"))
            updated_items.append(item)
            browser.switch_to.default_content()

    save_h5p_items(path, updated_items)
    print(f"[create_h5p] saved cache: {path}")
    if failed:
        print(f"[create_h5p] ⚠️  не створено {len(failed)}: {failed}")
    print(f"[create_h5p] done in {time.time() - start_time:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
