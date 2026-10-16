from __future__ import annotations

import json
import msvcrt
import mimetypes
import os
import re
import time
from pathlib import Path

import tools_moodle
from paths import ASSETS_DIR, ID_ARTICLE_TXT, INFO_JSON, MOODLE_BASE_URL, OUTPUT_HTML, STOCK_IMAGES_DIR
from pdf_to_image import convert_pdfs_to_images
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


browser = tools_moodle.browser
WAIT_SECONDS = 30
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
# Локальні відео з папки уроку вставляються через кнопку «Multimedia» редактора
# (окремий потік від картинок — див. upload_video).
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogv", ".mov", ".m4v"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
RESTART_EXIT_CODE = 75
# Коли крок виконує агент (оркестратор) — без інтерактивного msvcrt-ревʼю:
# редактор заповнюється і сторінка зберігається автоматично, а DOM-верифікацію
# агент робить уже по збереженій статті через браузер (порт 9222) і за потреби redo.
AGENT_MODE = os.environ.get("AGENT_MODE", "").strip() == "1"


def wait() -> WebDriverWait:
    return WebDriverWait(browser, WAIT_SECONDS)


def load_info() -> dict:
    with INFO_JSON.open(encoding="utf-8") as file:
        return json.load(file)


def read_article_id() -> str:
    article_id = ID_ARTICLE_TXT.read_text(encoding="utf-8").strip()
    if not article_id:
        raise RuntimeError(f"{ID_ARTICLE_TXT} is empty")
    return article_id


def lesson_number(info: dict) -> str:
    numbers = re.findall(r"\d+", info.get("code_subject", ""))
    if not numbers:
        raise RuntimeError("Cannot read lesson number from info/code_subject")
    return numbers[-1]


def class_folder(info: dict) -> str | None:
    first_token = info.get("code_subject", "").split()[0]
    match = re.search(r"\d+", first_token)
    if not match:
        return None
    return f"{match.group(0)} клас"


def existing_dirs(paths: list[Path]) -> list[Path]:
    return [path for path in paths if path.exists() and path.is_dir()]


def stock_image_subject(info: dict) -> str:
    """Базова назва предмета для теки стоків, без template-суфікса (напр. "510").
    insert_photo читає current_subject="Німецька мова 510" (для 510-шаблону рендера),
    але фото завантажуються/лежать у "Німецька мова" (photo_worker бере базову назву).
    Прибираємо трицифровий суфікс, інакше шлях не збігається і fallback rglob хапає
    однойменні файли з чужих папок."""
    subject = info.get("current_subject", "").strip()
    return re.sub(r"\s+\d{3}$", "", subject).strip()


def candidate_image_dirs(info: dict) -> list[Path]:
    subject = stock_image_subject(info)
    number = lesson_number(info)
    class_name = class_folder(info)
    allow_fallbacks = os.environ.get("INSERT_PHOTO_ALLOW_FALLBACKS", "").strip() == "1"

    candidates = []
    if subject and class_name:
        lesson_dir = STOCK_IMAGES_DIR / subject / class_name / number
        if not allow_fallbacks:
            if not lesson_dir.exists():
                print(f"[insert_photo] expected lesson image dir not found: {lesson_dir}")
            return existing_dirs([lesson_dir, ASSETS_DIR, STOCK_IMAGES_DIR])
        candidates.append(lesson_dir)
    if subject:
        candidates.append(STOCK_IMAGES_DIR / subject / number)
        candidates.append(STOCK_IMAGES_DIR / subject)
    candidates.extend([ASSETS_DIR, STOCK_IMAGES_DIR])
    return existing_dirs(candidates)


def index_images(dirs: list[Path]) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for folder in dirs:
        files = folder.rglob("*") if folder in {ASSETS_DIR, STOCK_IMAGES_DIR} else folder.glob("*")
        for path in files:
            if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS:
                index.setdefault(path.name, path)
    return index


def print_image_source_dirs(dirs: list[Path]) -> None:
    if not dirs:
        print("[insert_photo] image source dirs: none found")
        return

    print("[insert_photo] image source dirs:")
    for folder in dirs:
        print(f"  - {folder}")


def looks_like_image_name(text: str) -> bool:
    return Path(text.strip()).suffix.lower() in MEDIA_EXTENSIONS


def is_video_name(text: str) -> bool:
    return Path(text.strip()).suffix.lower() in VIDEO_EXTENSIONS


def open_edit_page(article_id: str) -> None:
    browser.get(f"{MOODLE_BASE_URL}/course/modedit.php?update={article_id}&return=1")
    wait().until(lambda driver: driver.execute_script("return document.readyState") == "complete")
    if "modedit.php" not in browser.current_url:
        raise RuntimeError(f"Expected modedit page, got {browser.current_url}")
    wait().until(EC.presence_of_element_located((By.ID, "id_page")))


def set_page_html(html: str) -> None:
    updated = browser.execute_script(
        """
        const html = arguments[0];
        const editor = window.tinymce && tinymce.get('id_page');
        const textarea = document.querySelector('#id_page, textarea[name="page[text]"]');

        if (editor) {
            editor.setContent(html);
            editor.save();
        }
        if (textarea) {
            textarea.value = html;
            textarea.dispatchEvent(new Event('input', {bubbles: true}));
            textarea.dispatchEvent(new Event('change', {bubbles: true}));
        }
        return Boolean(editor || textarea);
        """,
        html,
    )
    if not updated:
        raise RuntimeError("Cannot find Moodle page editor id_page")


def switch_to_page_iframe() -> None:
    browser.switch_to.default_content()
    iframe = wait().until(EC.presence_of_element_located((By.CSS_SELECTOR, "#id_page_ifr")))
    browser.switch_to.frame(iframe)


def find_image_placeholders() -> list[str]:
    switch_to_page_iframe()
    nodes = browser.find_elements(By.CSS_SELECTOR, "p.img_article")
    names = [node.text.strip() for node in nodes if looks_like_image_name(node.text)]
    browser.switch_to.default_content()
    return names


def select_placeholder(filename: str) -> bool:
    switch_to_page_iframe()
    selected = browser.execute_script(
        """
        const filename = arguments[0];
        const nodes = Array.from(document.querySelectorAll('p.img_article'));
        const node = nodes.find((item) => item.textContent.trim() === filename);
        if (!node) {
            return false;
        }
        node.scrollIntoView({block: 'center'});
        node.textContent = '';
        const range = document.createRange();
        range.selectNodeContents(node);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        node.focus();
        return true;
        """,
        filename,
    )
    browser.switch_to.default_content()
    return bool(selected)


def center_selected_placeholder() -> None:
    centered = browser.execute_script(
        """
        const editor = window.tinymce && tinymce.get('id_page');
        if (!editor) {
            return false;
        }

        editor.focus();
        try {
            editor.execCommand('JustifyCenter', false, null);
        } catch (error) {
            return false;
        }

        const node = editor.selection && editor.selection.getNode();
        const block = node && node.closest ? node.closest('p,div,figure') : node;
        if (block) {
            block.style.textAlign = 'center';
            block.setAttribute('data-mce-style', block.getAttribute('style') || 'text-align: center;');
        }
        editor.save();
        return true;
        """
    )
    if centered:
        return

    click_page_toolbar_button(
        "Align center",
        "Center",
        "Вирівняти по центру",
        "По центру",
        "Р’РёСЂС–РІРЅСЏС‚Рё РїРѕ С†РµРЅС‚СЂСѓ",
        "РџРѕ С†РµРЅС‚СЂСѓ",
    )


def click_page_toolbar_button(*titles: str) -> None:
    selector = "#fitem_id_page button, .fitem_id_page button, #id_page_editor button"
    buttons = wait().until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
    for button in buttons:
        title = (button.get_attribute("title") or "").strip()
        aria = (button.get_attribute("aria-label") or "").strip()
        if title in titles or aria in titles:
            browser.execute_script("arguments[0].click();", button)
            return
    raise RuntimeError(f"Cannot find page toolbar button: {titles}")


def wait_for_value(selector: str) -> str:
    def read_value(_driver):
        element = browser.find_element(By.CSS_SELECTOR, selector)
        value = element.get_attribute("value") or ""
        return value if value.strip() else False

    return wait().until(read_value)


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


def upload_image(filename: str, path: Path) -> None:
    if not select_placeholder(filename):
        print(f"[insert_photo] placeholder disappeared, skip: {filename}")
        return

    center_selected_placeholder()
    click_page_toolbar_button("Image")

    file_input = wait().until(EC.presence_of_element_located((By.CSS_SELECTOR, ".drop-zone-fileinput")))
    file_input.send_keys(str(path))

    presentation = wait().until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".tiny_image_presentation")))
    if not presentation.is_selected():
        browser.execute_script("arguments[0].click();", presentation)

    size_custom = wait().until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".tiny_image_sizecustom")))
    browser.execute_script("arguments[0].click();", size_custom)

    try:
        height = int(wait_for_value(".tiny_image_heightentry"))
    except (TimeoutException, ValueError):
        height = 0

    if height > 600 and "банер" not in filename.lower():
        set_input_value(".tiny_image_heightentry", "550")

    if any(part in filename for part in ("Показує", "Ручка", "Усміхається")):
        set_input_value(".tiny_image_widthentry", "200")

    submit = wait().until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".tiny_image_urlentrysubmit")))
    browser.execute_script("arguments[0].click();", submit)
    wait().until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".tox-dialog")))
    print(
        f"[insert_photo] uploaded: {filename} ({mimetypes.guess_type(path.name)[0] or 'image'}) "
        f"source: <- {path.parent}"
    )


def _first_present(selectors: tuple[str, ...], timeout: int = WAIT_SECONDS):
    """Перший елемент, що зʼявився за будь-яким із селекторів.
    Moodle-файлпікер має кілька варіантів розмітки залежно від версії/теми,
    тому не привʼязуємось до одного селектора."""
    end = time.time() + timeout
    while time.time() < end:
        for selector in selectors:
            elements = browser.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                if element.is_displayed():
                    return element
        time.sleep(0.3)
    raise TimeoutException(f"Не знайдено жодного з елементів: {selectors}")


def upload_video(filename: str, path: Path) -> None:
    """Локальне відео → кнопка «Multimedia» → вкладка Video → «Перегляд сховищ...»
    → завантаження файлу → «Insert media»."""
    if not select_placeholder(filename):
        print(f"[insert_photo] placeholder disappeared, skip: {filename}")
        return

    center_selected_placeholder()
    click_page_toolbar_button("Multimedia")

    # Вкладка «Video» у діалозі мультимедіа
    video_tab = _first_present(('a[href="#id_page_video"]', 'a[href*="_video"][data-toggle="tab"]'))
    browser.execute_script("arguments[0].click();", video_tab)

    # «Перегляд сховищ...» саме у панелі Video (у діалозі є така ж кнопка для audio)
    browse = _first_present((
        "#id_page_video .openmediabrowser",
        ".tab-pane.active .openmediabrowser",
        "button.openmediabrowser",
    ))
    browser.execute_script("arguments[0].click();", browse)

    # Файлпікер Moodle: репозиторій «Завантажити файл» + input[type=file]
    try:
        upload_repo = _first_present((
            ".fp-repo-area .fp-repo[title*='Завантажити']",
            ".fp-repo-area .fp-repo[title*='Upload']",
        ), timeout=5)
        browser.execute_script("arguments[0].click();", upload_repo)
    except TimeoutException:
        pass  # деякі теми одразу відкривають форму завантаження

    file_input = _first_present((
        ".fp-login-form input[type=file]",
        "input[name='repo_upload_file']",
        ".filepicker input[type=file]",
        ".moodle-dialogue-content input[type=file]",
    ))
    file_input.send_keys(str(path))

    submit_upload = _first_present((
        ".fp-upload-btn",
        ".fp-content .fp-upload-btn",
        ".moodle-dialogue-content button.fp-upload-btn",
    ))
    browser.execute_script("arguments[0].click();", submit_upload)

    # Після завантаження URL підставляється у поле діалогу — чекаємо на нього
    try:
        wait().until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".moodle-dialogue-content .fp-content")))
    except TimeoutException:
        pass

    insert_btn = _first_present((
        'button[data-action="save"]',
        ".modal-footer button.btn-primary",
    ))
    browser.execute_script("arguments[0].click();", insert_btn)
    print(f"[insert_photo] video inserted: {filename}  source: <- {path.parent}")


def is_page_editor_fullscreen() -> bool:
    return bool(
        browser.execute_script(
            """
            const editor = window.tinymce && tinymce.get('id_page');
            if (!editor) {
                return false;
            }
            return document.body.classList.contains('tox-fullscreen')
                || editor.getContainer().classList.contains('tox-fullscreen');
            """
        )
    )


def toggle_page_editor_fullscreen() -> bool:
    return bool(
        browser.execute_script(
            """
            const editor = window.tinymce && tinymce.get('id_page');
            if (!editor) {
                return false;
            }
            editor.focus();
            try {
                editor.execCommand('mceFullScreen');
                return true;
            } catch (error) {
                return false;
            }
            """
        )
    )


def enter_page_editor_fullscreen() -> None:
    if is_page_editor_fullscreen():
        return
    if not toggle_page_editor_fullscreen():
        print("[insert_photo] TinyMCE fullscreen command is not available")
        return
    try:
        wait().until(lambda _driver: is_page_editor_fullscreen())
        print("[insert_photo] editor fullscreen ON")
    except TimeoutException:
        print("[insert_photo] fullscreen did not activate, continuing with normal editor")


def exit_page_editor_fullscreen() -> None:
    if not is_page_editor_fullscreen():
        return
    toggle_page_editor_fullscreen()
    wait().until(lambda _driver: not is_page_editor_fullscreen())
    print("[insert_photo] editor fullscreen OFF")


def wait_for_review_action() -> str:
    print("\n[insert_photo] Перевір редактор у fullscreen.")
    print("Enter - save page  |  Ctrl+R - restart insert_photo  |  Ctrl+C - stop")
    while True:
        key = msvcrt.getch()
        if key in (b"\r", b"\n"):
            return "save"
        if key == b"\x12":
            return "restart"
        if key == b"\x03":
            raise KeyboardInterrupt
        if key in (b"\x00", b"\xe0"):
            msvcrt.getch()


def save_page() -> None:
    browser.execute_script(
        """
        const editor = window.tinymce && tinymce.get('id_page');
        if (editor) {
            editor.save();
        }
        """
    )
    submit = wait().until(
        EC.element_to_be_clickable(
            (
                By.CSS_SELECTOR,
                "#id_submitbutton, input[name='submitbutton'], button[name='submitbutton']",
            )
        )
    )
    browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit)
    browser.execute_script("arguments[0].click();", submit)
    wait().until(lambda driver: "mod/page/view.php" in driver.current_url)


def _lookup_drive_url_from_sheet(lesson_num: int) -> str:
    try:
        from run_pipeline_with_ai import read_sheet_rows
        for row in read_sheet_rows():
            if row.lesson == lesson_num:
                return row.drive_url
    except Exception as error:
        print(f"[insert_photo] spreadsheet lookup failed: {error}")
    return ""


def _ensure_photos_downloaded(info: dict) -> None:
    subject = stock_image_subject(info)
    class_name = class_folder(info)
    number = lesson_number(info)
    if not (subject and class_name):
        return

    lesson_dir = STOCK_IMAGES_DIR / subject / class_name / number
    if lesson_dir.exists() and any(
        item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS
        for item in lesson_dir.rglob("*")
    ):
        # Фото вже на місці, але PDF міг лишитись без картинки (напр. папку
        # качали до того, як зʼявилась конвертація). Ідемпотентно.
        convert_pdfs_to_images(lesson_dir)
        return

    lesson_num = int(number)
    print(f"[insert_photo] photos missing for lesson {lesson_num}, шукаю Drive URL у spreadsheet...")
    drive_url = _lookup_drive_url_from_sheet(lesson_num)
    if not drive_url:
        print(f"[insert_photo] Drive URL не знайдено — запусти download_photos_for_lesson.py вручну")
        return

    print(f"[insert_photo] downloading from Drive: {drive_url}")
    from run_pipeline_with_ai import DownloadStatus, LessonRow, photo_worker
    row = LessonRow(lesson=lesson_num, title="", document_id="", drive_url=drive_url, status="")
    status = DownloadStatus()
    photo_worker(row, status)
    if status.state == "error":
        print(f"[insert_photo] photo download failed: {status.error}")
    else:
        print(f"[insert_photo] downloaded {status.downloaded} photos to {lesson_dir}")


def insert_photo(article_id: str) -> None:
    start_time = time.time()
    info = load_info()
    _ensure_photos_downloaded(info)
    html = OUTPUT_HTML.read_text(encoding="utf-8")
    image_dirs = candidate_image_dirs(info)
    print_image_source_dirs(image_dirs)
    image_index = index_images(image_dirs)
    used_dirs: set[Path] = set()

    open_edit_page(article_id)
    set_page_html(html)

    placeholders = find_image_placeholders()
    print(f"[insert_photo] placeholders: {len(placeholders)}")

    for filename in placeholders:
        path = image_index.get(filename)
        if not path:
            print(f"[insert_photo] missing image, left placeholder: {filename}")
            continue
        used_dirs.add(path.parent)
        if is_video_name(filename):
            upload_video(filename, path)
        else:
            upload_image(filename, path)

    if used_dirs:
        print("[insert_photo] used image dirs:")
        for folder in sorted(used_dirs, key=lambda item: str(item).lower()):
            print(f"  - {folder}")

    enter_page_editor_fullscreen()
    if AGENT_MODE:
        # Агентний режим: не блокуємось на ручному ревʼю — зберігаємо автоматично.
        print("[insert_photo] AGENT_MODE: пропускаю ручне ревʼю, зберігаю сторінку")
    else:
        action = wait_for_review_action()
        if action == "restart":
            exit_page_editor_fullscreen()
            raise SystemExit(RESTART_EXIT_CODE)

    exit_page_editor_fullscreen()
    save_page()
    print(f"[insert_photo] done in {time.time() - start_time:.1f}s")
    print(f"url_article - {MOODLE_BASE_URL}/mod/page/view.php?id={article_id}")


if __name__ == "__main__":
    id_article = read_article_id()
    print(f"id_lesson - {id_article}")
    insert_photo(id_article)
