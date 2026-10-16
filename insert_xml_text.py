import os
import json
import tools_moodle
import time
import sys
start_time = time.time() 
browser = tools_moodle.browser
from time import sleep
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.support.ui import Select
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse
from xml.etree import ElementTree as ET
from typing import Optional
from paths import CHECKPOINT_DIR, CODE_SUBJECT_TXT, MOODLE_BASE_URL, QUESTION_BANK_FILE, SUBJECT_ROUTES_FILE, TEST_OUTPUT_XML, XML_URL_JSON


WAIT_SECONDS = 25


def wait_for_first(locators: list[tuple[str, str]], timeout: int = WAIT_SECONDS):
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


def click_first(locators: list[tuple[str, str]], timeout: int = WAIT_SECONDS) -> None:
    last_error = None
    for by, selector in locators:
        try:
            element = WebDriverWait(browser, timeout).until(
                EC.element_to_be_clickable((by, selector))
            )
            browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            # JS-клік: не залежить від фокуса/видимості вікна (native .click() через
            # ChromeDriver флапає, коли Chrome не у foreground на Windows → клік no-op).
            browser.execute_script("arguments[0].click();", element)
            return
        except (TimeoutException, WebDriverException) as error:
            last_error = error

    tried = ", ".join(f"{by}={selector}" for by, selector in locators)
    raise TimeoutException(f"None of the clickable locators matched: {tried}") from last_error


def try_click_first(locators: list[tuple[str, str]], timeout: int = 5) -> bool:
    try:
        click_first(locators, timeout=timeout)
        return True
    except TimeoutException:
        return False


def set_input_value(locators: list[tuple[str, str]], value: str) -> None:
    element = wait_for_first(locators)
    browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    try:
        element.clear()
        element.send_keys(value)
    except Exception:
        pass
    # send_keys — no-op, коли Chrome не у foreground (як native click, див. click_first):
    # винятку немає, тож покладатися на нього не можна. Верифікуємо й примусово ставимо
    # через JS з подіями input/change, щоб Moodle-валідація побачила значення.
    if (element.get_attribute("value") or "") != value:
        browser.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
            "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
            element,
            value,
        )


def ensure_collapse_container_expanded(container_id: str) -> None:
    container = browser.find_element(By.ID, container_id)
    toggles = browser.find_elements(
        By.CSS_SELECTOR,
        f"a[href$='#{container_id}'], a[aria-controls='{container_id}']",
    )
    if not toggles:
        return

    toggle = toggles[0]
    if toggle.get_attribute("aria-expanded") == "false" or not container.is_displayed():
        browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", toggle)
        try:
            toggle.click()
        except WebDriverException:
            browser.execute_script("arguments[0].click();", toggle)
        try:
            WebDriverWait(browser, 3).until(
                lambda driver: driver.find_element(By.ID, container_id).is_displayed()
            )
        except TimeoutException:
            # Bootstrap-collapse може не спрацювати по кліку (Moodle рендерить href як
            # абсолютний URL, тож ціль не резолвиться). Примусово розгортаємо класами.
            browser.execute_script(
                """
                var cid = arguments[0];
                var c = document.getElementById(cid);
                if (c) { c.classList.add('show'); }
                var fs = c ? c.closest('fieldset.collapsible') : null;
                if (fs) { fs.classList.remove('collapsed'); }
                var t = document.querySelector(
                    'a[href$="#' + cid + '"], a[aria-controls="' + cid + '"]');
                if (t) { t.setAttribute('aria-expanded', 'true'); }
                """,
                container_id,
            )
            WebDriverWait(browser, 5).until(
                lambda driver: driver.find_element(By.ID, container_id).is_displayed()
            )
        sleep(0.5)


def select_questions_on_one_page() -> None:
    ensure_collapse_container_expanded("id_layouthdrcontainer")
    select_element = wait_for_first(
        [
            (By.ID, "id_questionsperpage"),
            (By.NAME, "questionsperpage"),
            (By.CSS_SELECTOR, "select[name='questionsperpage']"),
            (By.XPATH, "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[4]/div[2]/div[1]/div[2]/fieldset/div/div/span/select"),
        ]
    )
    browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", select_element)
    select = Select(select_element)
    select.select_by_value("0")
    browser.execute_script(
        """
        arguments[0].value = '0';
        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
        arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
        """,
        select_element,
    )

    selected_value = Select(select_element).first_selected_option.get_attribute("value")
    if selected_value != "0":
        raise RuntimeError(f"Не вдалося виставити макет тесту на одну сторінку: value={selected_value}")


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


def create_quiz_url_for(code_subject: str) -> str:
    route = load_subject_route(code_subject)
    url = route.get("create_quiz_url")
    if not url:
        raise ValueError(f"No create_quiz_url configured for subject '{code_subject}'")
    return url


def question_bank_page_url(cmid: str, qpage: int) -> str:
    filter_json = json.dumps(
        {
            "category": {
                "name": "category",
                "jointype": 1,
                "values": [97],
                "filteroptions": {"includesubcategories": False},
            }
        },
        separators=(",", ":"),
    )
    return (
        f"{MOODLE_BASE_URL}/mod/quiz/edit.php?"
        f"cmid={cmid}&filter={quote(filter_json)}&qpage={qpage}"
    )


def visible_modal_fieldset():
    return wait_for_first(
        [
            (By.XPATH, "//table[@id='categoryquestions']/ancestor::fieldset[1]"),
            (By.CSS_SELECTOR, ".modal.show form fieldset"),
            (By.CSS_SELECTOR, ".modal.in form fieldset"),
        ]
    )


def modal_question_rows() -> list:
    wait_for_first([(By.ID, "categoryquestions"), (By.CSS_SELECTOR, "table#categoryquestions")])
    return browser.find_elements(By.CSS_SELECTOR, "#categoryquestions tbody tr")


def question_was_already_selected(text_question: str, selected_questions: list[str]) -> bool:
    normalized = text_question.strip()
    if not normalized:
        return False
    for selected in selected_questions:
        selected = selected.strip()
        if normalized == selected:
            return True
        if normalized[:60] and normalized[:60] in selected:
            return True
        if selected[:60] and selected[:60] in normalized:
            return True
    return False


def _cell_text(cell) -> str:
    """Текст комірки через JS textContent. Selenium `.text` повертає порожнє, коли
    Chrome не у foreground (елемент вважається невидимим) — як native click/send_keys."""
    return (browser.execute_script("return arguments[0].textContent || '';", cell) or "").strip()


def find_question_row_by_text(text_question: str):
    for row in modal_question_rows():
        cells = row.find_elements(By.CSS_SELECTOR, "td")
        if len(cells) >= 4 and _cell_text(cells[3]) == text_question:
            return row
    return None


def read_existing_quiz_questions(code_subject: str) -> list[str]:
    questions = []
    for element in browser.find_elements(By.CSS_SELECTOR, "li.activity, li.slot, .activityinstance"):
        text = element.text.strip()
        if code_subject not in text:
            continue
        for line in text.splitlines():
            line = line.strip()
            if code_subject in line and line not in questions:
                questions.append(line)
    return questions


def open_quiz_add_menu() -> None:
    candidates = browser.find_elements(
        By.CSS_SELECTOR,
        "a.dropdown-toggle:has(.add-menu), [data-action='addquestion'] a.dropdown-toggle",
    )
    if not candidates:
        candidates = [
            element
            for element in browser.find_elements(By.CSS_SELECTOR, "a.dropdown-toggle")
            if element.text.strip() in {"Додати", "Add"}
        ]
    if not candidates:
        raise TimeoutException("Не знайшов меню додавання питань у тест")

    button = candidates[-1]
    browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
    browser.execute_script("arguments[0].click();", button)
    WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".dropdown-menu a[data-action='questionbank']"))
    )


def open_question_bank_modal_from_add_menu() -> None:
    if browser.find_elements(By.CSS_SELECTOR, "#categoryquestions"):
        return

    visible_links = [
        element
        for element in browser.find_elements(By.CSS_SELECTOR, ".dropdown-menu a[data-action='questionbank']")
        if element.is_displayed()
    ]
    if visible_links:
        try:
            visible_links[-1].click()
        except WebDriverException:
            browser.execute_script("arguments[0].click();", visible_links[-1])
        wait_for_first([(By.ID, "categoryquestions"), (By.CSS_SELECTOR, "table#categoryquestions")])
        return

    try:
        click_first(
            [
                (By.CSS_SELECTOR, ".dropdown-menu.show a[data-action='questionbank']"),
                (By.CSS_SELECTOR, ".dropdown-menu a[data-action='questionbank']"),
                (By.XPATH, "//div[contains(@class, 'dropdown-menu')]//a[contains(., 'from question bank') or contains(., 'from the question bank') or contains(., 'банку питань')]"),
                (By.XPATH, "/html/body/div[4]/div[5]/div/div[3]/div/section/div[2]/div[2]/ul/li/div/div[2]/span/div/div/div/div/a[2]"),
            ],
            timeout=5,
        )
    except TimeoutException:
        links = browser.find_elements(By.CSS_SELECTOR, "a[data-action='questionbank']")
        if not links:
            raise
        browser.execute_script("arguments[0].click();", links[-1])

    wait_for_first([(By.ID, "categoryquestions"), (By.CSS_SELECTOR, "table#categoryquestions")])


def navigate_question_bank_modal_to_page(qpage: int | None) -> None:
    if qpage is None:
        return

    wait_for_first([(By.ID, "categoryquestions"), (By.CSS_SELECTOR, "table#categoryquestions")])
    table = browser.find_element(By.CSS_SELECTOR, "#categoryquestions")
    selectors = [
        f".modal.show a[href*='qpage={qpage}']",
        f".modal.in a[href*='qpage={qpage}']",
        f"a[href*='qpage={qpage}']",
    ]

    page_links = []
    for selector in selectors:
        page_links = [
            link for link in browser.find_elements(By.CSS_SELECTOR, selector)
            if link.is_displayed()
        ]
        if page_links:
            break

    if not page_links:
        page_links = [
            link for link in browser.find_elements(By.CSS_SELECTOR, ".modal a[href*='qpage='], a[href*='qpage=']")
            if link.is_displayed()
        ]
        if not page_links:
            return

        href = page_links[-1].get_attribute("href") or ""
        parsed = list(urlparse(href))
        query = parse_qs(parsed[4])
        query["qpage"] = [str(qpage)]
        parsed[4] = urlencode(query, doseq=True)
        browser.execute_script("arguments[0].setAttribute('href', arguments[1]);", page_links[-1], urlunparse(parsed))
        page_links = [page_links[-1]]

    target_link = page_links[0]
    browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_link)
    try:
        target_link.click()
    except WebDriverException:
        browser.execute_script("arguments[0].click();", target_link)

    try:
        WebDriverWait(browser, WAIT_SECONDS).until(EC.staleness_of(table))
    except TimeoutException:
        pass
    wait_for_first([(By.ID, "categoryquestions"), (By.CSS_SELECTOR, "table#categoryquestions")])


def select_lesson_questions_from_modal(
    code_subject: str,
    max_count: int,
    already_selected: list[str] | None = None,
) -> list[str]:
    visible_modal_fieldset()
    rows = modal_question_rows()
    already_selected = already_selected or []
    selected_questions = []

    print(f"DEBUG modal: {len(rows)} rows, searching for '{code_subject}'")
    if rows:
        first_cells = rows[0].find_elements(By.CSS_SELECTOR, "td")
        for i, c in enumerate(first_cells):
            print(f"DEBUG cells[{i}] = {repr(_cell_text(c)[:80])}")

    row_index = 0
    while row_index < len(rows) and len(selected_questions) < max_count:
        try:
            fresh_rows = modal_question_rows()
            if row_index >= len(fresh_rows):
                break

            row = fresh_rows[row_index]
            cells = row.find_elements(By.CSS_SELECTOR, "td")
            row_index += 1
            if len(cells) < 4:
                continue

            text_question = _cell_text(cells[3])
            if code_subject not in text_question:
                continue
            if question_was_already_selected(text_question, already_selected + selected_questions):
                continue

            selected_ok = False
            for _ in range(5):
                try:
                    fresh_row = find_question_row_by_text(text_question) or row
                    checkbox = fresh_row.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                    if not checkbox.is_selected():
                        browser.execute_script("arguments[0].click();", checkbox)
                        sleep(0.2)
                        fresh_row = find_question_row_by_text(text_question) or fresh_row
                        checkbox = fresh_row.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                    selected_ok = checkbox.is_selected()
                    if selected_ok:
                        break
                except StaleElementReferenceException:
                    sleep(0.2)

            if not selected_ok:
                raise RuntimeError(f"Question checkbox did not stay selected: {text_question}")

            selected_questions.append(text_question)
        except StaleElementReferenceException:
            sleep(0.2)

    return selected_questions


def close_question_bank_modal() -> None:
    buttons = browser.find_elements(
        By.CSS_SELECTOR,
        ".modal.show button.close, .modal.show [data-dismiss='modal'], .modal.show [data-bs-dismiss='modal']",
    )
    if buttons:
        browser.execute_script("arguments[0].click();", buttons[0])
        wait_for_modal_to_close()


def wait_for_modal_to_close() -> None:
    try:
        WebDriverWait(browser, 15).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".modal.show, .modal.in"))
        )
    except TimeoutException:
        pass
    WebDriverWait(browser, 15).until(
        lambda driver: driver.execute_script("return document.readyState") == "complete"
    )


def read_file(path_file: str) -> str:
    with open(path_file, "r", encoding="utf-8") as f:
        text = f.read()
    return text


def split_text_into_parts(text: str) -> list:
    parts = text.split("\n\n\n")

    # прибрати порожні
    parts = [p.strip() for p in parts if p.strip()]
    return parts


def extract_question_short_name(text: str) -> str | None:
    pattern = r"::([^:]+)::"
    m = re.search(pattern, text)
    return m.group(1) if m else None


def find_question_exact(parts: list[str], short_name: str) -> str | None:
    for q in parts:
        if extract_question_short_name(q) == short_name:
            return q
    return None


def parse_subject_and_num_str(short_name: str) -> tuple[str, str] | None:
    #формат "УМ6 95"
    parts = short_name.split()
    if len(parts) != 2:
        return None
    subj, num = parts[0], parts[1]
    if not num.isdigit():
        return None
    return subj, num  # num лишається РЯДКОМ


def find_question_for_insert(parts: list[str], target_short_name: str) -> Optional[str]:
    """
    Повертає блок питання, ПІСЛЯ якого треба вставляти target_short_name.
    Еталон порядку — новий файл банку питань. Порівняння числове (int).
    """
    target_parsed = parse_subject_and_num_str(target_short_name)
    if not target_parsed:
        return None
    target_subj, target_num_str = target_parsed
    target_num = int(target_num_str)

    best_question = None
    best_num = None

    for q in parts:
        sn = extract_question_short_name(q)
        if not sn:
            continue

        parsed = parse_subject_and_num_str(sn)
        if not parsed:
            continue

        subj, num_str = parsed
        if subj != target_subj:
            continue

        num = int(num_str)
        if num < target_num and (best_num is None or num > best_num):
            best_num = num
            best_question = q

    return best_question


def _question_sort_key(q: str) -> str:
    sn = extract_question_short_name(q)
    if sn:
        return sn
    # Questions with escaped colons in GIFT (::name\: ...) don't match the regex,
    # but their real name is in the comment line — use it so sort matches Moodle's modal.
    m = re.search(r"// question: \d+\s+name: (.+)", q)
    return m.group(1).strip() if m else ""


def get_numbers_page(parts: list, question_short_name: str) -> list:
    # Сортуємо лексикографічно — саме так Moodle відображає питання в банку
    sorted_parts = sorted(parts, key=_question_sort_key)

    groups = [sorted_parts[i:i+20] for i in range(0, len(sorted_parts), 20)]

    pages = []
    for i, group in enumerate(groups):
        for cell in group:
            if extract_question_short_name(cell) == question_short_name:
                pages.append(i)

    return sorted(set(pages))


def append_next_question_bank_page(
    pages_to_visit: list[int | None],
    visited_pages: set[int | None],
    max_qpage: int | None,
) -> bool:
    numeric_pages = [page for page in pages_to_visit if isinstance(page, int)]
    if not numeric_pages:
        return False

    next_page = max(numeric_pages) + 1
    if max_qpage is not None and next_page > max_qpage:
        return False
    if next_page in visited_pages or next_page in pages_to_visit:
        return False

    pages_to_visit.append(next_page)
    print(f"[insert_xml] still missing questions; will also check qpage={next_page}")
    return True
            

def insert_question(text:str, question_text: str, question_short_name: str, num_insert:int = 6) -> str:

    first_line = question_text.splitlines()[0]
    pattern = re.escape(first_line) + r"[\s\S]*?\}"
    insert_text = f"\n\n\n// question: 23920  name: {question_short_name}\\n::{question_short_name}::[html]ененененнене" + "{\n}"
    multipaled_insert_text = insert_text * num_insert
    match = re.search(pattern, text)

    if not match:
        raise ValueError("Питання у файлі не знайдено")

    insert_pos = match.end()
    text = text[:insert_pos] + multipaled_insert_text + text[insert_pos:]
    
    return text


def count_questions_to_insert(text: str, question_short_name: str | None = None) -> int:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        pattern = r"<question\s+type=['\"]multichoice['\"]"
        return len(re.findall(pattern, text))

    questions = [
        question
        for question in root.findall("question")
        if question.get("type") == "multichoice"
    ]
    if not question_short_name:
        return len(questions)

    matching_questions = [
        question
        for question in questions
        if (question.findtext("name/text") or "").strip() == question_short_name
    ]
    return len(matching_questions) if matching_questions else len(questions)


def save_updated_file(text, file_path):
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)
        


# --- checkpoint helpers ---

def _cp_path(code_subject: str, step: str):
    safe = code_subject.replace(" ", "_")
    return CHECKPOINT_DIR / f"{safe}_{step}.flag"

def checkpoint_done(code_subject: str, step: str) -> bool:
    return _cp_path(code_subject, step).exists()

def checkpoint_mark(code_subject: str, step: str, data: str = "") -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    _cp_path(code_subject, step).write_text(data, encoding="utf-8")

def checkpoint_read(code_subject: str, step: str) -> str:
    return _cp_path(code_subject, step).read_text(encoding="utf-8").strip()


def _create_quiz_and_get_id(url_activity: str, number_lesson: str) -> str:
    print(f"[insert_xml] create quiz url: {url_activity}")
    browser.get(url_activity)

    name_task = f"Тест до уроку {number_lesson}"
    set_input_value(
        [
            (By.ID, "id_name"),
            (By.NAME, "name"),
            (By.CSS_SELECTOR, "input[name='name']"),
            (By.XPATH, "//label[contains(., 'Name') or contains(., 'Назва')]/following::input[1]"),
            (By.XPATH, "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input"),
        ],
        name_task,
    )

    ensure_collapse_container_expanded("id_modstandardgradecontainer")
    set_input_value(
        [
            (By.ID, "id_gradepass"),
            (By.NAME, "gradepass"),
            (By.CSS_SELECTOR, "input[name='gradepass']"),
            (By.XPATH, "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[3]/div[2]/div[2]/div[2]/input"),
        ],
        "4",
    )

    select_questions_on_one_page()

    click_first(
        [
            (By.ID, "id_submitbutton2"),
            (By.ID, "id_submitbutton"),
            (By.CSS_SELECTOR, "input[type='submit'][name='submitbutton2']"),
            (By.CSS_SELECTOR, "input[type='submit'][name='submitbutton']"),
            (By.XPATH, "//input[@type='submit' and (contains(@value, 'Save') or contains(@value, 'Зберегти'))]"),
            (By.XPATH, "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/div[4]/div[2]/div[1]/div/div[2]"),
        ]
    )

    bank_questions_xpath = "/html/body/div[4]/div[5]/div/div[2]/nav/ul/li[5]/a"
    tools_moodle.wait_element(bank_questions_xpath)

    url_test = browser.current_url
    parsed_url = urlparse(url_test)
    params = parse_qs(parsed_url.query)
    id_value = params.get("id", [None])[0]
    return id_value or ""


def _import_questions(id_value: str) -> None:
    link_page_inport = f"{MOODLE_BASE_URL}/question/bank/importquestions/import.php?cmid={id_value}"
    browser.get(link_page_inport)

    click_first(
        [
            (By.ID, "id_format_xml"),
            (By.CSS_SELECTOR, "input[name='format'][value='xml']"),
            (By.XPATH, "//label[contains(., 'Moodle XML') or contains(., 'XML format') or contains(., 'XML')]"),
            (By.XPATH, "/html/body/div[4]/div[5]/div/div[3]/div/section/div[2]/form/fieldset[1]/div[2]/div/div[2]/div[1]/div/label[6]"),
        ]
    )

    click_first(
        [
            (By.CSS_SELECTOR, ".fp-btn-choose"),
            (By.CSS_SELECTOR, "input.fp-btn-choose"),
            (By.XPATH, "//input[contains(@class, 'fp-btn-choose') or contains(@value, 'Choose') or contains(@value, 'Вибрати')]"),
            (By.XPATH, "/html/body/div[4]/div[5]/div/div[3]/div/section/div[2]/form/fieldset[3]/div[2]/div[1]/div[2]/fieldset/div[2]/div[1]/input"),
        ]
    )

    sleep(1)
    file_input = wait_for_first([(By.NAME, "repo_upload_file"), (By.CSS_SELECTOR, "input[type='file']")])
    file_input.send_keys(str(TEST_OUTPUT_XML))

    click_first(
        [
            (By.CSS_SELECTOR, ".fp-upload-btn"),
            (By.XPATH, "//button[contains(@class, 'fp-upload-btn') or contains(., 'Upload') or contains(., 'Завантажити')]"),
            (By.XPATH, "/html/body/div[7]/div[3]/div/div[2]/div/div/div[2]/div/div[2]/div/div/div/button"),
        ]
    )

    click_first(
        [
            (By.ID, "id_submitbutton"),
            (By.CSS_SELECTOR, "input[type='submit'][name='submitbutton']"),
            (By.XPATH, "//input[@type='submit' and (contains(@value, 'Import') or contains(@value, 'Імпорт'))]"),
            (By.XPATH, "/html/body/div[4]/div[5]/div/div[3]/div/section/div[2]/form/fieldset[3]/div[2]/div[2]/div[2]/input"),
        ]
    )

    click_first(
        [
            (By.CSS_SELECTOR, "form button[type='submit']"),
            (By.CSS_SELECTOR, "form input[type='submit']"),
            (By.XPATH, "//button[contains(., 'Continue') or contains(., 'Продовжити')]"),
            (By.XPATH, "/html/body/div[4]/div[5]/div/div[3]/div/section/div[2]/div[4]/form/button"),
        ]
    )


def insert_test_in_moodle_from_XML(code_subject, number_lesson):

    if checkpoint_done(code_subject, "questions_added"):
        print(f"[checkpoint] {code_subject}: всі кроки вже виконано, пропускаємо")
        return

    path_file_code_subject = CODE_SUBJECT_TXT
    path_file_bank_quiz = QUESTION_BANK_FILE
    path_file_insert_quiz = TEST_OUTPUT_XML
    
    question_short_name = read_file(path_file_code_subject).strip()
    
    text_bank_quiz = read_file(path_file_bank_quiz)
    parts = split_text_into_parts(text_bank_quiz)
    
    pages = get_numbers_page(parts, question_short_name)
    
    text_insert_quiz = read_file(path_file_insert_quiz)
    
    question = find_question_exact(parts, question_short_name)
    
    if not question:
        prev_question = find_question_for_insert(parts, question_short_name)
        
        if prev_question:
            num_insert = count_questions_to_insert(text_insert_quiz, question_short_name)
            updated_text = insert_question(text_bank_quiz, prev_question, question_short_name, num_insert)
            save_updated_file(updated_text, path_file_bank_quiz)

            parts = split_text_into_parts(updated_text)
            pages = get_numbers_page(parts, question_short_name)
    
    print(f"Сторінки з питаннями для вставки: {pages}")


    
    
    
    


    
    
    
    
    # КРОК 1: створення тесту
    if checkpoint_done(code_subject, "quiz_created"):
        id_value = checkpoint_read(code_subject, "quiz_created")
        print(f"[checkpoint] quiz вже створено, id_value={id_value}")
    else:
        url_activity = create_quiz_url_for(code_subject)
        id_value = _create_quiz_and_get_id(url_activity, number_lesson)
        checkpoint_mark(code_subject, "quiz_created", id_value)
        print(f"[checkpoint] quiz створено, id_value={id_value}")

    # КРОК 2: імпорт питань у банк
    if checkpoint_done(code_subject, "questions_imported"):
        print("[checkpoint] питання вже імпортовано")
    else:
        _import_questions(id_value)
        checkpoint_mark(code_subject, "questions_imported")
        print("[checkpoint] питання імпортовано")


    sleep(1)
    # формуємо посилання на сторінку з імпортом питань для цього тесту
    url_question_task = f"{MOODLE_BASE_URL}/mod/quiz/edit.php?cmid={id_value}"
    browser.get(url_question_task)

    
    expected_question_count = count_questions_to_insert(text_insert_quiz, question_short_name)
    if expected_question_count <= 0:
        raise RuntimeError(f"No multichoice questions found in {path_file_insert_quiz}")

    selected_questions = read_existing_quiz_questions(code_subject)
    if selected_questions:
        print(
            f"[insert_xml] quiz already has {len(selected_questions)} "
            f"questions for {code_subject}"
        )
    pages_to_visit: list[int | None] = list(pages) if pages else [None]
    visited_pages: set[int | None] = set()
    numeric_start_pages = [page for page in pages_to_visit if isinstance(page, int)]
    max_qpage = max(numeric_start_pages) + 3 if numeric_start_pages else None
    page_index = 0

    while page_index < len(pages_to_visit):
        page = pages_to_visit[page_index]
        page_index += 1
        visited_pages.add(page)

        if len(selected_questions) >= expected_question_count:
            break

        browser.get(url_question_task)
        if page is not None:
            print(f"[insert_xml] opening question bank qpage={page}")

        open_quiz_add_menu()
        open_question_bank_modal_from_add_menu()
        navigate_question_bank_modal_to_page(page)

        remaining_count = expected_question_count - len(selected_questions)
        selected_on_page = select_lesson_questions_from_modal(
            code_subject,
            remaining_count,
            selected_questions,
        )

        if not selected_on_page:
            print(f"[insert_xml] no new questions on qpage={page}")
            close_question_bank_modal()
            if (
                len(selected_questions) < expected_question_count
                and page_index >= len(pages_to_visit)
                and append_next_question_bank_page(pages_to_visit, visited_pages, max_qpage)
            ):
                continue
            continue

        click_first(
            [
                (By.CSS_SELECTOR, ".modal.show form input[type='submit'][name='add']"),
                (By.CSS_SELECTOR, ".modal.in form input[type='submit'][name='add']"),
                (By.XPATH, "//div[contains(@class, 'modal') and contains(@class, 'show')]//input[@type='submit' and @name='add']"),
            ]
        )
        wait_for_modal_to_close()
        selected_questions.extend(selected_on_page)
        print(
            f"[insert_xml] added {len(selected_on_page)} from qpage={page}; "
            f"total={len(selected_questions)}/{expected_question_count}"
        )
        if (
            len(selected_questions) < expected_question_count
            and page_index >= len(pages_to_visit)
        ):
            append_next_question_bank_page(pages_to_visit, visited_pages, max_qpage)

    if len(selected_questions) != expected_question_count:
        # 0 відібрано (і в тесті нічого не було) → найімовірніше імпорт не наповнив
        # банк, а не транзитивний збій вибору. Скидаємо чекпойнт імпорту, щоб
        # наступна спроба зробила реімпорт, а не «залипла» на questions_imported.
        if len(selected_questions) == 0:
            _cp = _cp_path(code_subject, "questions_imported")
            if _cp.exists():
                _cp.unlink()
                print("[insert_xml] 0 відібрано → скинув чекпойнт questions_imported (наступна спроба реімпортує)")
        raise RuntimeError(
            f"Expected {expected_question_count} questions for {code_subject}, "
            f"selected {len(selected_questions)} across pages {pages_to_visit}"
        )

    sleep(2)
    
    url_test_xpath = "/html/body/div[4]/div[5]/div/div[2]/nav/ul/li[1]/a"
    
    url_test_element = browser.find_element(By.XPATH, url_test_xpath)
    url_test = url_test_element.get_attribute("href")
    print(f"url_test - {url_test}")

    with XML_URL_JSON.open("w", encoding="utf-8") as f:
        json.dump({"url": url_test, "code_subject": code_subject}, f, ensure_ascii=False, indent=4)

    checkpoint_mark(code_subject, "questions_added")
    print(f"[checkpoint] {code_subject}: питання додано до тесту")


def main() -> None:
    tree = ET.parse(TEST_OUTPUT_XML)
    root = tree.getroot()

    first_question = root.find("question")
    name_element = first_question.find("name/text") if first_question is not None else None
    quiz_title = name_element.text.strip() if name_element is not None else "Без назви"

    code_subject = quiz_title
    print(f"code_subject - {code_subject}")

    number_lesson = code_subject.split(" ")[-1]
    if "_" in number_lesson:
        number_lesson = number_lesson.replace("_", "-")
    insert_test_in_moodle_from_XML(code_subject, number_lesson)


if __name__ == "__main__":
    main()
