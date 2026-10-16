# Architecture notes (Ukrainian): how the doc_to_html stack works

## 1. Вхідні дані

- **Google Doc** → читається через Google Docs API (`get_document_content(DOCUMENT_ID)`)
- **Ручна конфігурація у файлі** (треба міняти перед запуском):
  - `code_subject = "УМ3 162"` — предмет + номер уроку
  - `CURRENT_SUBJECT = "Українська мова"` — назва предмету (впливає на стилі)
  - `div_color` — колір акцентів
- **Кеш-файли** (`info/`, `h5p_cache/`) — проміжні дані між запусками

---

## 2. Структура Google Doc

Документ — це одна велика таблиця. Кожен рядок = один блок уроку. Колонки:

| col 0–2 | col 3 | col 4 |
|---------|-------|-------|
| Текст контенту | Зображення (назви файлів) | H5P задача (`=DT=`, header, text) |

Перша клітинка рядка (col 0) — заголовок блоку (Теорія, Практика, Інтерактив...).
Якщо вона спанується на всю ширину — це розділювач між блоками.

---

## 3. Глобальний стан-машина (прапорці блоків)

При обході рядків таблиці, глобальні булеві змінні кажуть "в якому блоці ми зараз":

```
IN_HELLO_BLOCK       → Привітання
IN_THEORY_BLOCK      → Теорія
IN_PRACTICE_BLOCK    → Практика
IN_INTERACTIVE_BLOCK → Інтерактив
IN_TEST_BLOCK        → Тест
IN_FINAL_BLOCK       → Фінал
IN_ADDITIONAL_BLOCK  → Додатки
```

Коли зустрічається рядок-заголовок (наприклад "Теорія") — скидає всі прапорці і ставить `IN_THEORY_BLOCK = True`. Весь подальший контент обробляється залежно від поточного прапорця — інші стилі, інша логіка нумерації, інші HTML-шаблони.

---

## 4. Потік обробки (головний цикл)

```
main()
  └─ get_document_content()         ← Google Docs API
  └─ for table in doc:
       └─ process_table_with_details(table)
            └─ for row in table:
                 ├─ extract_row_title(row)         ← чи це заголовок?
                 │    └─ якщо так → оновити прапорці блоку
                 │                → додати HTML-заголовок секції
                 │
                 ├─ process_cell(cells[0..2])      ← основний текст
                 │    └─ paragraph by paragraph:
                 │         ├─ форматування (жирний, курсив, колір, списки)
                 │         ├─ спецмаркери (!p, !=, ??, !!, заглушка...)
                 │         └─ стилізація залежно від IN_*_BLOCK
                 │
                 ├─ extract_image_title(cells[3])  ← назви картинок
                 │    └─ підставити <img> замість маркера *photo*
                 │
                 └─ get_h5p_task(cells[4])         ← дані для H5P
                      └─ зберегти в h5p_cache/{code_subject}.json
```

---

## 5. Пост-обробка (після циклу)

```
html_output →
  ├─ замінити заглушки h5p на реальний embed (якщо є кеш)
  ├─ замінити "Пройди тест до уроку" на посилання (якщо є xml_url.json)
  ├─ прибрати сміттєві символи (, ~~, ✔️...)
  └─ обгорнути в <div class="page-set">
       └─ записати в output.html

  ├─ записати code_subject.txt
  └─ view_xml.generate_html_xml()   ← генерує XML для Moodle
```

---

## 6. Стилі — де що лежить

`custom_styles[CURRENT_SUBJECT]` — словник HTML-шаблонів для кожного предмету:

```python
custom_styles["Українська мова"]["theory"]["paragraph"]    # абзац у теорії
custom_styles["Українська мова"]["practice"]["task_block"] # блок завдання
custom_styles["Українська мова"]["homework"]               # ДЗ
custom_styles["Українська мова"]["interactive"]["iframe"]  # iframe wordwall/youtube
```

`HEADER_RENAME_MAPPING` — словник перейменувань заголовків для кожного предмету
("Практика" → "Мудровміння" для укр.мови).

---

## 7. Скрипти стеку

| Скрипт | Роль | Вхід | Вихід |
|--------|------|------|-------|
| `doc_to_html.py` | Генерація HTML уроку + збір H5P задач | Google Doc, `code_subject` | `output.html`, `h5p_cache/*.json` |
| `create_article.py` | Вставляє HTML у сторінку Moodle | `output.html`, `id_article.txt` | Moodle page оновлено |
| `insert_photos.py` | Замінює назви файлів у редакторі на реальні фото | `id_article.txt`, `code_subject.txt`, папка `стокі з уроків\` | Фото завантажені у Moodle |
| `create_h5p.py` | Selenium → створює H5P у Moodle → зберігає embed HTML | `h5p_cache/{code_subject}.json` | `h5p_cache/{code_subject}.json` (з html_code) |
| `insert_xml_text.py` | Selenium → завантажує тест XML у Moodle → зберігає URL | `test_output.xml`, `code_subject.txt` | Тест у Moodle, `info/xml_url.json` |

---

## 8. Реальний порядок запуску

```
1. doc_to_html.py
   └─ дивишся що вийшло, перевіряєш HTML

2. create_h5p.py
   └─ створює H5P у Moodle, заповнює кеш

3. doc_to_html.py (повторно)
   └─ заглушки замінюються на реальні H5P embed

4. create_article.py
   └─ фінальний HTML заливається у Moodle

5. ┌─ insert_xml_text.py          ─┐
   └─ insert_photos.py  ─┘  (паралельно)
```

Чому саме так:
- `insert_xml_text.py` і `insert_photos.py` потребують щоб стаття вже існувала у Moodle
- Між собою не залежать → запускаються паралельно

---

## 9. Де найбільший біль при рефакторингу

- **Глобальний стан-машина** — прапорці розкидані по функціях, важко тестувати
- **Ручна конфігурація** — `CURRENT_SUBJECT`, `code_subject`, `div_color` треба міняти у коді
- **XPath-и** — жорстко прошиті, ламаються при оновленні Moodle
- **`custom_styles`** — один величезний словник на ~800 рядків, складно підтримувати

При переписуванні: спочатку винести конфігурацію у `config.json`,
замінити глобальний стан на явне передавання стану в функції.
