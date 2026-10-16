# Вставляє інформацію про інтегровані уроки в Excel-файл

import os
import json
import win32com.client as win32
import datetime
from paths import ID_ARTICLE_TXT, INFO_JSON, INTEGRATION_EXCEL_FILE, MOODLE_BASE_URL, NAME_ARTICLE_TXT


with ID_ARTICLE_TXT.open("r", encoding="utf-8") as file:
    id_article = file.read()

with NAME_ARTICLE_TXT.open("r", encoding="utf-8") as file:
    name_article = file.read()

excel_file_path = str(INTEGRATION_EXCEL_FILE)

name_lesson = name_article
url_lesson = f"{MOODLE_BASE_URL}/mod/page/view.php?id={id_article}"
date_done = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
day_done = datetime.datetime.now().strftime("%d")

# Код предмета беремо з info.json (code_subject = "НМ10 23") — частина до пробілу ("НМ10"),
# щоб не хардкодити під конкретний предмет.
with INFO_JSON.open("r", encoding="utf-8") as file:
    _code_subject_full = json.load(file).get("code_subject", "").strip()
code_subject = _code_subject_full.split()[0] if _code_subject_full else ""
if not code_subject:
    raise RuntimeError(f"code_subject не знайдено в {INFO_JSON}")


def update_open_excel(file_path, name_lesson, url_lesson, date_done, day_done, code_subject):
    excel = win32.GetActiveObject("Excel.Application")

    excel.Visible = True

    # якщо файл вже відкритий — беремо існуючий екземпляр
    wb = None
    for w in excel.Workbooks:
        if w.FullName.lower() == file_path.lower():
            wb = w
            break
    if wb is None:
        wb = excel.Workbooks.Open(file_path)

    ws = wb.ActiveSheet  # або wb.Worksheets("Назва аркуша")

    # знайти перший порожній НЕжовтий рядок (перевіряємо A-стовпець)
    row = 2
    while True:
        cell = ws.Cells(row, 1)  # A{row}
        # перевірка: порожня?
        is_empty = (cell.Value is None or str(cell.Value).strip() == "")

        # перевірка жовтого фону
        # Колір у COM — через Interior.ColorIndex (6 = жовтий у стандартній палітрі)
        is_yellow = (cell.Interior.ColorIndex == 6)

        if is_empty and not is_yellow:
            ws.Cells(row, 1).Value = name_lesson
            ws.Cells(row, 2).Value = url_lesson
            ws.Cells(row, 3).Value = date_done
            ws.Cells(row, 4).Value = day_done
            ws.Cells(row, 5).Value = code_subject

            ws.Range(ws.Cells(row, 3), ws.Cells(row, 5)).HorizontalAlignment = -4108  # xlCenter
            break

        row += 1

    wb.Save()

update_open_excel(excel_file_path, name_lesson, url_lesson, date_done, day_done, code_subject)
