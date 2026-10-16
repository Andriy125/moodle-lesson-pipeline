# XPath changes

This document records Selenium locator changes made during the `pipeline`
refactor. The goal is to keep every UI automation change inspectable: what was
changed, why it was changed, and what fallback still exists.

## create_article.py

Purpose of the script: create a Moodle Page activity, fill the title, fill the
description, add placeholder page content, save, and write the created activity
id to `info/id_article.txt`.

### Page title field

Old primary locator:

```python
"/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input"
```

Problem:

- Absolute XPath depends on the full Moodle page layout.
- Any wrapper change, theme change, alert/banner, or block position shift can
  move `div[5]` or `fieldset[1]` and break the script.

New locator order:

```python
(By.ID, "id_name")
(By.NAME, "name")
(By.CSS_SELECTOR, "input[name='name']")
(By.XPATH, "//label[contains(., 'Name') or contains(., 'Назва')]/following::input[1]")
(By.XPATH, old_absolute_xpath)
```

Reason:

- `id_name` and `name=name` are Moodle form-field identifiers and should be much
  more stable than the visual DOM position.
- Label-based XPath survives some ID changes.
- The old XPath remains as last fallback for unexpected legacy markup.

### Description editor iframe

Old primary locator:

```python
"/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div/div[2]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/iframe"
```

Problem:

- The locator targets the rendered position of the editor, not the Moodle form
  field.
- TinyMCE/Atto/CKEditor wrappers can differ between Moodle versions or editor
  settings.

New locator order:

```python
(By.CSS_SELECTOR, "#id_introeditor iframe")
(By.CSS_SELECTOR, "iframe[id^='id_introeditor']")
(By.CSS_SELECTOR, "iframe.tox-edit-area__iframe")
(By.CSS_SELECTOR, "iframe.cke_wysiwyg_frame")
(By.XPATH, "//textarea[@name='intro']/ancestor::*[contains(@class, 'feditor') or contains(@class, 'editor_atto')]//iframe")
(By.XPATH, old_absolute_xpath)
```

Fallback if no iframe is present:

```python
(By.ID, "id_introeditoreditable")
(By.NAME, "intro")
(By.CSS_SELECTOR, "textarea[name='intro']")
```

Reason:

- Moodle description field is usually backed by `intro` / `id_introeditor`.
- TinyMCE uses `tox-edit-area__iframe`; CKEditor uses `cke_wysiwyg_frame`.
- If the rich editor is disabled, writing to the textarea is still possible.

### Page content placeholder

Old logic:

```python
browser.execute_script("try { tinymce.get('id_page').setContent('<p>.</p>'); } catch(e) {}")
```

Problem:

- Only works if TinyMCE is loaded and the page content editor has the exact
  editor id `id_page`.
- If Moodle uses a textarea or another editor wrapper, nothing is written.

New logic:

```python
if (window.tinymce && tinymce.get('id_page')) {
    tinymce.get('id_page').setContent('<p>.</p>');
}
const pageTextarea = document.querySelector(
    '#id_page, textarea[name="page[text]"], textarea[name="content"]'
);
if (pageTextarea) {
    pageTextarea.value = '<p>.</p>';
    pageTextarea.dispatchEvent(new Event('change', {bubbles: true}));
}
```

Reason:

- Keeps TinyMCE support.
- Adds textarea fallback.
- Dispatches `change` so Moodle/editor validation has a chance to see the new
  value.

### Save button

Old primary locator:

```python
"/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/div[4]/div[2]/div[1]/div/div[2]"
```

Problem:

- Points at a visual container near the button instead of the semantic submit
  control.
- Breaks if the Moodle form action buttons are reordered or wrapped.

New locator order:

```python
(By.ID, "id_submitbutton2")
(By.ID, "id_submitbutton")
(By.CSS_SELECTOR, "input[type='submit'][name='submitbutton2']")
(By.CSS_SELECTOR, "input[type='submit'][name='submitbutton']")
(By.CSS_SELECTOR, "button[type='submit'][name='submitbutton2']")
(By.CSS_SELECTOR, "button[type='submit'][name='submitbutton']")
(By.XPATH, "//input[@type='submit' and (contains(@value, 'Save') or contains(@value, 'Зберегти'))]")
(By.XPATH, old_absolute_xpath)
```

Reason:

- Moodle submit buttons normally have stable IDs/names.
- Text-based XPath catches localized button labels.
- The old absolute XPath remains only as last fallback.

## insert_photo_in_aritcle.py

Purpose of the script: open the newly created Moodle Page activity, insert
`output.html`, upload local lesson images into the page editor, and save the
page.

### Page edit URL

Old approach:

```python
tools_moodle.go_to_site(url_moodle)
tools_moodle.enable_edit_mode()
browser.get(f"https://moodle.example.com/course/modedit.php?update={id_lesson}&return=1")
```

Problem:

- The script depended on the course front page and edit-mode state before it
  went to the actual form.
- Auth and edit-mode preparation now belong to `pre_launch.py`.

New approach:

```python
browser.get(f"{MOODLE_BASE_URL}/course/modedit.php?update={article_id}&return=1")
wait().until(EC.presence_of_element_located((By.ID, "id_page")))
```

Reason:

- The Page edit form is addressed directly by the created activity id.
- `id_page` verifies that the script is on the page-content form before any
  write happens.

### Page HTML insertion

Old approach:

```python
instrument_btn_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div[2]/form/fieldset[2]/..."
source_code_div_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div[2]/form/fieldset[2]/..."
```

Problem:

- The script clicked through the TinyMCE source-code popup using absolute
  layout XPath.
- Any Moodle theme wrapper change moved the toolbar path.

New approach:

```javascript
const editor = window.tinymce && tinymce.get('id_page');
const textarea = document.querySelector('#id_page, textarea[name="page[text]"]');
editor.setContent(html);
editor.save();
textarea.value = html;
```

Reason:

- Moodle's page body editor is stable as `id_page`.
- TinyMCE API insertion avoids the source-code popup entirely.
- The textarea fallback keeps the script working if the rich editor changes or
  fails to initialize.

### Image placeholders

Old approach:

```python
ifrime_editor_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div[2]/form/fieldset[2]/..."
p_element_xpath = "/html/body/div/p[...]"
```

Problem:

- The script counted paragraphs by visual position.
- It could target the wrong paragraph if the generated HTML changed.

New approach:

```python
(By.CSS_SELECTOR, "#id_page_ifr")
(By.CSS_SELECTOR, "p.img_article")
```

Reason:

- Generated image placeholders already have `class="img_article"`.
- The script now uploads only paragraphs that explicitly look like image
  filenames.

### TinyMCE toolbar and image dialog

Old approach:

```python
center_editor_btn_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div[2]/form/fieldset[2]/..."
insert_img_editor_img_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div[2]/form/fieldset[2]/..."
```

New locator order:

```python
"#fitem_id_page button, .fitem_id_page button, #id_page_editor button"
button title / aria-label == "Image"
".drop-zone-fileinput"
".tiny_image_presentation"
".tiny_image_sizecustom"
".tiny_image_widthentry"
".tiny_image_heightentry"
".tiny_image_urlentrysubmit"
```

Reason:

- The Moodle/TinyMCE image dialog classes are tied to the image tool behavior,
  not to the outer page layout.
- The old centering click was removed because image positioning is handled by
  inserted HTML/CSS and the image dialog.

### Page save button

Old primary locator:

```python
"/html/body/div[5]/div[5]/div/div[3]/div/section/div[2]/form/div[4]/div[2]/div[1]/div/div[2]"
```

New locator order:

```python
(By.CSS_SELECTOR, "#id_submitbutton, input[name='submitbutton'], button[name='submitbutton']")
```

Reason:

- Uses Moodle's semantic submit button instead of a visual wrapper.
- The script now waits until the final URL is `mod/page/view.php`, so a wrong
  save target is caught.

## Next files to document

The following files still contain brittle Moodle XPath logic and should get the
same treatment when refactored:

- selected helpers inside `tools_moodle.py`

## create_h5p.py

Purpose of the script: create H5P content-bank activities from
`h5p_cache/<code_subject>.json`, save the Moodle view HTML, and write the
created content-bank URL back to the cache.

Current live-supported type:

```text
=DT= -> H5P.DragText 1.10
```

Other H5P markers are recognized, but live creation is intentionally blocked
until each type is tested against its current Moodle/H5P editor DOM.

### Content bank URL

Old approach:

```python
url_content_bank += "&plugin=h5p&library=H5P.DragText%201.10"
url_create_h5p = url_content_bank.replace("index.php", "edit.php")
```

Problem:

- The content-bank URL was mutated inside the loop.
- A second H5P item could inherit the previous item's `plugin`/`library`
  parameters.

New approach:

```python
create_url(bank_url, library)
```

Reason:

- The base `url_content_bank` from `info.json` stays immutable.
- Each item gets its own fresh edit URL.

### Existing-content check

Old locator:

```python
browser.find_element(By.CSS_SELECTOR, '[data-region="filearea"]')
```

Kept locator:

```python
(By.CSS_SELECTOR, "[data-region='filearea']")
```

Reason:

- This is already a semantic Moodle content-bank region.
- The refactor now wraps it in `open_content_bank()` and waits for the region
  before checking text.

### H5P editor iframe

Old locator:

```python
(By.CLASS_NAME, "h5p-editor-iframe")
```

Kept as:

```python
(By.CSS_SELECTOR, ".h5p-editor-iframe")
```

Reason:

- The H5P editor is isolated inside this iframe.
- The script now waits for the iframe after the edit page is fully loaded, then
  verifies the title field exists before writing.

### DragText title

Old locator:

```python
(By.ID, "field-extratitle--1")
```

Kept locator:

```python
(By.CSS_SELECTOR, "#field-extratitle--1")
```

Reason:

- This field is generated by the H5P DragText editor and was present in the
  live Moodle form.
- Values are now written via JavaScript plus `input/change` events, not only
  `send_keys`.

### DragText task description

Old approach:

```python
header_input_xpath = "/html/body/div/div[3]/div[2]/div[2]/div[2]"
write_text_in_cke_editor(header_input_xpath, header_h5p)
```

Problem:

- The field looked like CKEditor in older versions, but the live form exposes it
  directly as a contenteditable element.
- The absolute XPath was only a visual position inside the H5P iframe.

New locator:

```python
(By.ID, "field-taskdescription-16")
```

Reason:

- The live DragText editor exposes this element as
  `contenteditable="true"`.
- The setter still has a fallback for a classic CKEditor iframe if that appears
  later.

### DragText text field

Old locator:

```python
(By.ID, "field-textfield-17")
```

Kept locator:

```python
(By.CSS_SELECTOR, "#field-textfield-17")
```

Reason:

- This is the stable H5P DragText textarea for drop-zone text.
- Values are written with `input/change` events so the H5P editor detects the
  update.

### Save and result capture

Old approach:

```python
browser.find_element(By.ID, "id_submitbutton").click()
input("[create_h5p] H5P збережено → Enter → далі")
```

New approach:

```python
(By.ID, "id_submitbutton")
(By.CSS_SELECTOR, "[data-region='viewcontent-content']")
```

Reason:

- The submit button ID is stable on the Moodle content-bank edit form.
- The script now waits for the view region and stores `html_code`/`url_task`
  immediately, without manual pauses.

## insert_xml_text.py

Purpose of the script: create a Moodle Quiz activity, import generated Moodle
XML into the question bank, add imported questions to the quiz, and save the
quiz URL to `info/xml_url.json`.

### Subject-specific quiz create URLs

Old approach:

```python
if "УМ3" in code_subject:
    url_activity = "https://...add=quiz..."
```

Problem:

- Subject routing was embedded in the script.
- Page URLs, H5P URLs, and quiz URLs were spread across different files.
- Adding a new subject meant editing automation code.

New approach:

```json
{
  "УМ3": {
    "create_quiz_url": "https://moodle.example.com/course/mod.php?id=56&add=quiz&section=12&beforemod=0&sr=0"
  }
}
```

Location:

```text
config/subject_routes.json
```

Reason:

- Subject routes are pipeline state/config, not Selenium behavior.
- `insert_xml_text.py` now resolves `create_quiz_url` from the same config used
  by `create_article.py`.

### Quiz name field

Old primary locator:

```python
"/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input"
```

New locator order:

```python
(By.ID, "id_name")
(By.NAME, "name")
(By.CSS_SELECTOR, "input[name='name']")
(By.XPATH, "//label[contains(., 'Name') or contains(., 'Назва')]/following::input[1]")
(By.XPATH, old_absolute_xpath)
```

Reason:

- Same Moodle form pattern as `create_article.py`.
- Prefer stable form ids/names over full-page layout.

### Grade-to-pass field

Old primary locator:

```python
"/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[3]/div[2]/div[2]/div[2]/input"
```

New locator order:

```python
(By.ID, "id_gradepass")
(By.NAME, "gradepass")
(By.CSS_SELECTOR, "input[name='gradepass']")
(By.XPATH, old_absolute_xpath)
```

Before entering the value, the script now tries to open the grade fieldset with:

```python
(By.CSS_SELECTOR, "#id_modstandardgrade .ftoggler")
(By.CSS_SELECTOR, "fieldset#id_modstandardgrade legend")
(By.XPATH, "//fieldset[contains(@id, 'grade')]//legend")
```

Reason:

- Moodle form elements have stable ids.
- The fieldset click is best-effort only; if the section is already open, the
  script continues.

### Questions per page

Old primary locator:

```python
"/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[4]/div[2]/div[1]/div[2]/fieldset/div/div/span/select"
```

New locator order:

```python
(By.ID, "id_questionsperpage")
(By.NAME, "questionsperpage")
(By.CSS_SELECTOR, "select[name='questionsperpage']")
(By.XPATH, old_absolute_xpath)
```

Reason:

- Stable Moodle field id.
- Keeps the old XPath only as fallback.

Runtime correction:

- The grade/layout sections are now opened only when their collapse toggle has
  `aria-expanded="false"`. Blindly clicking the fieldset header could collapse
  an already-open section.
- The `questionsperpage` select is changed to value `"0"` through Selenium and
  then receives explicit `input` and `change` events.
- The selected value is verified before saving; if Moodle did not accept the
  one-page layout, the script fails before creating misleading downstream
  behavior.

Reason:

- During the `УМ3 173` test Moodle did not reliably keep the quiz layout as
  "one page". The old behavior made the later add-question step look broken
  even when the real issue was the quiz setting.

Live verification update:

- The real layout container on the Moodle quiz form is
  `id_layouthdrcontainer`, not `id_layout`.
- The grade container is `id_modstandardgradecontainer`.
- `aria-expanded` can report `true` while the container is still hidden, so the
  script now verifies `container.is_displayed()`.
- On `cmid=14358`, Moodle saved `id_questionsperpage` as value `"0"` and showed
  `Ніколи, усі запитання на одній сторінці` after reopening the edit form.

### Quiz save button

Old primary locator:

```python
"/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/div[4]/div[2]/div[1]/div/div[2]"
```

New locator order:

```python
(By.ID, "id_submitbutton2")
(By.ID, "id_submitbutton")
(By.CSS_SELECTOR, "input[type='submit'][name='submitbutton2']")
(By.CSS_SELECTOR, "input[type='submit'][name='submitbutton']")
(By.XPATH, "//input[@type='submit' and (contains(@value, 'Save') or contains(@value, 'Зберегти'))]")
(By.XPATH, old_absolute_xpath)
```

Reason:

- Clicks the actual submit control rather than a layout container.

### XML import format

Old primary locator:

```python
"/html/body/div[4]/div[5]/div/div[3]/div/section/div[2]/form/fieldset[1]/div[2]/div/div[2]/div[1]/div/label[6]"
```

New locator order:

```python
(By.ID, "id_format_xml")
(By.CSS_SELECTOR, "input[name='format'][value='xml']")
(By.XPATH, "//label[contains(., 'Moodle XML') or contains(., 'XML format') or contains(., 'XML')]")
(By.XPATH, old_absolute_xpath)
```

Reason:

- Selects the radio option by semantic Moodle field data first.
- The label-based XPath tolerates option order changes.

### File picker upload

Old primary locators:

```python
choose file: "/html/body/div[4]/div[5]/div/div[3]/div/section/div[2]/form/fieldset[3]/div[2]/div[1]/div[2]/fieldset/div[2]/div[1]/input"
upload:      "/html/body/div[7]/div[3]/div/div[2]/div/div/div[2]/div/div[2]/div/div/div/button"
```

New locator order:

```python
choose file:
(By.CSS_SELECTOR, ".fp-btn-choose")
(By.CSS_SELECTOR, "input.fp-btn-choose")
(By.XPATH, "//input[contains(@class, 'fp-btn-choose') or contains(@value, 'Choose') or contains(@value, 'Вибрати')]")

file input:
(By.NAME, "repo_upload_file")
(By.CSS_SELECTOR, "input[type='file']")

upload:
(By.CSS_SELECTOR, ".fp-upload-btn")
(By.XPATH, "//button[contains(@class, 'fp-upload-btn') or contains(., 'Upload') or contains(., 'Завантажити')]")
```

Reason:

- Moodle filepicker classes and input names are much more stable than modal
  `div[7]` positions.
- Removed fixed sleeps before finding the file input; now waits for the input.

### Import and continue buttons

Old primary locators:

```python
import:   "/html/body/div[4]/div[5]/div/div[3]/div/section/div[2]/form/fieldset[3]/div[2]/div[2]/div[2]/input"
continue: "/html/body/div[4]/div[5]/div/div[3]/div/section/div[2]/div[4]/form/button"
```

New locator order:

```python
import:
(By.ID, "id_submitbutton")
(By.CSS_SELECTOR, "input[type='submit'][name='submitbutton']")
(By.XPATH, "//input[@type='submit' and (contains(@value, 'Import') or contains(@value, 'Імпорт'))]")

continue:
(By.CSS_SELECTOR, "form button[type='submit']")
(By.CSS_SELECTOR, "form input[type='submit']")
(By.XPATH, "//button[contains(., 'Continue') or contains(., 'Продовжити')]")
```

Reason:

- Uses form submit controls and localized text instead of page layout.

### Add questions modal

Old approach:

```python
absolute_popup_xpath = f"/html/body/div[{tryes}]/div[2]/div/div/div[2]/div/div/div/div[2]/form/fieldset"
```

Problem:

- The modal index changes depending on previous modals, alerts, and page state.
- The script had to refresh and reconstruct modal paths repeatedly.

New approach:

```python
(By.XPATH, "//table[@id='categoryquestions']/ancestor::fieldset[1]")
(By.CSS_SELECTOR, ".modal.show form fieldset")
(By.CSS_SELECTOR, ".modal.in form fieldset")
```

Question rows are now read from:

```python
#categoryquestions tbody tr
```

Pagination is now read from:

```python
.modal.show .pagination li, .modal.in .pagination li
```

Reason:

- Anchors the modal logic to the question table `#categoryquestions`.
- Avoids guessing `div[6]`, `div[7]`, etc.
- Reduces repeated per-row waits by reading row cells directly from the table.

Runtime correction:

Old menu fallback:

```python
(By.CSS_SELECTOR, "a[data-action='addarandomquestion']")
```

Problem:

- This selects "випадкове питання" / random question, not "з банку питань".
- The modal then does not contain `#categoryquestions`, so the question-bank
  scan times out.

New menu locators:

```python
(By.CSS_SELECTOR, ".dropdown-menu a[data-action='questionbank']")
(By.XPATH, "//div[contains(@class, 'dropdown-menu')]//a[contains(., 'from question bank') or contains(., 'from the question bank') or contains(., 'банку питань')]")
(By.XPATH, old_absolute_a2_xpath)
```

The add menu itself is now opened by `open_quiz_add_menu()`, which prefers:

```python
.add-menu a.dropdown-toggle
[data-action='addquestion'] a.dropdown-toggle
```

Reason:

- Live DOM inspection on `cmid=14357` showed Moodle uses
  `data-action="questionbank"` for "з банку питань" and
  `data-action="addarandomquestion"` for "випадкове питання".
- The old absolute `a[2]` remains only as a last fallback because it matched the
  old script's behavior.

Live verification update:

- On `cmid=14358`, opening the quiz add menu showed:
  - `data-action="questionbank"` for `з банку питань`
  - `data-action="addarandomquestion"` for `випадкове питання`
- The imported `УМ3 173` questions appeared on `qpage=22`.
- The add-selected button is stable as:

```python
.modal.show form input[type='submit'][name='add']
```

- Six selected `УМ3 173` questions were added to `cmid=14358`; Moodle then
  showed `Питань: 6` and all six questions on `Сторінка 1`.
- Checkbox selection is now verified before submit: each matching row is clicked
  with JavaScript, rechecked with `is_selected()`, retried up to three times,
  and the script fails before submit unless exactly six lesson questions are
  selected.

### Speed changes

- Replaced several `sleep()` + absolute XPath waits with direct `WebDriverWait`
  on stable ids/classes.
- Removed per-row `tools_moodle.wait_element()` calls while scanning question
  rows; the table is waited once, then rows are inspected directly.
- File upload now waits for `repo_upload_file` instead of sleeping before the
  modal is ready.
