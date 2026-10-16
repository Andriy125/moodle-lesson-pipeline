# присираємо live оновлення файлу після редагування в Google Docs


import logging
import os
import html
import random
import re
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials  
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from xml.dom import minidom
from lxml import etree
import view_xml
import json
from time import sleep
import copy
from googleapiclient.discovery import build
from paths import (
    CODE_SUBJECT_TXT,
    DESCRIPTION_TXT,
    GOOGLE_CLIENT_SECRET_FILE,
    H5P_CACHE_DIR,
    INFO_JSON,
    NAME_ARTICLE_TXT,
    OUTPUT_HTML,
    SERVICE_ACCOUNT_FILE,
    SUBJECT_ROUTES_FILE,
    TEST_OUTPUT_XML,
    XML_URL_JSON,
)

  
# Налаштування логування
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SCOPES = ['https://www.googleapis.com/auth/documents.readonly']

PATH_SECRET_FILE = str(GOOGLE_CLIENT_SECRET_FILE)

CLIENT_SECRET_FILE = os.getenv('CLIENT_SECRET_FILE', PATH_SECRET_FILE)

DOCUMENT_ID = os.environ.get('GOOGLE_DOC_ID', '')
CURRENT_SUBJECT = os.environ.get("CURRENT_SUBJECT", "Українська мова")
code_subject = os.environ.get("CODE_SUBJECT", "")

# Перебиваємо значення з info.json якщо він є
_INFO_JSON = INFO_JSON
if _INFO_JSON.exists():
    with _INFO_JSON.open(encoding="utf-8") as _f:
        _info = json.load(_f)
    if "document_id" in _info:
        DOCUMENT_ID = _info["document_id"]
    if "code_subject" in _info:
        code_subject = _info["code_subject"]
    if "current_subject" in _info:
        CURRENT_SUBJECT = _info["current_subject"]
    print(f"[doc_to_html] info.json: code_subject={code_subject}, CURRENT_SUBJECT={CURRENT_SUBJECT}")


def homework_book_embed(code_subject: str) -> str:
    """iframe з книжкою BookCreator для домашнього завдання, якщо для предмета
    задано homework_book_url у subject_routes.json."""
    if not SUBJECT_ROUTES_FILE.exists():
        return ""
    routes = json.loads(SUBJECT_ROUTES_FILE.read_text(encoding="utf-8"))
    head = code_subject.split()[0] if code_subject else ""
    for key in (head, re.sub(r"[\d_]+$", "", head)):
        url = routes.get(key, {}).get("homework_book_url") if key else None
        if url:
            return (
                '<div style="max-width: 720px; margin: 20px 0;"><iframe style="border: 0px; '
                f'width: 100%; height: 600px;" src="{html.escape(url, quote=True)}" '
                'allowfullscreen="allowfullscreen"></iframe></div>'
            )
    return ""

# Норма тесту залежить від класу, а не від предмета:
#   • 1 клас (УМ1) — 4 питання по 2.5 бала        = 10
#   • решта       — 6 питань: 5×1.6 + останнє 2   = 10
# CURRENT_SUBJECT для УМ1 і УМ3 однаковий («Українська мова»), тому
# розрізняємо саме за кодом уроку.
IS_GRADE_1 = bool(code_subject) and code_subject.split()[0].upper() == "УМ1"
QUIZ_EXPECTED_QUESTIONS = 4 if IS_GRADE_1 else 6
QUIZ_GRADE_GRADE_1 = "2.5"


YELLOW ="#FCD01F" # Жовтий
PINK ="#E9629E" # Розовий
BLUE ="#3C398C" # Синій
GREEN ="#00A676" 
RED ="#B3261E" # Червоний
RED ="#C71F37" # Червоний
RED ="#E11A1C" # Червоний


div_color = PINK


IN_HELLO_BLOCK = False
IN_THEORY_BLOCK = False
FACT_BLOCK = False
IN_EXAMPLE_BLOCK = False
IN_PRACTICE_BLOCK = False
IN_INTERACTIVE_BLOCK = False  # Прапорець для інтерактивного блоку
IN_TEST_BLOCK = False
AFTER_TEST_BLOCK = False
IN_ADDITIONAL_BLOCK = False
IN_FINAL_BLOCK = False


IN_REDACTORII_BLOCK = False

# Назва секції, яку треба пропустити як перший елемент контенту (щоб уникнути дублювання)
SKIP_SECTION_HEADER_NAME = ""


# Літмережа у укр літературі
LITWEB_BLOCK = False

# в українській літературі є блок Цитатоскоп / Мемоскоп 
# це для стилізації
TERM_MEMO_BLOCK  = False


FULL_WIDTH_HEADERS_COUNT = 0

BANER_NAME = "Банер.png"
CART_NAME = "1-карта.png"

# Словник для мапінгу заголовків для предмету "Пізнаємо природу"
if CURRENT_SUBJECT == "Пізнаємо природу":
    HEADER_RENAME_MAPPING = {
        "Теорія": "Точка зустрічі з цікавим",
        "Приклади": "Зрозумій через приклади",
        "Практика": "Кроки до майстерності",
        "Інтерактив": "Інтерактивний майданчик",
        "Додатки": "ІнфоСкарб",
        "Фінал": "Ось і фініш"
    }

# укр мова
if CURRENT_SUBJECT == "Українська мова":
    HEADER_RENAME_MAPPING = {
        "Привітання": "Привітання",
        "Теорія": "Територія теорії",
        "Територія теорії": "Територія теорії",
        "Мрійко-пригадайко": "Мрійко-пригадайко",
        "Приклади": "Зрозумій через приклади",
        "Фактотека": "Фактотека",
        "Практика": "Мудровміння",
        "Інтерактив": "Взаємодійка",
        "Взаємодійка": "Взаємодійка",
        "Редакторій ": "Редакторій ",
        "Редакторій": "Редакторій",
        "Додатки": "Додатки",
        "Мемоскоп": "Мемоскоп",
        "Цитатоскоп": "Цитатоскоп",
        "Емоційний фейс-контроль": "Емоційний фейс-контроль",
        "Фінал": "Фінал"
    }

# Укр літ
if CURRENT_SUBJECT == "Українська література":
    HEADER_RENAME_MAPPING = {
        "Територія теорії": "Територія теорії",
        "Теорія": "Територія теорії",
        "Мрійко-пригадайко": "Мрійко-пригадайко",
        "Приклади": "Зрозумій через приклади",
        "Мудровміння": "Мудровміння",
        "Практика": "Мудровміння",
        "Фактотека": "Фактотека",
        "Інтерактив": "Взаємодійка",
        "Взаємодійка": "Взаємодійка",
        "Літмережа": "Літмережа",
        "Додатки": "Додатки",
        "Мемоскоп": "Мемоскоп",
        "Цитатоскоп": "Цитатоскоп",
        "Цитатоскоп / Мемоскоп": "Цитатоскоп",
        "Емоційний фейс-контроль": "Емоційний фейс-контроль",
        "Фінал": "Емоційний фейс-контроль"
    }


# }

# Німецька мова 11 клас
if CURRENT_SUBJECT == "Німецька мова" or CURRENT_SUBJECT == "Математика" or CURRENT_SUBJECT == "Зарубіжна література":
    HEADER_RENAME_MAPPING = {
        # "Привітання": "Привітання",
        "Теорія": "Теорія",
        "Приклади": "Приклади",
        "Практика": "Практика",
        "Словник": "Словник",
        "Інтерактив": "Інтерактив",
        "Додатки": "Додатки",
        "Фінал": "Фінал"
    }

# Німецька мова 5 - 10 клас
if CURRENT_SUBJECT == "Німецька мова 510":
    HEADER_RENAME_MAPPING = {
        "Привітання": "Привітання",
        "Теорія": "Секрети мови",
        "Теорія лонгрід": "Секрети мови",
        "Теорія презентація": "Секрети мови",
        "повторення": "Швидке оновлення",
        "Швидке оновлення": "Швидке оновлення",
        "Приклади": "Мова в дії",
        "Практика": "Deutsch Minuten",
        "Словник": "Ключі до мови",
        "Ключі до мови": "Ключі до мови",
        "Інтересанте факт": "Інтересанте факт",
        "Цікавий факт": "Інтересанте факт",
        "Інтерактив": "Spiel Spaß!",
        "Рефлексія": "Meine Möglichkeiten",
        "Додатки": "Andere",
        "Фінал": "Finale"
    }

if CURRENT_SUBJECT == "Історія України":
    HEADER_RENAME_MAPPING = {
        "Теорія": "Приготуй мозок до пригод!",
        "Теорія ВІДЕО": "Приготуй мозок до пригод!",
        "Теорія ЛОНГРІД": "Приготуй мозок до пригод!",
        # "Мрійко-пригадайко": "Мрійко-пригадайко",
        "Приклади": "Зрозумій через приклади",
        "Важливі дати та події": "Важливі дати та події",
        "Робота з картою": "Робота з картою",
        "Словник": "Мовний архів",
        "Практика": "Кроки до майстерності",
        "Інтерактив": "Взаємодійка",
        "Додатки": "ІнфоСкарб",
        "Фінал": "Фінішна пряма"
    }


# custom_styles = {
all_styles = {

# Шапка
# шапка з Пізнаємо природу
    "theory_header": """<div class="title" style="padding-block: 90px 4px; text-align: center;">
<div style="background-color: #eaf0ff; display: inline-block; padding: 10px 30px; border-radius: 50px; font-size: clamp(24px, 5vw, 40px); font-weight: bold; color: #3c398c; font-family: 'DreamSchoolBold', sans-serif;">{header_text}</div>
</div>
""",

# Українська мова
# Українська література
    "theory_header_double_color": """<div class="title" style="position: relative; display: inline-block; text-align: center; padding: 20px 0; margin-block-start: 90px;"><!-- Рожева підкладка -->
<div style="position: absolute; top: 23px; left: 50%; transform: translateX(-50%) rotate(5deg); background-color: #e9629e; border-radius: 10px; height: 60px; width: calc(100% - 10px); max-width: 400px; z-index: 1;">&nbsp;</div>
<!-- Синій блок -->
<div style="position: relative; background-color: #3c398c; color: white; font-size: 30px; font-weight: bold; padding: 10px 20px; font-family: 'DreamSchoolBold', sans-serif; border-radius: 10px; z-index: 2;">{header_text}</div>
</div>
""",
    "theory_header_double_color_center": """
<hr>
<div class="title" style="text-align: center;">
<div style="position: relative; display: inline-block; text-align: center; padding: 20px 0; margin-block-start: 45px;"><!-- Рожева підкладка -->
<div style="position: absolute; top: 23px; left: 50%; transform: translateX(-50%) rotate(5deg); background-color: #e9629e; border-radius: 10px; height: 60px; width: calc(100% - 10px); max-width: 400px; z-index: 1;">&nbsp;</div>
<!-- Синій блок -->
<div style="position: relative; background-color: #3c398c; color: white; font-size: 30px; font-weight: bold; padding: 10px 20px; font-family: 'DreamSchoolBold', sans-serif; border-radius: 10px; z-index: 2;">{header_text}</div>
</div>
</div>
""",

# Зарубіжна література
    "theory_simple_circle": """<div class="title" style="padding-block: 90px 4px; text-align: center;">
<div style="background-color: #e8eaf6; padding: 10px 30px;border-radius: 20px;font-size: clamp(24px, 5vw, 40px);border: 2px solid #3C398C;font-weight: bold;color: #3C398C;font-family: 'DreamSchoolBold', sans-serif;">
{header_text}</div>
</div>
""",
# Математика
    "theory_math": """<div class="title" style="margin-bottom: 20px; margin: auto; margin-block-start: 90px;">
<h2 style="font-size: 44px; text-align: center; color: #2980b9;" ><span style="background-color: rgb(60, 56, 140); color: rgb(255, 255, 255); padding: 5px 15px; border-radius: 8px; display: inline-block;">
{header_text}</span></h2>
</div>
""",




    "theory_unordered_item": """
    <div class="notice custom_ul" style="position: relative; border-radius: 15px; padding: 5px 0; color: #4a4a4a; max-width: 720px; margin-left: 0px;">
    <!-- Кружечок -->
    <div style="position: absolute; top: 16px; left: 30px;">
        <div style="background-color:{main_color}; min-width: 8px; height: 8px; border-radius: 50%; margin-right: 10px;">&nbsp;</div>
    </div>
    <!-- Текстовий блок -->
    <div style="padding-left: 56px; font-size: 18px; line-height: 1.66;">{item_text}</div>
</div>

""",



    "theory_ordered_item": """
    <div class="notice custom_ol" style="position: relative; border-radius: 15px; padding: 16px 0; color: #4a4a4a; max-width: 720px; margin-left: 0px;">
  <div style="display: flex; align-items: baseline;">
    <div style="background-color: {main_color}; color: #ffffff; min-width: 30px; height: 30px; display: flex; font-family: 'DreamSchoolBold', sans-serif; justify-content: center; align-items: center; border-radius: 50%; font-size: 16px; margin-right: 10px;">
      <strong>{number}</strong>
    </div>
    <div style="line-height: 1.66;">{item_text}</div>
  </div>
</div>
""",


    "theory_paragraph": "<p>{text}</p>\n",
    "default_header": "<h2>{header_text}</h2>\n",
    "default_unordered_item": "<li><p>{item_text}</p></li>\n",
    "default_ordered_item": "<p>{number}. {item_text}</p>\n",
    "default_paragraph": "<p>{text}</p>\n",

    "ordered_item_)": "<p>{number}) {item_text}</p>\n",


# Історія України
"theory_history": """<div class="title" style="margin: 90px auto 20px; background-color: #e9629e; border-radius: 150px; font-family: 'DreamSchoolBold', sans-serif;">
<h2 style="text-align: center; color: #ffffff; padding: 15px 15px; border-radius: 8px; font-size: 35px; margin-block: 0;" >{header_text}</h2>
</div>
""",


# Цитати
 
 
"quote": """
<div class="term_beautifule" style=" text-align: center;">
<div style="position: relative;display: inline-block;/* text-align: center; */padding: 10px 0;margin: 40px auto;max-width: 720px;margin-left: 20px;"><!-- Рожева підкладка -->
<div style="position: absolute; top: -5px; left: 47%; transform: translateX(-50%); background-color: #3c398c; border-radius: 20px; height: calc(90% - 10px); width: calc(100% - 0px); z-index: 1;">&nbsp;</div>
<!--
    Синій блок -->
<div style="position: relative;background-color: #ffffff;font-family: 'Montserrat',sans-serif !important;color: #000000;font-size: 16px;padding: 10px 20px;border-radius: 20px;border: 2px solid #3c398c;z-index: 2;display: inline-block;">
<div>{text}</div>
<strong id="docs-internal-guid-70453711-7fff-6c55-75f5-d1dea724fb2a"></strong></div>
<!-- Жовті крапки зверху -->
<div style="position: absolute; top: -25px; left: 10px; display: flex; gap: 5px;">
<div style="width: 10px; height: 10px; background-color: #f8c71f; border-radius: 50%;">&nbsp;</div>
<div style="width: 10px; height: 10px; background-color: #f8c71f; border-radius: 50%;">&nbsp;</div>
<div style="width: 10px; height: 10px; background-color: #f8c71f; border-radius: 50%;">&nbsp;</div>
</div>
<!-- Жовті крапки знизу -->
<div style="position: absolute; bottom: -10px; right: 10px; display: flex; gap: 5px;">
<div style="width: 10px; height: 10px; background-color: #f8c71f; border-radius: 50%;">&nbsp;</div>
<div style="width: 10px; height: 10px; background-color: #f8c71f; border-radius: 50%;">&nbsp;</div>
<div style="width: 10px; height: 10px; background-color: #f8c71f; border-radius: 50%;">&nbsp;</div>
</div>
</div>
</div>
""",
 
 
 
# Пізнаємо природу   
    
    "term": """
<div class="term" style="text-align: center;">    
    <div style="text-align: center; margin: 40px 20px; font-family: 'Montserrat',sans-serif !important;">
    <!-- Лінія -->
    <div
        style="width: 100px; height: 5px; background-color: #e9629e; margin: 0 auto 15px auto; border-radius: 2px;">
        </div>
        <!-- Текст -->
        <div
        style="font-size: 24px; line-height: 1.5; margin: 0; font-style: italic;">
        {text}  
        </div>
    </div>
</div>
""",

# Українська мова, література
    "term_circle": """<div class="term_circle" style="text-align: center; margin: 40px auto; border: 4px #E9629E solid; padding: 15px; border-radius: 25px;">
<p style="font-size: 24px; line-height: 1.5; margin: 0;">{text}</p>
</div>
""",

"term_circle_PP": """<div class="term_circle" style="text-align: center; margin: 40px auto; border: 4px #3C398C solid; padding: 15px; border-radius: 60px;">
<p style="font-size: 24px; line-height: 1.5; margin: 0; color: #3C398C;">{text}</p>
</div>
""",


# Зарубіжна література



"term_beautifule": """
<div class="term_beautifule" style=" text-align: center;">
<div style="
    justify-content: center;
    margin: auto;
">
<div style="position: relative;display: inline-block;text-align: center;padding: 10px 0;margin: 40px auto;max-width: 720px; margin-left: 20px;"><!-- Рожева підкладка -->
<div style="position: absolute; top: -5px; left: 47%; transform: translateX(-50%); background-color: #3c398c; border-radius: 20px; height: calc(90% - 10px); width: calc(100% - 0px); z-index: 1;">&nbsp;</div>
<!--
    Синій блок -->
<div style="position: relative; background-color: #ffffff; font-family: 'Montserrat',sans-serif !important; color: #000000; font-size: 24px; padding: 10px 20px; border-radius: 20px; border: 2px solid #3c398c; z-index: 2; display: inline-block;">
<div>{text}</div>
</div>
<!-- Жовті крапки зверху -->
<div style="position: absolute; top: -25px; left: 10px; display: flex; gap: 5px;">
<div style="width: 10px; height: 10px; background-color: #f8c71f; border-radius: 50%;">&nbsp;</div>
<div style="width: 10px; height: 10px; background-color: #f8c71f; border-radius: 50%;">&nbsp;</div>
<div style="width: 10px; height: 10px; background-color: #f8c71f; border-radius: 50%;">&nbsp;</div>
</div>
<!-- Жовті крапки знизу -->
<div style="position: absolute; bottom: -10px; right: 10px; display: flex; gap: 5px;">
<div style="width: 10px; height: 10px; background-color: #f8c71f; border-radius: 50%;">&nbsp;</div>
<div style="width: 10px; height: 10px; background-color: #f8c71f; border-radius: 50%;">&nbsp;</div>
<div style="width: 10px; height: 10px; background-color: #f8c71f; border-radius: 50%;">&nbsp;</div>
</div>
</div>
</div>
</div>
<br>
""",

# Математика
"term_simple_border": """<div class="term" style="text-align: center; margin: 40px auto; border: 4px #E9629E solid; padding: 15px; border-radius: 25px;">
<p style="font-size: 24px; line-height: 1.5; margin: 0;">{text}</p>
</div>""",


# Приклади
# Зарубіжна література
"example": """<div style="position: relative; background-color: #eaf0ff; border-radius: 15px; padding: 20px; font-family: 'Montserrat', sans-serif; color: #4a4a4a; max-width: 720px; margin: 50px auto; margin-left: 20px;"><!-- Круглий номер -->
<div style="position: absolute; top: -5px; left: -15px; transform: translateY(-50%); background-color: #3c398c; color: #ffffff; width: 40px; height: 40px; display: flex; justify-content: center; align-items: center; border-radius: 50%; font-size: 18px; font-weight: bold; font-family: 'DreamSchoolBold', sans-serif;">{number}</div>
<!-- Текстовий блок -->
<div style="font-size: 18px; line-height: 1.6;">{text}</div>
</div>
""",


# Інтерактив

    "interactive_instruction": """<h3 style="text-align: left; font-size: 26px; color: #3c398c; font-family: 'DreamSchoolBold'; margin-block: 40px 8px;"><strong>{instruction_text}</strong></h3>""",
    "interactive_iframe": """<div style="max-width: 720px; margin: 40px 0;"><iframe style="border: 0px; width: 100%; height: 500px;" src="{src_url}" allowfullscreen="allowfullscreen"></iframe></div>""",
    
    
# Домашнє завдання 
"homework": """<div class="notice homework_block"
  style="position: relative; background-color: #f9dce7; border-radius: 15px; padding: 20px; color: #4a4a4a; max-width: 720px; margin: 40px auto; margin-left: 20px;">
  <!-- піктограма -->
  <div style="position: absolute; top: -20px; left: -20px;"><img
      class="img-fluid" role="presentation"
      src="https://moodle.example.com/pluginfile.php/19796/mod_page/content/4/IMG_2368.PNG"
      alt="" width="60" height="69"></div>
  <!-- Текстовий блок -->
  <h3 style="padding-left: 20px; font-size: 26px; line-height: 1.66;">Домашнє
    завдання:</h3>
  <div
    style="padding-left: 20px; font-size: 18px; line-height: 1.66; margin: 20px 0 10px 0;">
    {text}</div>
</div>
""",


# 1 клас

# 3 клас

# 5 клас, фото


# 6 клас

# Завдання 

    "task": """<div class="notice task_block"
  style="position: relative; background-color: #d8f5e6; border-radius: 15px; padding: 25px; color: #202b58; max-width: 720px; margin: 40px auto; justify-content: center; flex-direction: column; align-content: center; align-items: center;">
  <!-- Круглий номер -->
  <div style="display: flex; justify-content: center; padding-bottom: 20px;">
    <div
      style="background-color: #202b58; color: #ffffff; width: 200px; height: 40px; display: flex; justify-content: center; align-items: center; border-radius: 25px; font-size: 18px; font-weight: bold;">
      Завдання 1</div>
  </div>
  <!-- Текстовий блок -->
  <div
    style="font-size: 18px; line-height: 1.66; display: flex; justify-content: flex-start; flex-direction: column;">
    <div>{text}</div>
  </div>
</div>
""",

# Українська література
    "task_1": """<div style="position: relative;background-color: #ddebff;border-radius: 15px;padding: 20px;font-family: 'Montserrat', sans-serif;color: #4a4a4a;max-width: 720px;margin: 50px auto;margin-left: 10px;"><!-- Круглий номер -->
<div style="position: absolute; top: -5px; left: -15px; transform: translateY(-50%); background-color: #e9629e; color: #ffffff; width: 40px; height: 40px; display: flex; justify-content: center; align-items: center; border-radius: 50%; font-size: 18px; font-weight: bold;">{number_task}</div>
<!-- Текстовий блок -->
<div style="padding-left: 20px; font-size: 18px; line-height: 1.66;">{text}</div>
</div>
""",

# Зарубіжна література
"task_2":"""
<div class="notice task_block" style="position: relative;background-color: #DDEBFF;border-radius: 15px;padding: 25px;color: #4a4a4a;max-width: 720px;margin: 40px auto;margin-left: 20px;padding-top: 40px;margin-top: 60px;"><!-- Круглий номер -->
<div style="position: absolute;top: 0;left: -20px;transform: translateY(-50%);background-color: #202B58;color: #ffffff;width: 200px;height: 40px;display: flex;justify-content: center;align-items: center;border-radius: 25px;font-size: 18px;font-weight: bold;">Завдання 1</div>
<!-- Текстовий блок -->
<div style="font-size: 18px; line-height: 1.66;">{text}</div>
</div>""",

# Математика
"task_3":"""<div class="notice task_block" style="position: relative; background-color: #fff4e1; border-radius: 15px; padding: 25px; color: #202b58; max-width: 720px; margin: 40px auto; margin-left: 20px; padding-top: 40px; margin-top: 60px;"><!-- Круглий номер -->
<div style="position: absolute; top: 0; left: -20px; transform: translateY(-50%); background-color: #502274; color: #ffffff; width: 200px; height: 40px; display: flex; justify-content: center; align-items: center; border-radius: 25px; font-size: 18px; font-weight: bold;">Завдання 1</div>
<div style="font-size: 18px; line-height: 1.66;">{text}</div>
</div>""",


# Історія України
"task_header":"""
<h3 style="text-align: left; font-size: 26px; color: #3c398c; font-family: 'DreamSchoolBold'; margin-block: 32px 16px;">Завдання {number_task}</h3>
{text}
""",


# Украхнська мова 2
"task_ukr_2":"""
<div class="notice task_block" style="position: relative; background-color: #f7ea86; border-radius: 15px; padding: 25px; color: #4a4a4a; max-width: 720px; margin: 40px auto; margin-left: 20px; padding-top: 40px; margin-top: 60px;"><!-- Круглий номер -->
<div style="position: absolute; top: 0; left: -20px; transform: translateY(-50%); background-color: #e9629e; color: #ffffff; width: 200px; height: 40px; display: flex; justify-content: center; align-items: center; border-radius: 25px; font-size: 18px; font-weight: bold;">Завдання {number_task}</div>
<!-- Текстовий блок -->
<div style="font-size: 18px; line-height: 1.66;">
<p>{text}</p>
</div>
</div>
""",


# Відповіді

"answer":"""
<details class="answer" style="background-color: #eaf0ff; padding: 20px; border-radius: 15px; color: #3c398c; font-family: 'DreamSchoolBold';">
<summary style="font-size: 20px;">Відповідь</summary>
<div style="padding-left: 20px; font-size: 18px; line-height: 1.66; color: #4a4a4a; font-family: 'Montserrat',sans-serif!important;">
{text}
</div>
</details>""",

"answer_open":"""
<details class="answer" style="background-color: #eaf0ff; padding: 20px; border-radius: 15px; color: #3c398c; font-family: 'DreamSchoolBold';" open="">
<summary style="font-size: 20px;">Відповідь</summary>
<div style="padding-left: 20px; font-size: 18px; line-height: 1.66; color: #4a4a4a; font-family: 'Montserrat',sans-serif!important;">
{text}
</div>
</details>""",

# Стилізоване питання
"question":"""
<div class="notice question" style="position: relative; background-color: #f4ebff; border-radius: 15px; padding: 20px; color: #4a4a4a; max-width: 720px; margin: 40px auto 40px 20px;"><!-- Круглий номер -->
<div style="position: absolute; top: -20px; left: -20px;"><img class="img-fluid" role="presentation"
src="https://moodle.example.com/pluginfile.php/19536/mod_page/content/5/IMG_2364%20%281%29.PNG"
alt="" width="45" height="61"></div>
<!-- Текстовий блок -->
<div style="padding-left: 20px; font-size: 18px; line-height: 1.66;">
{text}
</div>
</div>
""",

# 3 клас

# 5 клас, фото

# 6 клас


# стилізований блок акцентування (увага)
"attention":"""
<div class="notice info_block" style="position: relative; background-color: #eaf9ea; border-radius: 15px; padding: 20px; color: #4a4a4a; max-width: 720px; margin: 40px auto; margin-left: 20px;"><!-- піктограма -->
<div style="position: absolute; top: -20px; left: -20px;"><img class="img-fluid" role="presentation"
src="https://moodle.example.com/pluginfile.php/19534/mod_page/content/4/IMG_2365.PNG"
alt="" width="45" height="61"></div>
<!-- Текстовий блок -->
<div style="padding-left: 20px; font-size: 18px; line-height: 1.66;">{text}</div>
</div>
""",

# 3 клас

# 5 клас

# 6 клас  


# рефлексія
"reflection":"""
<div class="notice info_block" style="position: relative; background-color: #f9cd6a; border-radius: 15px; padding: 10px; color: #4840a3; max-width: 720px; margin: 40px auto; margin-top: 70px; margin-left: 40px;"><!-- піктограма -->
<div style="position: absolute; top: -60px; left: -50px;">
<div style="font-size: 60px; margin: 0px; text-align: left;"><img class="img-fluid" role="presentation"
src="https://moodle.example.com/pluginfile.php/19796/mod_page/content/4/%D0%B7%D0%BD%D0%B0%D1%87%D0%BE%D0%BA%20%D0%BD%D0%B0%20%D0%BE%D1%86%D1%96%D0%BD%D0%B8%20%D1%81%D0%B2%D0%BE%D1%97%20%D1%81%D1%82%D0%B0%D1%80%D0%B0%D0%BD%D0%BD%D1%8F.PNG"
alt="" width="90" height="112"></div>
</div>
<!-- Текстовий блок -->
<div style="margin: 0px; text-align: center; font-family: 'DreamSchoolBold'; font-size: clamp(24px, 5vw, 30px);">Оціни свої старання</div>
</div>
<p class="img_article">{img_name}</p>

""",


# 1 клас

# 3 клас

# 5 клас, фото

# 6 клас


# виділення заголовків у теорії
# Синя
"local_title": """<h3 style="text-align: left; font-size: 26px; color: #3c398c; font-family: 'DreamSchoolBold'; margin-block: 32px 16px;"><strong>{text}</strong></h3>""",
# рожева

# кастомне позначення деякого тексту у прикладах
"task_atention": """
<div class="notice info_block" style="position: relative; background-color: #f2f2f2; border-radius: 15px; padding: 20px; color: #202b58; max-width: 720px; margin: 40px auto; margin-left: 20px;"><!-- піктограма -->
<div style="position: absolute; top: -20px; left: -20px;"><img class="img-fluid" role="presentation" src="https://moodle.example.com/pluginfile.php/19796/mod_page/content/4/IMG_2433.PNG" alt="" width="60" height="54"></div>
<!-- Текстовий блок -->
<div style="padding-left: 20px; font-size: 18px; line-height: 1.66;"><strong>{text}</strong></div>
</div>
""",

# 1 клас

# 3 клас

# стиль на ютаб
"youtube":"""
<div style="max-width: 100%; width: 720px; margin: 20px 0; aspect-ratio: 16/9;">
<iframe style="width: 100%; height: 100%;" src="{link}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen="allowfullscreen"></iframe>
</div>""",

# стиль на ютаб шорти
"youtube_shorts":"""
<div style="
  margin: 20px auto;
  height: 80vh;
  aspect-ratio: 9 / 16;
  display: flex;
  justify-content: center;
  align-items: center;
">
  <iframe
    style="
      height: 100%;
      aspect-ratio: 9 / 16;
      border: 0;
    "
    src="{link}"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
    allowfullscreen>
  </iframe>
</div>
""",


# кастомізований блок на стилізацію нумерованого списку
"number_block": """<div style="position: relative; background-color: #fcd01f; border-radius: 15px; padding: 20px; font-family: 'Montserrat', sans-serif; color: #4a4a4a; max-width: 720px; margin: 50px auto; margin-left: 20px;"><!-- Круглий номер -->
<div style="position: absolute; top: -5px; left: -15px; transform: translateY(-50%); background-color: #3c398c; color: #ffffff; width: 40px; height: 40px; display: flex; justify-content: center; align-items: center; border-radius: 50%; font-size: 18px; font-weight: bold; font-family: 'DreamSchoolBold', sans-serif;">{number}</div>
<!-- Текстовий блок -->
<div style="font-size: 18px; line-height: 1.6;">{text}</div>
</div>""",

"number_block_text_blue": """<div style="background-color: #eaf0ff; border-radius: 15px; padding: 20px; font-family: 'Montserrat', sans-serif; color: #4a4a4a; max-width: 720px; margin: 50px auto;">
<div style="background-color: #3c398c;color: #eaf0ff;border-radius: 36px;font-weight: bold; text-align: center; width: 100%;font-size: clamp(16px, 5vw, 20px);padding: 1px 1px;margin-bottom: 15px;font-family: 'DreamSchoolBold', sans-serif;">{header_text}</div>
<div style="font-size: 18px; line-height: 1.6;">
{text}
</div>
</div>""",


# блок цікавого факту
"fact": """<div class="notice fact_block" style="position: relative; background-color: #fbe5a0; border-radius: 15px; padding: 20px; color: #704f37; max-width: 720px; margin: 40px auto; margin-left: 20px;"><!-- піктограма -->
<div style="position: absolute; top: -20px; left: -20px;"><img class="img-fluid" role="presentation"
src="https://moodle.example.com/pluginfile.php/19796/mod_page/content/4/IMG_2370.PNG"
alt="" width="60" height="60"></div>
<!-- Текстовий блок -->
<div style="padding-left: 20px; padding-right: 20px; font-size: 18px; line-height: 1.66;">
<h3 dir="ltr" style="margin: 0; padding-block: 10px 10px;">Цікаві факти, які тебе здивують!</h3>
{text}
</div>
</div>""",

# 1 клас

# 3 клас

# 5 клас, фото

# 6 клас


# блок цікавого факту зі зміним першим заголовком
"fact2": """<div class="notice fact_block" style="position: relative; background-color: #fbe5a0; border-radius: 15px; padding: 20px; color: #704f37; max-width: 720px; margin: 40px auto; margin-left: 20px;"><!-- піктограма -->
<div style="position: absolute; top: -20px; left: -20px;"><img class="img-fluid" role="presentation"
src="https://moodle.example.com/pluginfile.php/19796/mod_page/content/4/IMG_2370.PNG"
alt="" width="60" height="60"></div>
<!-- Текстовий блок -->
<div style="padding-left: 20px; padding-right: 20px; font-size: 18px; line-height: 1.66;">
<h3 dir="ltr" style="margin: 0; padding-block: 10px 10px;">{header_text}</h3>
{text}
</div>
</div>""",

# 1 клас

# 3 клас

# 5 клас, фото

# 6 клас


# блок літмережі (Укр література)
"litweb": """<div class="notice info_block" style="position: relative; background-color: #f9cd6a; border-radius: 0 15px 15px 15px; padding: 10px; color: #4840a3; max-width: 720px; margin: 10px auto; margin-top: 40px; margin-left: 90px;"><!-- піктограма -->
<div style="position: absolute; top: -10px; left: -90px;">
<div style="font-size: 60px; margin: 0px; text-align: left;"><img class="img-fluid litweb_img" role="presentation" src="https://moodle.example.com/pluginfile.php/7013/mod_page/content/5/%D0%BA%D0%BE%D0%BD%D1%82%D0%B0%D0%BA%D1%82.png" alt="" width="80" height="80"></div>
</div>
<!-- Текстовий блок -->
<div style="padding: 5px 15px 0; font-size: 18px; line-height: 1.66;"><strong><i>Павло Тичина</i></strong></div>
<div style="padding: 15px; font-size: 18px; line-height: 1.66;"><i>{text}</i></div>
</div>""",


# блок Творчого завдання
"creative_project": """<div class="notice homework_block" style="position: relative; background-color: #ddebff; border-radius: 15px; padding: 20px; color: #4a4a4a; max-width: 720px; margin: 40px auto; margin-left: 20px;"><!-- піктограма -->
<div style="position: absolute; top: -20px; left: -20px;"><img class="img-fluid" role="presentation" src="https://moodle.example.com/pluginfile.php/6602/mod_page/content/21/IMG_2777%20%281%29.PNG" alt="" width="60" height="60"></div>
<!-- Текстовий блок -->
<h3 style="padding-left: 20px; font-size: 26px; line-height: 1.66;">{header_name}</h3>
<div style="padding-left: 20px; font-size: 18px; line-height: 1.66; margin: 20px 0 10px 0;">
{text}
</div>
</div>""",


# блок для розміщення на 1\3 карітнка на другу 2\3 текст

"image_text_block":"""
<div class="image_text_block" style="display: flex; align-items: center; max-width: 800px; margin: 20px auto;">
    <div style="flex: 1; text-align: center;">
        <p>*картинка</p>
    </div>
    <div style="flex: 2; padding-left: 20px; font-size: 18px; line-height: 1.6;">
        <p>{text}</p>
    </div>
</div>
"""


}

custom_styles = {
    "Пізнаємо природу": {
        "theory": {
            "header": "theory_header",
            "unordered_item": "theory_unordered_item",
            "ordered_item": "theory_ordered_item",
            "paragraph": "theory_paragraph",
        },
        "default": {
            "header": "default_header",
            "unordered_item": "default_unordered_item",
            "ordered_item": "default_ordered_item",
            "paragraph": "default_paragraph",
        },
        "term": "term_circle_PP",
        "interactive": {
            "instruction": "interactive_instruction",
            "iframe": "interactive_iframe",
        },
        "homework": "homework",
        "text_task": "task",
        "answer": "answer",
        
    },
     "Українська мова": {
        "theory": {
            "header": "theory_header_double_color_center",
            "unordered_item": "theory_unordered_item",
            "ordered_item": "theory_ordered_item",
            "paragraph": "theory_paragraph",
        },
        "default": {
            "header": "default_header",
            "unordered_item": "default_unordered_item",
            "ordered_item": "default_ordered_item",
            "paragraph": "default_paragraph",
        },
        "term": "term_circle",
        "interactive": {
            "instruction": "interactive_instruction",
            "iframe": "interactive_iframe",
        },
        "homework": "homework",
        "text_task": "task_ukr_2",
        # "text_task": "task_header",
        
        "answer": "answer",

    },
         "Українська література": {
        "theory": {
            "header": "theory_header_double_color",
            "unordered_item": "theory_unordered_item",
            "ordered_item": "theory_ordered_item",
            "paragraph": "theory_paragraph",
        },
        "default": {
            "header": "default_header",
            "unordered_item": "default_unordered_item",
            "ordered_item": "default_ordered_item",
            "paragraph": "default_paragraph",
        },
        "term": "term_circle",
        "interactive": {
            "instruction": "interactive_instruction",
            "iframe": "interactive_iframe",
        },
        "homework": "homework",
        "text_task": "task_1",
        "answer": "answer",
    },
         "Зарубіжна література": {
        "theory": {
            "header": "theory_simple_circle",
            "unordered_item": "theory_unordered_item",
            "ordered_item": "theory_ordered_item",
            "paragraph": "theory_paragraph",
        },
        "default": {
            "header": "default_header",
            "unordered_item": "default_unordered_item",
            "ordered_item": "default_ordered_item",
            "paragraph": "default_paragraph",
        },
        "term": "term_beautifule",
        "interactive": {
            "instruction": "interactive_instruction",
            "iframe": "interactive_iframe",
        },
        # "example": "example",
        "homework": "homework",
        "text_task": "task_2",
        "answer": "answer",
    },
         "Математика": {
        "theory": {
            "header": "theory_math",
            "unordered_item": "theory_unordered_item",
            "ordered_item": "theory_ordered_item",
            "paragraph": "theory_paragraph",
        },
        "default": {
            "header": "default_header",
            "unordered_item": "default_unordered_item",
            "ordered_item": "default_ordered_item",
            "paragraph": "default_paragraph",
        },
        "term": "term_simple_border",
        "interactive": {
            "instruction": "interactive_instruction",
            "iframe": "interactive_iframe",
        },
        "homework": "homework",
        "example": "task_header",
        "text_task": "task_3",
        "answer": "answer",

    },
         "Німецька мова": {
        "theory": {
            # "header": "theory_header_double_color", # 5 - 10 клас
            "header": "theory_math", # 11 клас
            "unordered_item": "theory_unordered_item",
            "ordered_item": "theory_ordered_item",
            "paragraph": "theory_paragraph",
        },
        "default": {
            "header": "default_header",
            "unordered_item": "default_unordered_item",
            "ordered_item": "default_ordered_item",
            "paragraph": "default_paragraph",
        },
        "term": "term_beautifule",
        "interactive": {
            "instruction": "interactive_instruction",
            "iframe": "interactive_iframe",
        },
        "homework": "homework",
        "text_task": "task_2",
        "answer": "answer",
    },
    
     "Історія України": {
        "theory": {
            "header": "theory_history",
            "unordered_item": "theory_unordered_item",
            "ordered_item": "theory_ordered_item",
            "paragraph": "theory_paragraph",
        },
        "default": {
            "header": "default_header",
            "unordered_item": "default_unordered_item",
            "ordered_item": "default_ordered_item",
            "paragraph": "default_paragraph",
        },
        "term": "term_beautifule",
        "interactive": {
            "instruction": "interactive_instruction",
            "iframe": "interactive_iframe",
        },
        "example": "example",
        "homework": "homework",
        "text_task": "task_header",
        "answer": "answer",
    },
     
      "Німецька мова 510": {
        "theory": {
            "header": "theory_header_double_color_center", # 5 - 10 клас
            "unordered_item": "theory_unordered_item",
            "ordered_item": "theory_ordered_item",
            "paragraph": "theory_paragraph",
        },
        "default": {
            "header": "default_header",
            "unordered_item": "default_unordered_item",
            "ordered_item": "default_ordered_item",
            "paragraph": "default_paragraph",
        },
        "term": "term_beautifule",
        "interactive": {
            "instruction": "interactive_instruction",
            "iframe": "interactive_iframe",
        },
        "homework": "homework",
        "text_task": "task_2",
        "answer": "answer",
    },
    
     "Історія України": {
        "theory": {
            "header": "theory_history",
            "unordered_item": "theory_unordered_item",
            "ordered_item": "theory_ordered_item",
            "paragraph": "theory_paragraph",
        },
        "default": {
            "header": "default_header",
            "unordered_item": "default_unordered_item",
            "ordered_item": "default_ordered_item",
            "paragraph": "default_paragraph",
        },
        "term": "term_beautifule",
        "interactive": {
            "instruction": "interactive_instruction",
            "iframe": "interactive_iframe",
        },
        "example": "example",
        "homework": "homework",
        "text_task": "task_header",
        "answer": "answer",
    },
     
}


def compose_subject_styles(subject_styles, all_styles):
    """
    Заповнює словник предметів реальними стилями зі звалища стилів.
    """
    for subject, categories in subject_styles.items():
        for category, elements in categories.items():
            if isinstance(elements, dict):
                for key, style_name in elements.items():
                    if style_name in all_styles:
                        subject_styles[subject][category][key] = all_styles[style_name]
                    else:
                        raise KeyError(f"Style '{style_name}' not found in all_styles")
            elif isinstance(elements, str):
                if elements in all_styles:
                    subject_styles[subject][category] = all_styles[elements]
                else:
                    raise KeyError(f"Style '{elements}' not found in all_styles")




SCOPES = [
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly",
]


service = None          # docs
drive_service = None    # drive
service = None

def init_google_service():
    global service, drive_service

    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )

    service = build('docs', 'v1', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)


def get_document_content(doc_id):
    global service
    return service.documents().get(documentId=doc_id).execute()

def get_list_type_old(list_id, lists):
    if list_id in lists:
        list_properties = lists[list_id].get('listProperties', {})
        nesting_levels = list_properties.get('nestingLevels', [{}])
        glyph_type = nesting_levels[0].get('glyphType', None)
        if glyph_type and any(num_type in glyph_type for num_type in ['DECIMAL', 'ROMAN', 'ALPHA']):
            return 'ordered_list', glyph_type  
    return 'unordered_list', None

def get_list_type(list_id, lists, nesting_level=0):
    if not list_id or list_id not in lists:
        return 'unordered_list', None  # Якщо список не знайдено, вважаємо його маркованим

    list_properties = lists[list_id].get('listProperties', {})
    nesting_levels = list_properties.get('nestingLevels', [])

    # Якщо рівень вкладеності більше, ніж доступні рівні, повертаємо unordered_list
    if nesting_level >= len(nesting_levels):
        return 'unordered_list', None

    # Перевіряємо тільки потрібний рівень вкладеності
    glyph_type = nesting_levels[nesting_level].get('glyphType', None)

    if glyph_type in ['DECIMAL', 'ROMAN', 'ALPHA']:
        return 'ordered_list', glyph_type
    else:
        return 'unordered_list', glyph_type


def apply_text_styles(content, style):
    styled_content = html.escape(content)
    # Додаємо семантичні теги для стилів
    if style.get('bold', False):
        styled_content = f"<b>{styled_content}</b>"
    if style.get('italic', False):
        styled_content = f"<i>{styled_content}</i>"
    if style.get('underline', False):
        styled_content = f"<u>{styled_content}</u>"
    if style.get('strikethrough', False):
        styled_content = f"<s>{styled_content}</s>"
    if style.get('baselineOffset') == 'SUPERSCRIPT':
        styled_content = f"<sup>{styled_content}</sup>"
    if style.get('baselineOffset') == 'SUBSCRIPT':
        styled_content = f"<sub>{styled_content}</sub>"


    def rgb_to_hex(rgb):
        """Конвертує RGB-об'єкт у HEX-код."""
        r = int(rgb.get('red', 0) * 255)
        g = int(rgb.get('green', 0) * 255)
        b = int(rgb.get('blue', 0) * 255)
        return f"#{r:02x}{g:02x}{b:02x}"
    # Обробка кольорів для термінів
    has_term = False  # Флаг для визначення, чи є це термін
    bg_color = ""  # Колір фону

    if 'backgroundColor' in style:
        bg_color = style['backgroundColor'].get('color', {}).get('rgbColor', {})
        if bg_color:
            # Перевіряємо, чи це жовтий фон (термін)
            bg_color = rgb_to_hex(bg_color)
                
            global IN_TEST_BLOCK
            if IN_TEST_BLOCK:
                styled_content = f'<span class="background_color" style="background-color: {bg_color};">{styled_content}</span>'
            
    
     # Обробка кольору тексту (foregroundColor)
    if 'foregroundColor' in style:
        fg_color = style['foregroundColor'].get('color', {}).get('rgbColor', {})
        if fg_color:
            fg_color_str = rgb_to_hex(fg_color)
            
            styled_content = f'<span class="span_color" style="color: {fg_color_str};">{styled_content}</span>'


        # Спочатку – зважте на надрядкові та підрядкові стилі

    #     # m.group(1) – це вміст без дужок


    #     # Можете тут робити будь-що, хоч заміняти апострофи чи діакритику.
    

    return styled_content, bg_color

def get_styles_for_subject_block():
    subject_cfg = custom_styles.get(CURRENT_SUBJECT, {})
    # Якщо ми в теорії - беремо 'theory', якщо в інтерактиві - беремо 'interactive', інакше 'default'
    if (IN_THEORY_BLOCK and "theory" in subject_cfg) or IN_HELLO_BLOCK:
        return subject_cfg["theory"]
    elif IN_INTERACTIVE_BLOCK and "interactive" in subject_cfg:
        return subject_cfg["interactive"]
    return subject_cfg.get("default", {
        "header": "<h2>{header_text}</h2>\n",
        "unordered_item": "<p>• {item_text}</p>\n",
        "ordered_item": "<p>{number}. {item_text}</p>\n",
        "paragraph": "<p>{text}</p>\n"
    })


def update_styles_with_color(styles, color):
    for key, value in styles.items():
        if isinstance(value, dict):
            # Рекурсивно обробляємо вкладені словники
            update_styles_with_color(value, color)
        elif isinstance(value, str) and "{main_color}" in value:
            # Оновлюємо тільки {main_color}, не торкаючись інших маркерів
            styles[key] = value.replace("{main_color}", color)


def get_list_nesting_level(paragraph):
    """
    Отримує рівень вкладеності для пункту списку.
    Якщо рівень не вказано, за замовчуванням 0 (верхній рівень).
    """
    
    return paragraph.get('bullet', {}).get('nestingLevel', 0)


list_counters = {}

def get_exact_list_marker(paragraph, lists):
    bullet = paragraph.get('bullet', {})
    list_id = bullet.get('listId')
    nesting_level = bullet.get('nestingLevel', 0)

    if not list_id or not lists.get(list_id):
        return None

    list_info = lists[list_id]
    list_properties = list_info.get('listProperties', {})
    nesting_levels = list_properties.get('nestingLevels', [])
    if nesting_level >= len(nesting_levels):
        return None

    glyph_format = nesting_levels[nesting_level].get('glyphFormat', '')
    # Якщо це вкладений список і використовується '%1', замінюємо його на '%a'
    if nesting_level > 0 and '%1' in glyph_format:
        glyph_format = glyph_format.replace('%1', '%a')

    # Для зовнішніх списків (рівень 0) за замовчуванням startNumber = 1,
    # для вкладених — за замовчуванням startNumber = 0 (тобто починаємо з 0)
    if nesting_level == 0:
        start_number = nesting_levels[nesting_level].get('startNumber', 1)
    else:
        start_number = nesting_levels[nesting_level].get('startNumber', 0)

    global list_counters
    key = (list_id, nesting_level)
    if nesting_level == 0:
        # Оновлюємо лічильник для зовнішнього рівня
        current_index = list_counters.get(key, 0) + 1
        list_counters[key] = current_index
        # Скидаємо лічильники для всіх вкладених рівнів цього списку
        for k in list(list_counters.keys()):
            if k[0] == list_id and k[1] > 0:
                list_counters[k] = 0
    else:
        # Для вкладених bullet просто збільшуємо лічильник
        current_index = list_counters.get(key, 0) + 1
        list_counters[key] = current_index

    # Обчислюємо абсолютну позицію з урахуванням startNumber
    absolute_position = start_number + current_index - 1

    return resolve_list_marker(glyph_format, absolute_position)


def resolve_list_marker(glyph_format, current_index):
    if '%0' in glyph_format:
        return glyph_format.replace('%0', str(current_index))
    elif '%1' in glyph_format:
        return glyph_format.replace('%1', str(current_index))
    elif '%a' in glyph_format:
        return glyph_format.replace('%a', chr(96 + current_index))
    elif '%A' in glyph_format:
        return glyph_format.replace('%A', chr(64 + current_index))
    elif '%i' in glyph_format:
        return glyph_format.replace('%i', int_to_roman(current_index))
    elif '%I' in glyph_format:
        return glyph_format.replace('%I', int_to_roman(current_index).upper())
    else:
        return glyph_format


def int_to_roman(num):
    """
    Конвертує число в римський формат.
    :param num: Ціле число.
    :return: Римське представлення числа.
    """
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    roman = ''
    i = 0
    while num > 0:
        for _ in range(num // val[i]):
            roman += syms[i]
            num -= val[i]
        i += 1
    return roman


def process_text_elements(elements, lists):
    html_output = ""
    current_list_type = None
    ordered_counter = 1
    sub_order_counter = 1

    # це для блоків з цифрами щоб розрізняти де початок або кінець у комірці з цифрами
    is_in_number_text = False
    style_list_nubmer_block = True
    is_local_header = False
    is_nubmer_list = False
    
    AUTO_NUMBER_RECOGNITION = True


    local_styled_text = ""
    header_text = ""
    
    
    global div_color, SKIP_SECTION_HEADER_NAME
    _skip_header = SKIP_SECTION_HEADER_NAME
    _header_checked = False

    colors_array = ["#FCD01F", "#E9629E","#3C398C"]
    # Знайти індекс поточного кольору
    current_index = colors_array.index(div_color)
    next_index = (current_index + 1) % len(colors_array)  # Циклічний перехід
    next_color = colors_array[next_index]
    

    styles = get_styles_for_subject_block()


    pending_pereglyan_html = None   # буфер "Переглянь:" у розділі Andere (один task_atention-блок)

    _in_answer_block = False
    _answer_buf = ""
    _answer_keys = [
        "<b>Відповідь</b>:", "<b>Відповідь</b>", "<b>Відповідь:</b>",
        "<b>Відповіді</b>:", "<b>Відповіді</b>", "<b>Antworten</b>",
        "Antworten", "Відповідь:", "Відповідь", "Відповіді:", "Відповіді",
        "Lösungen (відповіді)", "Перевір себе:", "Перевір себе",
    ]

    for element in elements:
        if 'paragraph' in element:
            paragraph = element['paragraph']
            paragraph_type = 'normal_text'
            text = ""
            is_quote = False  # Флаг для визначення, чи є параграф цитатою
            has_term = False  # Флаг для визначення, чи містить параграф терміни
            is_charater_blok = False  # Флаг для визначення, реплік персожнажу
            is_theory_title = False  # Флаг для визначення, чи це заголовок в теорії

            # Визначення, чи є параграф цитатою
            paragraph_style = paragraph.get('paragraphStyle', {})
            alignment = paragraph_style.get('alignment', 'START')
            if alignment in ['CENTER', 'END']:
                is_quote = True
            else:
                indent = paragraph_style.get('indent', {}).get('start', 0)
                if indent > 1000:  # Приклад значення, залежить від реального форматування
                    is_quote = True


            if 'bullet' in paragraph:
                nesting_level = get_list_nesting_level(paragraph)
                
                list_id = paragraph['bullet']['listId']
                paragraph_type_old, glyph_type_old = get_list_type_old(list_id, lists)
                paragraph_type, glyph_type = get_list_type(list_id, lists, nesting_level)
                
                
                # Перевіряємо, чи список вкладений

                print(f"📌 Пункт у списку {list_id} знаходиться на рівні вкладеності: {nesting_level}")
                
                

            # Обробка текстових елементів
            for el in paragraph.get('elements', []):
                if 'textRun' in el:
                    text_run = el['textRun']
                    # styled_content, term_flag = apply_text_styles(
                    styled_content, bg_color = apply_text_styles(
                        text_run.get('content', ''),
                        text_run.get('textStyle', {})
                    )
                    text += styled_content
                    if "#ffff00" in  bg_color:
                        has_term = True

                    if "#00ffff" in bg_color:
                        is_charater_blok = True
                        return html_output
                elif 'richLink' in el:
                    uri = el['richLink'].get('richLinkProperties', {}).get('uri', '')
                    if uri:
                        text += uri

            stripped_text = text.strip()

            # Пропускаємо параграф, що дублює заголовок секції.
            # SKIP скидаємо ЛИШЕ при фактичному збігу — інакше проміжна клітинка
            # (SOURCE/інструкція) передчасно очистила б SKIP, і повтор заголовка
            # у наступній клітинці (напр. "Секрети мови"/"Мова в дії") не пропустився б.
            if _skip_header and not _header_checked and stripped_text:
                _plain = re.sub(r'<[^>]+>', '', stripped_text).strip('\n').strip()
                if _plain == _skip_header:
                    _header_checked = True
                    SKIP_SECTION_HEADER_NAME = ""
                    continue

            # ── Andere: "Переглянь:" + відео-підпис(@) → один task_atention-блок, рядки через <br>
            if IN_ADDITIONAL_BLOCK:
                _pl = re.sub(r'<[^>]+>', '', stripped_text).strip()
                if pending_pereglyan_html is None and _pl == "Переглянь:":
                    pending_pereglyan_html = stripped_text.strip()
                    continue
                if pending_pereglyan_html is not None:
                    if "@" in re.sub(r'<[^>]+>', '', stripped_text):
                        _cap = stripped_text.replace("@", "").strip()
                        _row = all_styles["task_atention"].format(
                            text=f"{pending_pereglyan_html}<br>{_cap}") + "~~"
                        html_output += f'{_row}\n'
                        pending_pereglyan_html = None
                        continue
                    else:
                        # наступний параграф не відео-підпис → "Переглянь:" як звичайний абзац
                        html_output += f'<p>{pending_pereglyan_html}</p>\n'
                        pending_pereglyan_html = None
                        # поточний параграф обробляється далі звичайним шляхом

            if "Ознаки водоростей – унікальних жителів світу" in stripped_text:
                print(repr(stripped_text))
                pass
            
            if "Як вони живуть – водні герої" in stripped_text:
                print(repr(stripped_text))
                pass
        
            if "Будова тіла" in stripped_text:
                print(repr(stripped_text))
                pass
        
            
            if AUTO_NUMBER_RECOGNITION:
                pattern = re.compile(
                    r'^(?:<[^>]+>|\s)*'   # нуль або більше тегів/пробілів
                    r'(\d+)'              # група з цифрами
                    r'([.)])'             # . або )
                    r'(?:<[^>]+>|\s)+'    # хоча б один тег чи пробіл
                    r'(.*)'               # решта тексту
                    , flags=re.DOTALL
                )

                match = pattern.match(text)
                if match:
                    paragraph_type = 'ordered_list'
                    glyph_type = "DECIMAL"
                    nesting_level = 0
                    number_part = match.group(1)
                    if number_part == '1':

                        # скидаємо глобальний лічильник
                        global list_counters
                        
                        list_counters[("FAKE_LIST_ID", 0)] = 0
                        
                    
                    for i in range(1,11):
                        stripped_text = stripped_text.replace(f"{i}. ", "")
                        
                    # 1) Підкладаємо штучний bullet
                    paragraph["bullet"] = {
                        "listId": "FAKE_LIST_ID",
                        "nestingLevel": 0
                    }
                    
                    # 2) Якщо у lists ще нема нашого «FAKE_LIST_ID», створюємо його
                    if "FAKE_LIST_ID" not in lists:
                        lists["FAKE_LIST_ID"] = {
                            "listProperties": {
                                "nestingLevels": [
                                    {
                                        "glyphType": "DECIMAL",
                                        "glyphFormat": "%1.",
                                        "startNumber": int(number_part)
                                        
                                        # Тут можна поставити %1) або щось інше
                                    }
                                ]
                            }
                        }
            
            # Зчитування довбаних значеннь з нумерованих списків
            exact_list_marker = get_exact_list_marker(paragraph, lists)
            if exact_list_marker:
                exact_list_marker = exact_list_marker.replace(".","")
                

                
            #     # Перевіряємо, чи список вкладений


            # Збираємо текст з параграфа
            for el in paragraph.get('elements', []):
                if 'textRun' in el:
                    text_run = el['textRun']
                    text += text_run.get('content', '').strip()
                    
                    
                    
            # обробка фото 
            if 'elements' in paragraph:
                for p_el in paragraph['elements']:
                    # 1. Для "inline" зображень
                    if 'inlineObjectElement' in p_el:
                        inline_id = p_el['inlineObjectElement']['inlineObjectId']
                        print(f"Знайдено inline-зображення з ID: {inline_id}")
                        stripped_text = "*photo*"  # замінюємо текст на маркер фото
                        
                    # 2. Для "positioned" (плаваючих) зображень 
                    if 'positionedObjectElement' in p_el:
                        positioned_id = p_el['positionedObjectElement']['positionedObjectId']
                        print(f"Знайдено positioned-зображення з ID: {positioned_id}")
                        stripped_text = positioned_id
                        

            if "картинка" in stripped_text:
                pass
            
            # припинення роботи якщо знайдено знак "!="
            if "!=" in stripped_text or is_charater_blok:
                html_output += stripped_text
                return html_output
                break
           
            # пропуск зчитування параграфу 
            if "!p" in stripped_text:
                 continue
            
            # а це на вставку div блока для інтерактиву
            if "Заглушка" in stripped_text:
                match = re.search(r'[Зз]аглушка\d+', stripped_text)
                marker = match.group(0) if match else "Заглушка"
                html_output += f"<p>{marker}</p>\n<div style='max-width: 720px;'></div>\n"
                continue

            if "заглушка" in stripped_text:
                match = re.search(r'заглушка\d+', stripped_text)
                marker = match.group(0) if match else "заглушка"
                html_output += f'<p>{marker}</p>\n<div style="max-width: 720px; padding: 10px; background: white;"></div>\n'
                continue
            
            # Розпізнавання стилізації блоку для знаку питання
            # ?? може бути розбитий між двома textRun-ами → перевіряємо у plain-тексті
            _plain_for_q = re.sub(r'<[^>]+>', '', stripped_text)
            if "??" in _plain_for_q:
                _question_text = _plain_for_q.replace("??", "?").strip()
                question_text_row = all_styles["question"].format(text=_question_text)
                html_output += f'{question_text_row}\n'
                continue

            # Розпізнавання стилізації блоку для "Увага" питання

            if "!!" in stripped_text or "!</b><b>!" in stripped_text:
                stripped_text = stripped_text.replace("!!","!")
                stripped_text = stripped_text.replace("!</b><b>!","!")
                attention_text_row = all_styles["attention"].format(text=stripped_text)
                html_output += f'{attention_text_row}\n'
                
                continue
            
            # Кастомні локальні заголовки в теорії
            
            # is_local_header
            if "$" in stripped_text or is_nubmer_list:
                is_local_header = False
                is_nubmer_list = True
                
                
                # онця шутка треба для того щоб зчитуватис рядки які виділині жирним що це заголовк, але якщо у тексті просто є жирні рядки то це також його вносить в заголовок
                
            elif ("**" in stripped_text):
                is_local_header = False


                    
                    
                if "*!" not in stripped_text:
                    is_local_header = True
                    
                    
                    
                    if not IN_TEST_BLOCK:
                        is_local_header = True
                        
                    if IN_TEST_BLOCK or IN_PRACTICE_BLOCK:
                        is_local_header = False
                        

                        
                
            if is_local_header:
                stripped_text = stripped_text.replace("**","")
                local_title_text_row = all_styles["local_title"].format(text=stripped_text)
                html_output += f'{local_title_text_row}\n'
                is_local_header = False
                continue
            else:
                stripped_text = stripped_text.replace("*!","")

            
            # Кастомні локальні заголовки в теорії
            if "@" in stripped_text:
                stripped_text = stripped_text.replace("@","")
                task_atention_text_row = all_styles["task_atention"].format(text=stripped_text)
                task_atention_text_row += "~~"
                html_output += f'{task_atention_text_row}\n'
                continue

            # оформлення блоків з цифрами
            if "$" in stripped_text or is_in_number_text:
                
                # # Кастиль для відпрацювання додавання останього пункту 

    
        
                if "$$" not in stripped_text:
                    if "$" in stripped_text:
                        if "$*" in stripped_text:
                            style_list_nubmer_block = False
                            stripped_text = stripped_text.replace("$*","текст")


                    stripped_text = stripped_text.replace("$","")
                    stripped_text = f"<p>{stripped_text}</p>"
                    

                    local_styled_text += stripped_text
                    
                    
                    
                    
                    
                    


                if style_list_nubmer_block:
                    if paragraph_type == 'unordered_list' and stripped_text:
                        
                        if stripped_text in local_styled_text:
                            local_styled_text = local_styled_text.replace(stripped_text, "")
                            stripped_text = stripped_text.replace("<p>","").replace("</p>","")
                            
                        if nesting_level > 0:
                            # Додати вкладений список                
                            
                            unordered_item_div = all_styles["theory_unordered_item"].format(main_color=next_color, item_text=stripped_text)

                            custom_padding = 30 * nesting_level
                            unordered_item_div = unordered_item_div.replace(f'margin-left: 0px;', f'margin-left: {custom_padding}px;')
                            
                            
                        
                        
                        if nesting_level > 0:
                            local_styled_text += unordered_item_div
                        else:
                            local_styled_text += styles["unordered_item"].format(item_text=stripped_text)
                
                    elif paragraph_type == 'ordered_list' and stripped_text:
                        if nesting_level > 0:
                            ordered_item_div = all_styles["theory_ordered_item"].format(main_color=next_color, item_text=stripped_text)

                            custom_padding = 30 * nesting_level
                            ordered_item_div = ordered_item_div.replace(f'margin-left: 0px;', f'margin-left: {custom_padding}px;')
                        
                        if nesting_level > 0:
                            local_styled_text += ordered_item_div
                        else:
                            local_styled_text += styles["ordered_item"].format(item_text=stripped_text, number=ordered_counter)
                        ordered_counter += 1


                is_in_number_text = True
                hh_text = stripped_text.replace("<p>","").replace("</p>","")
                if hh_text.startswith("<b>") and hh_text.endswith("</b>"):
                    header_text = stripped_text
                    html_output = html_output.replace(stripped_text, "")
                    local_styled_text = local_styled_text.replace(stripped_text, "")
                    continue

                if is_in_number_text and "$$" in stripped_text:
                    
                    is_nubmer_list = False
                    
                    
                    stripped_text = stripped_text.replace("$$","")
                    
                    if "_blue_" in stripped_text:
                        stripped_text = stripped_text.replace("<p>","").replace("</p>","")
                        
                        stripped_text = stripped_text.replace("_blue_","")
                        header_text = header_text.replace("<b>","").replace("</b>","")
                        
                        text_block_number_block = all_styles["number_block_text_blue"].format(text=local_styled_text, header_text = header_text)
                    else:
                        # Видаляємо число і пробіл на початку тексту (враховуємо можливі символи нового рядка)
                        header_text = re.sub(r'(<b>)?\s*\d+\.\s*(.*?)(</b>)?', r'\1\2\3', header_text, flags=re.DOTALL)
                        header_text = header_text.replace("<p>","<p style='color: #3C398C;'>")
                        local_styled_text = header_text + local_styled_text
                        text_block_number_block = all_styles["number_block"].format(text=local_styled_text, number=ordered_counter)
                    
                    ordered_counter += 1
                    html_output += f'{text_block_number_block}\n'
                    
                    local_styled_text = ""
                    header_text = ""
                    is_in_number_text = False
                continue

                

            # опрацювання рефлексії
            reflection_text = [
                "Оціни свої старання на уроці",
                "Оціни свої старання!",
                "Оціни свою роботу на уроці!",
                "Обери емодзі, яке відображає твої емоції",
                "Обери емодзі, які відображають твої емоції",
                ]
            for ref_item in reflection_text:
                if ref_item in stripped_text:
                    if CURRENT_SUBJECT == "Німецька мова" or CURRENT_SUBJECT == "Німецька мова 510":
                        img_name = "рефлексія німецька.png"
                    else:
                        img_name = "Рефлексія.png"

                    reflection_text_row = all_styles["reflection"].format(img_name=img_name)

                    if "Оціни свою роботу на уроці!" in stripped_text:
                        reflection_text_row = reflection_text_row.replace("Оціни свої старання", "Оціни свою роботу")
                    
                    html_output += f'{reflection_text_row}\n'
                    return html_output

            

            if paragraph_type in ['unordered_list', 'ordered_list']:
                if current_list_type != paragraph_type:
                    
                    # цей участок коду збиває нумерацію нумерованого списку
                    # так то він вирубаний щоб все було норм і працювала нумерація
                    
                    # для блоку практики треба її увімкнути бо там зміщується цифра у відповіді
                    
                    
                    
                    current_list_type = paragraph_type


            else:
                current_list_type = None
                
            if "<b>Цікавий факт:</b>" in stripped_text:
                text = text.replace("<b>Цікавий факт:</b>", "").strip()
                text = text[0].upper() + text[1:] if text else text
                fact_text_row = all_styles["fact2"].format(text=text, header_text = "Цікавий факт")
                html_output += f'{fact_text_row}'
                continue
                # header_text
                
                
                
            # ця єрунда треба аби moodle не агрився на слово "підручник" ібо воно автоматично вставляє посилання на підручник
            if "підручник" in stripped_text:
                text = text.replace("підручник", "підр&esmp;учник")


            if IN_INTERACTIVE_BLOCK:
                # Цей блок більше не використовується, обробка інтерактивних блоків відокремлена
                continue
            
            if IN_PRACTICE_BLOCK:
              
                if "Відповідь" in stripped_text or "Відповіді" in stripped_text:
                    ordered_counter = 1
                    


  
  
            # блок для розміщення на 1\3 карітнка на другу 2\3 текст
            if "//3" in stripped_text:
                stripped_text = stripped_text.replace("//3","")
                image_text_block = all_styles["image_text_block"].format(text=stripped_text)
                html_output += f'{image_text_block}\n'
                continue
  
  
            if "/q" in stripped_text:
                stripped_text = stripped_text.replace("/q","")
                quote_div = process_quote_row(stripped_text)
                html_output += f'{quote_div}\n'
                continue
  
                    
  
  
  
  
  
            # а цей кастиль аби в укр мові нормально у блоці "Тест" зчитувало відповіді ібо довбані списки всю малину портять
            # типу якщо відповідь має список 1) то вона відображається 1.
            # а як ми пам'ятаємо 1. це питання
            # не отріцаю той факт що можливо це я десь напартачив з розпізнавнням списків і воно всюди лупить {number}.
            
            
                
                
                
            
            if "словосполученні є слово" in stripped_text:
                pass

            _elem_html = ""

            if is_quote:

                if stripped_text:
                    _elem_html += f'<p class="quote">{stripped_text}</p>\n'
            elif has_term and ' ' in stripped_text:
                if stripped_text:
                    term_block = custom_styles[CURRENT_SUBJECT]["term"].format(text=stripped_text)
                    _elem_html += f'{term_block}\n'
            elif paragraph_type == 'unordered_list' and stripped_text:

                unordered_item_div = styles["unordered_item"].format(item_text=stripped_text)

                if nesting_level > 0:
                    # Додати вкладений список

                    unordered_item_div = all_styles["theory_unordered_item"].format(main_color=next_color, item_text=stripped_text)

                    custom_padding = 30 * nesting_level
                    unordered_item_div = unordered_item_div.replace(f'margin-left: 0px;', f'margin-left: {custom_padding}px;')


                _elem_html += f'{unordered_item_div}\n'

            elif paragraph_type == 'ordered_list' and stripped_text:
                stripped_text = stripped_text.replace("<p>","").replace("</p>","")

                if 'PARENTHESES' in glyph_type:
                    _elem_html += all_styles["ordered_item_)"].format(item_text=stripped_text, number=ordered_counter)

                else:
                    ordered_item_div = styles["ordered_item"].format(item_text=stripped_text, number=exact_list_marker)

                    if nesting_level > 0:
                        ordered_item_div = all_styles["theory_ordered_item"].format(main_color=next_color, item_text=stripped_text, number=exact_list_marker)

                        custom_padding = 30 * nesting_level
                        ordered_item_div = ordered_item_div.replace(f'margin-left: 0px;', f'margin-left: {custom_padding}px;')

                    _elem_html += f'{ordered_item_div}\n'
                ordered_counter += 1
            else:
                if stripped_text and current_list_type is None:
                    found_key = None
                    # practica має власний обробник відповідей (process_practice_row);
                    # _answer_buf тут — лише для теорії/Секретів. Інакше для practica
                    # вийде ДВА спойлери (один тут, другий у process_practice_row).
                    if not IN_PRACTICE_BLOCK:
                        for _k in _answer_keys:
                            if _k in stripped_text:
                                found_key = _k
                                break
                    if found_key:
                        _pre = stripped_text.split(found_key)[0].strip()
                        _post = stripped_text.split(found_key)[1].strip()
                        if _pre:
                            html_output += styles["paragraph"].format(text=_pre)
                        _in_answer_block = True
                        _answer_buf = _post
                    else:
                        _elem_html += styles["paragraph"].format(text=stripped_text)

            if _in_answer_block:
                _answer_buf += _elem_html
            else:
                html_output += _elem_html


    if _in_answer_block:
        html_output += all_styles["answer"].format(text=_answer_buf) + '\n'

    return html_output

def is_full_width_header(row):
    # Перевіряємо, чи має хоча б одна комірка columnSpan >1 та наявний фон
    for cell in row.get('tableCells', []):
        cell_style = cell.get('tableCellStyle', {})
        column_span = cell_style.get('columnSpan', 1)
        bg_color = cell_style.get('backgroundColor', {}).get('color', {}).get('rgbColor', {})
        if column_span > 2 and bool(bg_color):
            return True
    return False

def is_subheader_row(row):
    cells = row.get('tableCells', [])
    if len(cells) < 2:
        return False
    for cell in cells:
        cell_style = cell.get('tableCellStyle', {})
        column_span = cell_style.get('columnSpan', 1)
        bg_color = cell_style.get('backgroundColor', {}).get('color', {}).get('rgbColor', {})
        if column_span > 1 and bool(bg_color):
            return True
    return False

def header_for_subject(header_text):
    # Перейменування заголовків для предмету "Пізнаємо природу"
    renamed_header = rename_header(CURRENT_SUBJECT, header_text)

    # Заголовки завжди йдуть з теоретичних стилів заголовка
    subject_cfg = custom_styles.get(CURRENT_SUBJECT, {})
    theory_header = subject_cfg.get("theory", {}).get("header", "<h2>{header_text}</h2>\n")
    return theory_header.format(header_text=renamed_header)

def paragraph_for_subject(text):
    styles = get_styles_for_subject_block()
    return styles["paragraph"].format(text=text)


def extract_image_title_from_rich_links(cell):
    titles = []
    if 'content' in cell:
        for element in cell['content']:
            if 'paragraph' in element:
                for el in element['paragraph'].get('elements', []):
                    if 'richLink' in el:
                        rich_link = el['richLink']
                        title = rich_link.get('richLinkProperties', {}).get('title', '')
                        # Якщо потрібно не лише title, а й url, можна додати:
                        if title.strip():
                            titles.append(title.strip())
    return titles


def extract_rich_link_urls(cell):
    """{назва файлу: url} з rich-link'ів клітинки дизайнера.
    Потрібно для PDF: у статтю йде картинка, зроблена з PDF, а поруч —
    посилання на сам PDF, узяте зі сценарію (Drive-URL цього ж rich-link)."""
    urls = {}
    if 'content' in cell:
        for element in cell['content']:
            if 'paragraph' in element:
                for el in element['paragraph'].get('elements', []):
                    if 'richLink' in el:
                        props = el['richLink'].get('richLinkProperties', {})
                        title = (props.get('title') or '').strip()
                        uri = (props.get('uri') or '').strip()
                        if title and uri:
                            urls[title] = uri
    return urls


def pdf_image_name(pdf_name):
    """«3-прописи.pdf» → «3-прописи.png».
    insert_photos.looks_like_image_name() приймає лише
    .png/.jpg/.jpeg/.webp/.gif — плейсхолдер із .pdf він проігнорує,
    тому в статтю кладемо назву картинки, зробленої з цього PDF."""
    return re.sub(r'\.pdf$', '.png', pdf_name, flags=re.IGNORECASE)


def get_h5p_task(cell, lists):
    text_array = []
    is_h5p_template_exist = False
    
    if 'content' in cell:
        for element in cell['content']:
            if 'paragraph' in element:    
                text = ""
                
                # Збираємо текст з параграфа
                for el in element['paragraph'].get('elements', []):
                    if 'textRun' in el:
                        text_run = el['textRun']
                        # \x0b = м'який перенос (Shift+Enter у Google Docs) → перетворюємо у \n
                        content = text_run.get('content', '').replace('\x0b', '\n')
                        text += content.rstrip('\n')
                        
                if "=" in text:
                    is_h5p_template_exist = True
                    
                if is_h5p_template_exist and text:
                    text_array.append(text)
    
    
    data = {
        "type": "",
        "title": "",
        "header": "",
        "text_task": "",
        "html_code": "",
        "url_task": "",
        
    }
                        
    text_task = ""
    for text_item in text_array:
        if "=" in text_item:                    
            data["type"] = text_item
            
        elif "h:" in text_item:                    
            data["header"] = text_item
        else:
            text_task += text_item + "\n"
        
    
    if text_task:
        data["text_task"] = text_task
        return data
    

def read_cell_block(cell):
    """
    Функція для читання повного вмісту комірки таблиці.
    Повертає список параграфів у комірці.
    """
    content = []
    if 'content' in cell:
        for element in cell['content']:
            if 'paragraph' in element:
                content.append(element)


    return content

def process_cell_block(cell_content, lists):
    """
    Функція для обробки вмісту комірки таблиці.
    Повертає HTML-представлення вмісту комірки.
    """
    return process_text_elements(cell_content, lists).strip()

def process_cell(cell, lists, cell_index):
    """
    Обробляє окрему комірку таблиці в залежності від її контексту.
    """
    cell_content = read_cell_block(cell)
    html_output = process_cell_block(cell_content, lists)
    return html_output

def rename_header(subject, header_text):
    """
    Перейменовує заголовок залежно від предмету та мапінгу.
    """
    if subject == "Пізнаємо природу":
        return HEADER_RENAME_MAPPING.get(header_text.strip(), header_text)
    return header_text

def process_fact_row(text):
    fact_div =  all_styles["fact"].format(text=text)
    return fact_div

def insert_fact_row(text):
    fact_div =  all_styles["fact"].format(text="")
    return fact_div

def process_example_row(text, number_example):
    example_div =  all_styles["example"].format(text=text, number=number_example)
    return example_div


def process_example_row_math(text, number_example):
    text = insert_answer_block(text)
    text = text.split(f"Завдання {number_example}.")[-1]
    
    example_div = custom_styles[CURRENT_SUBJECT]["example"].format(text=text, number_task=number_example)
    return example_div
    

        
        
def process_hello_row(cell, lists):
    """
    Обробляє рядок інтерактивного блоку.
    Форматує інструкції та iframe/посилання.
    """
    html_output = ""
    
    if 'content' in cell:
        for element in cell['content']:
            paragraph_type = 'normal_text'
            
            if 'paragraph' in element:
                paragraph = element['paragraph']
                content_text = ""
                for el in paragraph.get('elements', []):
                    if 'textRun' in el:
                        text_run = el['textRun']
                        content_text += text_run.get('content', '').strip()
                if not content_text:
                    continue
                
                if 'bullet' in paragraph:
                    list_id = paragraph['bullet']['listId']
                    paragraph_type, glyph_type  = get_list_type(list_id, lists)
                    
                if paragraph_type == 'unordered_list' and content_text:
                    unordered_item_div = all_styles["default_unordered_item"].format(item_text=content_text)
                    
                    unordered_item_div = f"<ul class='ulala'>{unordered_item_div}</ul>\n"
                    html_output += f'{unordered_item_div}\n'
                    
                    
                if paragraph_type == 'normal_text' and content_text:
                    html_output += all_styles["default_paragraph"].format(text=content_text)
                
                
    if html_output:
        return html_output
                
                
                
            


def _extract_interactive_title(row):
    """Назва інтерактиву часто стоїть у ТІЙ САМІЙ клітинці НИЖЧЕ фрейму (патерн
    вчителя) — а process_interactive_row рендерить лише iframe і виходить, тому
    назва губиться. Повертаємо plain-текст-параграф, що стоїть ПІСЛЯ iframe
    (короткий, з літерами, без iframe/URL/прочерків), або None."""
    if not row:
        return None
    for cell in row.get("tableCells", []):
        seen_iframe = False
        for element in read_cell_block(cell):
            if "paragraph" not in element:
                continue
            text = "".join(
                pe["textRun"].get("content", "")
                for pe in element["paragraph"].get("elements", [])
                if "textRun" in pe
            ).strip()
            if not text:
                continue
            if "iframe" in text.lower():
                seen_iframe = True
                continue
            if not seen_iframe:
                continue  # текст ПЕРЕД iframe рендерить сам process_interactive_row
            if "http" in text.lower():
                continue
            if re.fullmatch(r"[—–‒―\-\s]+", text):
                continue
            if not re.search(r"[А-ЯҐЄІЇа-яґєіїA-Za-zÄÖÜäöüß]", text):
                continue
            if len(text) > 80:
                continue
            return text
    return None


def process_interactive_row(row, lists):
    """
    Обробляє рядок інтерактивного блоку.
    Форматує інструкції та iframe/посилання.
    """
    html_output = ""
    cells = row['tableCells']
    for cell in cells:
        # ХАРД-ФІКС (тільки «Німецька мова 510»): назва інтерактив-блоку стоїть у
        # тій самій комірці ПІСЛЯ iframe. Стандартна обробка рендерить лише iframe
        # і виходить, тому заголовок губиться. Беремо повний текст комірки, ріжемо
        # по "iframe>" і, якщо після фрейму є текст, ставимо його заголовком ПЕРЕД iframe.
        if CURRENT_SUBJECT == "Німецька мова 510":
            full_cell_text = "".join(
                pe["textRun"].get("content", "")
                for el in read_cell_block(cell) if "paragraph" in el
                for pe in el["paragraph"].get("elements", [])
                if "textRun" in pe
            )
            iframe_full = re.search(r'<iframe[^>]+src="([^"]+)"[^>]*></iframe>', full_cell_text)
            if iframe_full and "iframe>" in full_cell_text:
                title_text = full_cell_text.split("iframe>")[-1].strip()
                if (title_text
                        and re.search(r'[А-ЯҐЄІЇа-яґєіїA-Za-zÄÖÜäöüß]', title_text)
                        and "http" not in title_text.lower()):
                    html_output += custom_styles[CURRENT_SUBJECT]["interactive"]["instruction"].format(instruction_text=title_text) + "\n"
                    html_output += custom_styles[CURRENT_SUBJECT]["interactive"]["iframe"].format(src_url=iframe_full.group(1)) + "\n"
                    return html_output  # заголовок + iframe віддали, виходимо

        cell_content = read_cell_block(cell)
        for element in cell_content:
            if 'paragraph' in element:
                paragraph = element['paragraph']
                content_text = ""
                for el in paragraph.get('elements', []):
                    if 'textRun' in el:
                        text_run = el['textRun']
                        content_text += text_run.get('content', '').strip()
                if not content_text:
                    continue
                
                # вскавка ifrime для wordwall
                
                
                # Перевірка на наявність iframe
                iframe_match = re.search(r'<iframe[^>]+src="([^"]+)"[^>]*></iframe>', content_text)
                if iframe_match:
                    src_url = iframe_match.group(1)
                    html_output += custom_styles[CURRENT_SUBJECT]["interactive"]["iframe"].format(src_url=src_url) + "\n"
                    return html_output  # зупиняємось після першого інтерактиву
                else:

                    if "learningapps.org/" in content_text:
                        if "learningapps.org/view" not in content_text:
                            content_text = content_text.replace("learningapps.org/", "learningapps.org/view")

                    # Перевірка на наявність URL
                    url_match = re.search(r'(https?://\S+)', content_text)

                    if url_match:
                        url = url_match.group(1)
                        # Інструкція текст перед URL (лише якщо містить букви)
                        instruction_text = content_text.split(url)[0].strip()
                        if instruction_text and re.search(r'[А-ЯҐЄІЇа-яґєіїA-Za-z]', instruction_text):
                            if IN_PRACTICE_BLOCK:
                                html_output += f'<p><strong>{instruction_text}</strong></p>\n'
                            else:
                                html_output += custom_styles[CURRENT_SUBJECT]["interactive"]["instruction"].format(instruction_text=instruction_text) + "\n"
                        # Конвертуємо YouTube-посилання у embed-формат
                        if "youtube.com" in url or "youtu.be" in url:
                            embed_url = generate_youtube_embed_url(url)
                            if "/shorts/" in url:
                                html_output += all_styles["youtube_shorts"].format(link=embed_url) + "\n"
                            else:
                                html_output += all_styles["youtube"].format(link=embed_url) + "\n"
                        else:
                            html_output += custom_styles[CURRENT_SUBJECT]["interactive"]["iframe"].format(src_url=url) + "\n"
                        return html_output  # зупиняємось після першого інтерактиву
                    else:
                        # Весь текст - інструкція (лише якщо містить букви)
                        if re.search(r'[А-ЯҐЄІЇа-яґєіїA-Za-z]', content_text):
                            if IN_PRACTICE_BLOCK:
                                html_output += f'<p><strong>{content_text}</strong></p>\n'
                            else:
                                html_output += custom_styles[CURRENT_SUBJECT]["interactive"]["instruction"].format(instruction_text=content_text) + "\n"
    return html_output

_BOOK_URL = {
    # УВАГА: ключ "Українська мова" спільний для УМ3 (3 клас, grade-3-ukrmova-ch2.pdf,
    # офсет 2) і УМ1 (1 клас, буквар, офсет нижче) — CURRENT_SUBJECT в обох однаковий,
    # тому підручник МОЖЕ бути лише один одночасно. Стара версія для УМ3 — в коментарі,
    # якщо колись знадобиться повернути.
    "Українська мова": "https://moodle.example.com/pluginfile.php/19792/mod_resource/content/0/1-klas-ukrmova-bukvar-ischenko-2023-5.pdf",
    "Німецька мова": "https://moodle.example.com/pluginfile.php/8816/mod_resource/content/1/Passwort_Deutsch_2.pdf",
    "Німецька мова 510": "https://moodle.example.com/pluginfile.php/8816/mod_resource/content/1/Passwort_Deutsch_2.pdf",
}
_BOOK_OFFSET = {
    # TODO: офсет під буквар 1 класу не перевірений (0 = без зміщення, звірити на реальному уроці).
    # Старий офсет 2 був підібраний саме під grade-3-ukrmova-ch2.pdf, для букваря не годиться.
    "Українська мова": 0,
    "Німецька мова": -1,
    "Німецька мова 510": -1,
}
# Passwort Deutsch 2 — відповідність книжкова сторінка → PDF сторінка (тільки «Німецька мова 510»).
# Офсет НЕ сталий: у скані відсутні сторінки (40-41, 48-49, 60-61, 80, 161, 178, 186-187),
# тому потрібна явна таблиця, а не book+offset. Пропущений ключ = сторінки нема у PDF.
BOOK_TO_PDF = {
    4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 9: 8, 10: 9, 11: 10, 12: 11, 13: 12, 14: 13, 15: 14,
    16: 15, 17: 16, 18: 17, 19: 18, 20: 19, 21: 20, 22: 21, 23: 22, 24: 23, 25: 24,
    26: 25, 27: 26, 28: 27, 29: 28, 30: 29, 31: 30, 32: 31, 33: 32, 34: 33, 35: 34,
    36: 35, 37: 36, 38: 37, 39: 38, 42: 39, 43: 40, 44: 41, 45: 42, 46: 43, 47: 44,
    50: 45, 51: 46, 52: 47, 53: 48, 54: 49, 55: 50, 56: 51, 57: 52, 58: 53, 59: 54,
    62: 55, 63: 56, 64: 57, 65: 58, 66: 59, 67: 60, 68: 61, 69: 62, 70: 63, 71: 64,
    72: 65, 73: 66, 74: 67, 75: 68, 76: 69, 77: 70, 78: 71, 79: 72, 81: 73, 82: 74,
    83: 75, 84: 76, 85: 77, 86: 78, 87: 79, 88: 80, 89: 81, 90: 82, 91: 83, 92: 84,
    93: 85, 94: 86, 95: 87, 96: 88, 97: 89, 98: 90, 99: 91, 100: 92, 101: 93, 102: 94,
    103: 95, 104: 96, 105: 97, 106: 98, 107: 99, 108: 100, 109: 101, 110: 102, 111: 103,
    112: 104, 113: 105, 114: 106, 115: 107, 116: 108, 117: 109, 118: 110, 119: 111,
    120: 112, 121: 113, 122: 114, 123: 115, 124: 116, 125: 117, 126: 118, 127: 119,
    128: 120, 129: 121, 130: 122, 131: 123, 132: 124, 133: 125, 134: 126, 135: 127,
    136: 128, 137: 129, 138: 130, 139: 131, 140: 132, 141: 133, 142: 134, 143: 135,
    144: 136, 145: 137, 146: 138, 147: 139, 148: 140, 149: 141, 150: 142, 151: 143,
    152: 144, 153: 145, 154: 146, 155: 147, 156: 148, 157: 149, 158: 150, 159: 151,
    160: 152, 162: 153, 163: 154, 164: 155, 165: 156, 166: 157, 167: 158, 168: 159,
    169: 160, 170: 161, 171: 162, 172: 163, 173: 164, 174: 165, 175: 166, 176: 167,
    177: 168, 179: 169, 180: 170, 181: 171, 182: 172, 183: 173, 184: 174, 185: 175,
    188: 176, 189: 177, 190: 178, 191: 179, 192: 180, 193: 181, 194: 182, 195: 183,
    196: 184, 197: 185, 198: 186, 199: 187, 200: 188, 201: 189, 202: 190, 203: 191,
    204: 192, 205: 193, 206: 194, 207: 195, 208: 196, 209: 197, 210: 198, 211: 199,
    212: 200, 213: 201, 214: 202, 215: 203, 216: 204, 217: 205, 218: 206, 219: 207,
    220: 208,
}


def get_pdf_page(book_page: int):
    """PDF-сторінка для книжкової, або None якщо сторінка відсутня у скані."""
    return BOOK_TO_PDF.get(book_page)


_HW_LINK_RE = re.compile(r'\[([^\]]+)\]\s*#(\d+)')


def process_aditional_row(text):
    text = text.replace("<p>", "").replace("</p>", "")
    text_hw = text.split("завдання:")[-1]

    book_url = _BOOK_URL.get(CURRENT_SUBJECT)
    if book_url:
        offset = _BOOK_OFFSET.get(CURRENT_SUBJECT, 0)
        def _make_link(m):
            book_page = int(m.group(2))
            if CURRENT_SUBJECT == "Німецька мова 510":
                # явна таблиця замість офсета (у скані пропущені сторінки)
                pdf_page = get_pdf_page(book_page)
                url = f"{book_url}#page={pdf_page}" if pdf_page is not None else book_url
            else:
                url = f"{book_url}#page={book_page + offset}"
            return f'<a href="{url}" target="_blank">{m.group(1)}</a>'
        text_hw = _HW_LINK_RE.sub(_make_link, text_hw)

    homework_div = custom_styles[CURRENT_SUBJECT]["homework"].format(text=text_hw)
    return homework_div


def process_practice_row(text, number_task):
    div = ""
    # Кастиль щоб стилізацію винести поза межами стилізованого блоку завдання
    if "~~" in text:
        text_block = text.split("~~")[0]
        div += text_block

        text = text.split("~~")[1]


    # Бейдж "Завдання N" вже друкується стилем завдання (task_2) — лідируючий
    # літеральний лейбл "Завдання[ N][:.]" у тілі дублює його. Зрізаємо (render-only,
    # документ не чіпаємо). Анкер: початок рядка / після HTML-тега (>) / після \n.
    if CURRENT_SUBJECT == "Німецька мова 510":
        # Бейдж "Завдання N" вже друкується стилем (task_2); лідируючий лейбл
        # "Завдання[ N][:.]" у тілі — дубль. Зрізаємо й капіталізуємо першу літеру
        # інструкції (анкер: початок / після тега '>' / після \n).
        text = re.sub(
            r'(^|>|\n)\s*Завдання\s*\d*\s*[:.]\s*((?:</?b>\s*)*)([^\s<])',
            lambda m: m.group(1) + m.group(2) + m.group(3).upper(),
            text)
        # лейбл часто був жирним <b>Завдання:</b> — після зрізу лишається <b></b>.
        text = re.sub(r'<b>\s*</b>\s*', '', text)


    key_words = ["<b>Відповідь</b>:",
                 "<b>Відповідь</b>" , 
                 "<b>Відповіді</b>:", 
                 "<b>Відповіді</b>",
                 "<b>Antworten</b>",
                 "Antworten",
                 "Відповідь:",
                 "Відповідь" ,
                 "Відповіді:", 
                 "Відповіді", 
                 "Lösungen (відповіді)"
                 "Перевір себе:",
                 "Перевір себе",
                 
                 ]

    text_task = ""
    text_answer = ""
    for key in key_words:
        if key in text:
            text_task = text.split(key)[0]
            text_answer = text.split(key)[1]
            text_answer = text_answer.replace(key, "")
            break


    if text_task:
        text = text_task

    # чомусь я вирішив в укр мові стилізацію завдань не робити
    if CURRENT_SUBJECT != "Українська мова" and CURRENT_SUBJECT != "Історія України":
    
        if CURRENT_SUBJECT == "Українська література":
            div_task = custom_styles[CURRENT_SUBJECT]["text_task"].format(text=text, number_task=number_task)
        else:
            div_task = custom_styles[CURRENT_SUBJECT]["text_task"].format(text=text)
            
        div_task = div_task.replace("Завдання 1", "Завдання " + str(number_task))
        div += div_task
    

        
    
    elif CURRENT_SUBJECT == "Історія України" or CURRENT_SUBJECT == "Українська мова":
        
        # цей кастиль треба для блоку Реадкторій у Укр мові щоб не було стилізації
        if not IN_REDACTORII_BLOCK:
            text = text.replace("Завдання " + str(number_task) + ".", "")
            
            div_task = custom_styles[CURRENT_SUBJECT]["text_task"].format(text=text, number_task=number_task)
            div += div_task
            
        else:
            div += text
            
        
    
    else:
        div += text
        
        


    if text_answer:
        div_answer = custom_styles[CURRENT_SUBJECT]["answer"].format(text=text_answer)
        if CURRENT_SUBJECT == "Історія України":
            div_answer = div_answer.replace("Відповідь", "Перевір себе")
        div += div_answer
    return div


def insert_answer_block(text):
    
    key_words = ["<b>Відповідь</b>:",
                "<b>Відповідь</b>" , 
                "<b>Відповідь:</b>" , 
                "<b>Відповіді</b>:", 
                "<b>Відповіді</b>",
                "<b>Antworten</b>",
                "Antworten",
                "Відповідь:",
                "Відповідь" ,
                "Відповіді:", 
                "Відповіді", 
                "Lösungen (відповіді)"
                "Перевір себе:",
                "Перевір себе",
                
    ]
    
    text_task = ""
    text_answer = ""
    for key in key_words:
        if key in text:
            text_task = text.split(key)[0]
            text_answer = text.split(key)[1]
            text_answer = text_answer.replace(key, "")
            break
        
    if text_answer:
        answer_div = all_styles["answer_open"].format(text=text_answer)
        text = text_task + answer_div
        
    return text

def generate_youtube_embed_url(youtube_url):
    href_match = re.search(r'href=["\'](https?://(?:www\.)?(?:youtu\.be|youtube\.com|m\.youtube\.com)[^"\']+)["\']', youtube_url)
    if href_match:
        youtube_url = href_match.group(1)

    # Прибираємо HTML-теги та розкодовуємо &amp; → & тощо
    clean_url = re.sub(r'<[^>]+>', '', youtube_url)
    clean_url = html.unescape(clean_url).strip()
    clean_url = re.sub(r"(https?://youtu\.be)(?!/)", r"\1/", clean_url)
    known_youtube_url_fixes = {
        "https://youtu.be/cQBLpiO3Cs": "https://youtu.be/qcQBLpiO3Cs",
    }
    clean_url = known_youtube_url_fixes.get(clean_url, clean_url)

    video_match = re.search(r"(?:v=|youtu\.be/|youtube\.com/shorts/)([\w-]+)", clean_url)
    # підтримуємо як &t= так і &amp;t= (після html.unescape обидва зводяться до &t=)
    start_time_match = re.search(r"[?&]t=(\d+)", clean_url)

    if not video_match:
        raise ValueError(f"Неправильне посилання на YouTube: {clean_url}")

    video_id = video_match.group(1)
    start_time = start_time_match.group(1) if start_time_match else None

    embed_url = f"https://www.youtube.com/embed/{video_id}"
    if start_time:
        embed_url += f"?start={start_time}"

    return embed_url


def process_additional_row(text):
    div = ""
    if "youtube" in text or "youtu.be" in text:
        if "www." in text:
            text = text.replace("www.", "")
            
        link_match = re.search(r'href=["\'](https?://(?:www\.)?(?:youtu\.be|youtube\.com|m\.youtube\.com)[^"\']+)["\']', text)
        if not link_match:
            link_match = re.search(r"https?://(?:youtu\.be/?|youtube\.com/\S+|m\.youtube\.com/\S+)\S*", text)
        if not link_match:
            return None

        if "~~" in text:
            text_block = text.split("~~", 1)[0] + "~~\n"
        else:
            text_block = text[:link_match.start()]
        link_text = link_match.group(1) if link_match.lastindex else link_match.group(0)
        link = generate_youtube_embed_url(link_text)
        if "/shorts/" in text:
            attention_text_row = all_styles["youtube_shorts"].format(link=link)
        else:
            attention_text_row = all_styles["youtube"].format(link=link)
        
        
        attention_text_row = attention_text_row.replace("<u>", "")
        text_block = text_block.replace("<u>", "")
        
        div += text_block
        div += attention_text_row
        return div
    else:
        return None

def process_homework_row(text):
    text = text.replace("<p>", "").replace("</p>", "")
    text_hw = text.split("https")[0]

    book_url = _BOOK_URL.get(CURRENT_SUBJECT)
    if book_url:
        offset = _BOOK_OFFSET.get(CURRENT_SUBJECT, 0)
        def _make_link(m):
            book_page = int(m.group(2))
            if CURRENT_SUBJECT == "Німецька мова 510":
                # явна таблиця замість офсета (у скані пропущені сторінки)
                pdf_page = get_pdf_page(book_page)
                url = f"{book_url}#page={pdf_page}" if pdf_page is not None else book_url
            else:
                url = f"{book_url}#page={book_page + offset}"
            return f'<a href="{url}" target="_blank">{m.group(1)}</a>'
        text_hw = _HW_LINK_RE.sub(_make_link, text_hw)

    homework_div = custom_styles[CURRENT_SUBJECT]["homework"].format(text=text_hw)
    homework_div = homework_div.replace("Hausaufgaben: ", "")
    homework_div = homework_div.replace("Hausaufgaben:", "")
    homework_div = homework_div.replace("Домашнє завдання", "Hausaufgaben")
    homework_div = homework_div.replace("Домашнє\n    завдання", "Hausaufgaben")
    return homework_div


def process_quote_row(text):
    quote_div =  all_styles["quote"].format(text=text)
    return quote_div


def process_term_memo_row(text):
    term_memo_div =  all_styles["term_beautifule"].format(text=text)
    return term_memo_div


def process_litweb_row(text):
    litweb_div =  all_styles["litweb"].format(text=text)
    return litweb_div


def process_creative_project_row(text, header_name):
    text = text.replace("Творчий проєкт", "").replace(header_name, "")
    creative_project_div =  all_styles["creative_project"].format(text=text, header_name=header_name)
    return creative_project_div

def get_clear_text(subject_name):
    separators = [ " (", ","]
    for separator in separators:
        if separator in subject_name:
            subject_name = subject_name.split(separator)[0]
            
            # костиль
            if " (" in separator and "," in subject_name:
                subject_name = subject_name.split(",")[0]

            break
    return subject_name


def extract_row_title(row):
    """
    Витягує назву заголовка з рядка таблиці.
    """
    for cell in row.get('tableCells', []):
        cell_text = ""
        cell_style = cell.get('tableCellStyle', {})
        column_span = cell_style.get('columnSpan', 1)


        # Зчитуємо колір фону комірки
        background_color = cell_style.get('backgroundColor', {}).get('color', {})
        color_rgb = background_color.get('rgbColor', {})

        if column_span > 2 or background_color:  # Перевірка об'єднаних комірок
    
            for content in cell['content']:
                for text_element in content.get('paragraph', {}).get('elements', []):
                    if 'textRun' in text_element:
                        cell_text += text_element['textRun']['content'].strip()

                    
            if "Оціни свої старання на уроці" in cell_text:
                pass
            return cell_text  # Повертаємо назву
                        

    return ""  # Якщо заголовок не знайдено


def extract_row(row):
    """
    Витягує назву заголовка з рядка таблиці.
    """
    cell_text = ""

    for cell in row['tableCells']:
        for content in cell['content']:
            for text_element in content.get('paragraph', {}).get('elements', []):
                if 'textRun' in text_element:
                    cell_text += text_element['textRun']['content']


    return cell_text  # Повертаємо назву
                    

    return ""  # Якщо заголовок не знайдено

# Чи вже пронумероване питання в самому тексті («1. Питання…») — тоді номер
# з 1-ї колонки не підставляємо, щоб не вийшло «1. 1. Питання…».
_TEST_NUMBERED_RE = re.compile(r'<p[^>]*>\s*(?:<[^>]+>\s*)*\d{1,2}\s*\.\s')


def raw_cell_text(cell):
    """Сирий текст комірки БЕЗ побічних ефектів.
    process_cell() тягне за собою process_text_elements(), який мутує глобальний
    стан (лічильники списків тощо) — для простого зчитування номера питання
    це ламало розбір наступних комірок."""
    parts = []

    def walk(node):
        if isinstance(node, dict):
            if 'textRun' in node:
                parts.append(node['textRun'].get('content', ''))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(cell)
    return "".join(parts).strip()


def parce_test_text(test_text):
    global CURRENT_SUBJECT
    # test_text
    test_text = test_text.replace('\x0b', '</p><p>')
    # Використовуємо BeautifulSoup для парсингу HTML
    soup = BeautifulSoup(test_text, 'html.parser')

    # Зберігатимемо питання та відповіді
    questions = []

    # Знаходимо всі абзаци <p>
    paragraphs = soup.find_all('p')
    bs = soup.find_all('b')
    questions_texts = [b.get_text(strip=True) for b in bs if b.get_text(strip=True)]
    

    current_question = None
    answers = []

    describe_text = ""
    describe_section = False

    for p in paragraphs:

        text = p.get_text()
 
        # це обробка питання опису
        if "{{" in text:
            describe_section = True
            text = text.replace("{{","")


        if describe_section:
            describe_text += text
            
            if "}}" not in text:
                continue

        if "}}" in text:
            describe_section = False
            describe_text = describe_text.replace("}}","")
            current_question = describe_text

            # так я знизу стоїть пропуск при пустому елементі то опис додаємо окремо
            questions.append({
                'type': 'description',
                'question': current_question,
                'answers': []
            })
            # current_question треба збивати бо тоді опис ще раз вставляє як питання
            current_question = None
            continue


        if "" == text:
            continue

        # Кастиль для відповідей якщо там тільки цифра.
        if len(text) == 1:
            text += " "
            
        if len(text) == 2:
            text += " "


        # Якщо текст виглядає як нове питання
        is_answer = False
        is_question = False
        spans = p.find_all('span')
        for span in spans:
            pass
        if any(
            ('background_color' in span.get('class', []) 
            or 'background-color' in span.get('style', '') 
            or 'color' in span.get('style', ''))
            for span in spans):
            is_answer = True
            
        if text in questions_texts:
            is_question = True
            
        
        
        if (text[0].isdigit() and text[1] == '.')\
            or (text[0].isdigit() and text[1].isdigit() and text[2] == '.'):
                # and (not is_answer):

            text = text.split(". ")[1:]
            text = ". ".join(text).strip()


            # Зберігаємо попереднє питання, якщо воно було
            if current_question:
                questions.append({
                    'type': 'multichoice',
                    'question': current_question,
                    'answers': answers
                })
            # Починаємо нове питання
            current_question = text
            answers = []
        
        elif CURRENT_SUBJECT in ("Українська мова", "Українська література") and is_question:
            if current_question:
                questions.append({
                    'type': 'multichoice',
                    'question': current_question,
                    'answers': answers
                })
            # Починаємо нове питання
            current_question = text
            answers = []
        
        else:
            if CURRENT_SUBJECT != "Математика":
                text = text.split(") ")[-1]
            text = text.split("А. ")[-1]
            text = text.split("Б. ")[-1]
            text = text.split("В. ")[-1]
            text = text.split("Г. ")[-1]
            
            text = text.split("A. ")[-1]
            text = text.split("B. ")[-1]
            text = text.split("C. ")[-1]
            text = text.split("D. ")[-1]
            
            if CURRENT_SUBJECT == "Історія України":
                text = text.split("А ")[-1]
                text = text.split("Б ")[-1]
                text = text.split("В ")[-1]
                text = text.split("Г ")[-1]
                
                text = text.split("а) ")[-1]
                text = text.split("б) ")[-1]
                text = text.split("в) ")[-1]
                text = text.split("г) ")[-1]
            
            if CURRENT_SUBJECT in ("Українська мова", "Пізнаємо природу"):
                text = text.split("А) ")[-1]
                text = text.split("Б) ")[-1]
                text = text.split("В) ")[-1]
                text = text.split("Г) ")[-1]
                
                
            if CURRENT_SUBJECT == "Зарубіжна література":
                text = text.split("А. ")[-1]
                text = text.split("Б. ")[-1]
                text = text.split("В. ")[-1]
                text = text.split("Г. ")[-1]
                

            # # Перевіряємо виділення через стилі


            
                


            # Додаємо відповіді, відмічаючи правильну
            text = text.replace(";", "").replace(".", "")
            if p.find('b') or (CURRENT_SUBJECT == "Історія України" and '+' in text):
                if "+" in text:
                    text = text.replace("+","")
                    
                answers.append({'text': text, 'correct': True})
                
            elif is_answer:
                answers.append({'text': text, 'correct': True})
            else:
                answers.append({'text': text, 'correct': False})

    # Зберігаємо останнє питання
    if current_question:
        questions.append({
            'type': 'multichoice',
            'question': current_question,
            'answers': answers
        })
    return questions


def create_moodle_xml(questions, code_subject=""):
    """
    Генерує XML у форматі Moodle (multichoice) із переданого списку питань.

    :param questions: список словників такого формату:
        [
          {
            "question": "1. Питання...",
            "answers": [
              {"text": "a) Варіант 1", "correct": False},
              {"text": "b) Варіант 2", "correct": True},
              ...
            ]
          },
          ...
        ]
    :param code_subject: код предмету (опціонально)
    :param shorten_name: Якщо True, залишає тільки код предмету у <name>
    :return: Рядок XML (pretty-printed)
    """

    shorten_name=True


    # Створюємо кореневий елемент <quiz>
    quiz_el = etree.Element("quiz")
    

    # Кількість питань
    total_questions = len(questions)

    for idx, item in enumerate(questions):
        
         # Визначаємо кількість правильних відповідей
        correct_answers = [ans for ans in item["answers"] if ans["correct"]]
        multiple_correct = len(correct_answers) > 1  # Якщо більше 1 правильної відповіді
        
        
        
        
        question_type = item.get("type", "multichoice") 
        question_el = etree.SubElement(quiz_el, "question", {"type": question_type})

        # 1) <name>
        name_el = etree.SubElement(question_el, "name")
        name_text_el = etree.SubElement(name_el, "text")
        
        if shorten_name and code_subject:
            name_text_el.text = code_subject  # Лише код предмету
        elif code_subject:
            if question_type == "multichoice":
                name_text_el.text = f"{code_subject}: {item['question']}"
            else:
                name_text_el.text = f"{code_subject}: {' Опис'}"

        else:
            name_text_el.text = item["question"]

        # 2) <questiontext format="html">
        questiontext_el = etree.SubElement(question_el, "questiontext", {"format": "html"})
        questiontext_text_el = etree.SubElement(questiontext_el, "text")
        questiontext_text_el.text = etree.CDATA(item["question"])


         # Якщо тип питання "description", не додаємо відповіді
        if question_type == "multichoice":
            
            fraction_value = 100 / len(correct_answers) if multiple_correct else 100
            
            
            # 3) Варіанти відповідей
            random.shuffle(item["answers"])
            for ans in item["answers"]:
                fraction_val = str(fraction_value) if ans["correct"] else "0"
                answer_el = etree.SubElement(question_el, "answer", {"fraction": fraction_val})
                answer_text_el = etree.SubElement(answer_el, "text")
                answer_text_el.text = ans["text"]
           
            # 4) <defaultgrade>
            defaultgrade_el = etree.SubElement(question_el, "defaultgrade")
            if IS_GRADE_1:
                # 1 клас: рівний бал за кожне з 4 питань (4 × 2.5 = 10)
                defaultgrade_el.text = QUIZ_GRADE_GRADE_1
            elif idx < total_questions - 1:
                defaultgrade_el.text = "1.6"
            else:
                defaultgrade_el.text = "2"

    # Генеруємо XML-рядок
    xml_string = etree.tostring(quiz_el, pretty_print=True, encoding="utf-8").decode("utf-8")
    return xml_string


def process_table_with_details(table, lists):
    global FULL_WIDTH_HEADERS_COUNT, IN_HELLO_BLOCK, IN_THEORY_BLOCK, IN_INTERACTIVE_BLOCK, IN_TEST_BLOCK, IN_ADDITIONAL_BLOCK, \
    IN_EXAMPLE_BLOCK, IN_PRACTICE_BLOCK, IN_FINAL_BLOCK, AFTER_TEST_BLOCK, FACT_BLOCK, LITWEB_BLOCK, TERM_MEMO_BLOCK, IN_REDACTORII_BLOCK
    global code_subject, SKIP_SECTION_HEADER_NAME
    html_output = ""
    test_text = ""
    number_example = 0
    number_task = 0
    is_write_description = False
    h5p_task = []

    cache_dir = H5P_CACHE_DIR
    cache_path = os.path.join(cache_dir, f"{code_subject}.json")
    h5p_cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as _f:
            try:
                for _item in json.load(_f):
                    h5p_cache[_item["title"]] = _item
            except Exception:
                pass
    
    # цей кастиль треба для Історії україіни 1 семестру бо по середині теорії є колонка з фактами
    # і це треба щоб знову заголовок теорії не вставлявся
    theory_counter = 0
    
        
    # ця зміна треба для того щоб рахувати кількість h5p вправ у теорії або повторення
    # зазвичай ця фігня у Німецькій мові з 5 по 10 клас
    h5p_counter = 1

    # рядки, чий текст уже спожито як назву інтерактиву (стоїть нижче фрейму) → пропускаємо
    _interactive_title_skip = set()

    for row_index, row in enumerate(table['tableRows']):
        if row_index in _interactive_title_skip:
            continue
        is_check_title = False
        is_added_header = False

        row_title = extract_row_title(row)
        
        
        # пропускаємо пусті блоки
        # Перевіряємо, чи існує наступний рядок
        if row_index + 1 < len(table['tableRows']):
            next_row = table['tableRows'][row_index + 1]
        else:
            next_row = None  # Останній рядок не має наступного
        
        if row_title:
            if next_row:
                next_row_title = extract_row(next_row).replace("\n", "").strip()
                # Порожній розділ: наступний рядок містить лише залишковий шаблон відео
                # "*відео може не відтворюватись" (без @ — не справжній підпис) та/або
                # прочерки «—----» (вчитель ставить замість контенту, напр. Spiel Spaß!).
                # Прибравши шаблон і перевіривши решту: якщо лишилися лише тире або нічого —
                # секція порожня. Шаблон+тире в одному рядку теж покривається.
                if "@" not in next_row_title:
                    next_row_title = next_row_title.replace("*відео може не відтворюватись", "").rstrip("!").strip()
                if next_row_title == "" or re.fullmatch(r'[—–‒―\-\s]+', next_row_title):
                    continue
        
        
        
        
        if "повторення" in row_title:
            pass

        extract_row_text = extract_row(row)
        if "Інтересанте факт" in extract_row_text:
            print(f"extract_row_text - {extract_row_text}")

            pass

        if row_title not in "":
            print(f"row_title - {row_title}")
        d =3
        for cell in row.get('tableCells', []):
                
            # кастиль для німецької мови бо там вже нові назви
            if CURRENT_SUBJECT == "Німецька мова 510":
                # Німецька мова 10 клас
                HEADER_RENAME_MAPPING_germany = {
                    "Привітання": "Привітання",
                    "Секрети мови": "Теорія",
                    "Швидке оновлення": "повторення",
                    "Мова в дії": "Приклади", # Приклади
                    "Deutsch Minuten": "Практика", # Практика
                    "Словник": "Словник",
                    "Інтересанте факт": "Інтересанте факт",
                    "Spiel Spa": "Інтерактив",  # Інтерактив
                    "Deutsch Test": "Тест",  # Інтерактив
                    "Meine Möglichkeiten": "Рефлексія",  # Інтерактив
                    "Andere": "Додатки", # Додатки
                    "Finale": "Фінал"
                }
                


            if row_title not in "" and CURRENT_SUBJECT == "Німецька мова 510":
                if is_added_header:
                    continue
                for key, value in HEADER_RENAME_MAPPING_germany.items():
                    if key.lower() in row_title.lower() or row_title.lower() in key.lower():  # Перевірка наявності ключа в заголовку
                        row_title = HEADER_RENAME_MAPPING_germany.get(key, "")
                        if row_title in HEADER_RENAME_MAPPING.keys():

                            is_added_header = True
                            # Перейменування заголовків
                            row_title_text = HEADER_RENAME_MAPPING.get(row_title, row_title)
                            html_output += header_for_subject(row_title_text)
                            SKIP_SECTION_HEADER_NAME = row_title_text

                        break


            cell_style = cell.get('tableCellStyle', {})
            column_span= cell_style.get('columnSpan', 1)
            background_color = cell_style.get('backgroundColor', {}).get('color', {})

            if row_title not in "" and column_span == 1:
                column_span = 3
            if column_span > 2:

                
                is_check_title = True
                row_title = get_clear_text(row_title)

                FULL_WIDTH_HEADERS_COUNT += 1
                
                    
                    # зазвичай блок привітанння не друкується тому він не враховується, але в укр мові він друкується
                    # там в коді я спєцом поставив щоб цей блок не враховувався
                    
                    
                    
                    
                    
                    
                    

                    
                    
                
                if "Теорія" in row_title:
                    IN_THEORY_BLOCK = True
                    row_title = "Теорія"
                    
                    IN_HELLO_BLOCK = False
                    FACT_BLOCK = False
                    IN_EXAMPLE_BLOCK = False
                    IN_PRACTICE_BLOCK = False
                    
                    is_write_description = True
                    theory_counter += 1
                    

                if CURRENT_SUBJECT == "Українська мова" or CURRENT_SUBJECT == "Українська література":
                    if "Теорія" in row_title or "Територія теорії" in row_title:
                        IN_THEORY_BLOCK = True
                        row_title = "Територія теорії"  
                        IN_HELLO_BLOCK = False
                        is_write_description = True
                        
                        
                    if "Мрійко-пригадайко" in row_title:
                        IN_THEORY_BLOCK = True
                        
                        IN_HELLO_BLOCK = False
                        is_write_description = True
                        
                if "Привітання" in row_title:
                    IN_HELLO_BLOCK = True
                
                
                if IN_THEORY_BLOCK:
                    
                    
                    IN_HELLO_BLOCK = False
                    

                if CURRENT_SUBJECT == "Німецька мова 510":
                    if "Секрети мови" in row_title or "Словник" in row_title or "повторення" in row_title or "Швидке оновлення" in row_title:
                        IN_THEORY_BLOCK = True
                        IN_HELLO_BLOCK = False
                        
    

                if "Цікавий факт" in row_title:
                    FACT_BLOCK = True
                    print(f"Цікавий")

                if "Приклади" in row_title:
                    FACT_BLOCK = False
                    
                    IN_EXAMPLE_BLOCK = True
                    
                    if CURRENT_SUBJECT == "Німецька мова 510":
                        IN_EXAMPLE_BLOCK = False
                        
                    
                    pass
                        
                        

                if "Практика" in row_title:
                    IN_EXAMPLE_BLOCK = False
                    
                    IN_PRACTICE_BLOCK = True
                    FACT_BLOCK = False
                
                key_row_history = [
                    "Робота з картою",
                    "Важливі дати та події",
                    "Словник",
                ]
                
                if any(key in row_title for key in key_row_history):
                    IN_PRACTICE_BLOCK = False
                    
                
                
                if CURRENT_SUBJECT == "Українська мова":
                    if "Редакторій" in row_title:
                        IN_REDACTORII_BLOCK = True
                    
                if CURRENT_SUBJECT == "Українська література":
                    if "Мудровміння" in row_title:
                        IN_PRACTICE_BLOCK = True


                if "Інтерактив" in row_title:
                    IN_THEORY_BLOCK = False
                    IN_PRACTICE_BLOCK = False
                    FACT_BLOCK = False


                    IN_INTERACTIVE_BLOCK = True
                else:
                    IN_INTERACTIVE_BLOCK = False
                    if CURRENT_SUBJECT == "Українська мова" or CURRENT_SUBJECT == "Українська література":
                        if "Взаємодійка" in row_title:
                            IN_THEORY_BLOCK = False
                            IN_PRACTICE_BLOCK = False
                            LITWEB_BLOCK = False


                            IN_INTERACTIVE_BLOCK = True
                            row_title = "Взаємодійка"

                if "Тест" in row_title:
                    IN_THEORY_BLOCK = False
                    IN_PRACTICE_BLOCK = False
                    IN_TEST_BLOCK = True

                if "Додатки" in row_title or "Рефлексія" in row_title:
                    IN_ADDITIONAL_BLOCK = True
                    TERM_MEMO_BLOCK = False
                    IN_TEST_BLOCK = False
                    IN_PRACTICE_BLOCK = False
                    

                    if CURRENT_SUBJECT in [
                        "Математика", 
                        "Зарубіжна література", 
                        "Історія України", 
                        "Українська мова", 
                        "Українська література", 
                        "Пізнаємо природу", 
                        "Німецька мова", 
                        "Німецька мова 510"
                        ]:
                        IN_THEORY_BLOCK = True
                        


                if "Додатки" in row_title or "Фінал" in row_title:
                    IN_TEST_BLOCK = False


                # розділ Цитатоскоп / Мемоскоп в укр літ
                if "Цитатоскоп" in row_title or "Мемоскоп" in row_title:
                    IN_PRACTICE_BLOCK = False
                    IN_TEST_BLOCK = False
                    IN_ADDITIONAL_BLOCK = False
                    TERM_MEMO_BLOCK = True

                if CURRENT_SUBJECT == "Українська література" or CURRENT_SUBJECT == "Українська мова":
                    if "Емоційний фейс-контроль" in row_title: 
                        TERM_MEMO_BLOCK = False
                        IN_FINAL_BLOCK = True

                if CURRENT_SUBJECT == "Німецька мова" or CURRENT_SUBJECT == "Німецька мова 510":
                    if "Фінал" in row_title: 
                        IN_FINAL_BLOCK = True
                    
                        IN_THEORY_BLOCK = True


                if CURRENT_SUBJECT == "Українська мова" or CURRENT_SUBJECT == "Українська література":
                    if "Літмережа" in row_title: 
                        row_title = "Літмережа"
                        IN_PRACTICE_BLOCK = False
                        LITWEB_BLOCK = True

                if "Фінал" in row_title:

                    print(f"Фінал")

                if "Словник" in row_title:
                    IN_EXAMPLE_BLOCK = False
                    IN_HELLO_BLOCK = False
                    IN_THEORY_BLOCK = True
                    
                    print(f"Словник")


                # Визначаємо, чи це заголовок за мапінгом
                if CURRENT_SUBJECT != "Німецька мова 510":
                    if "Теорія" in row_title and theory_counter > 1:
                        break
                    else:
                        row_title = row_title.strip()
                        if row_title in HEADER_RENAME_MAPPING.keys():
                            renamed_header = HEADER_RENAME_MAPPING.get(row_title, row_title)

                                # Додаємо заголовок до HTML
                            html_output += header_for_subject(renamed_header)
                            SKIP_SECTION_HEADER_NAME = renamed_header
                        break

        

        


        if not is_check_title:
            cells = row['tableCells']
            if len(cells) < 1:
                continue
            if IN_INTERACTIVE_BLOCK:
                # Обробка інтерактивного блоку
                html_output += process_interactive_row(row, lists)
                continue  # Пропускаємо звичайну обробку рядка
            
            if IN_TEST_BLOCK:
                AFTER_TEST_BLOCK = True
                # Кожне питання — окремий рядок таблиці, а його НОМЕР вчитель пише
                # в 1-й колонці (cell[0]), не в тексті. parce_test_text() очікує
                # «N. » на початку питання, тому підставляємо номер самі.
                # Так не треба переписувати клітинку в Google Doc — а саме перезапис
                # (delete+insert+reset style) стирав зелену заливку правильної відповіді.
                _q_num = ""
                if len(cells) > 0:
                    _num_m = re.fullmatch(r'(\d{1,2})\s*[.)]?', raw_cell_text(cells[0]))
                    if _num_m:
                        _q_num = _num_m.group(1)

                for i in range(2, -1, -1):
                    if i < len(cells):
                        cell_text = process_cell(cells[i], lists, i).strip()
                        logging.info(f"Рядок {row_index + 1}, Комірка для тексту: '{cell_text}'")
                        if cell_text:
                            if _q_num and i > 0 and not _TEST_NUMBERED_RE.search(cell_text):
                                cell_text = re.sub(
                                    r'(<p[^>]*>)\s*(?=\S)',
                                    rf'\g<1>{_q_num}. ',
                                    cell_text,
                                    count=1,
                                )
                                logging.info(
                                    f"Рядок {row_index + 1}: номер питання {_q_num} узято з 1-ї колонки"
                                )
                            test_text += cell_text
                            break
                print(f"test_text - {test_text}")
                
                
                continue

            if AFTER_TEST_BLOCK and not IN_TEST_BLOCK:
                delete_lete = [
                    "✔️",
                    "▫️",
                ]
            
                for item in delete_lete:
                    if item in test_text:
                        test_text = test_text.replace(item, "")
                        
                questions = parce_test_text(test_text)
                xml_output = create_moodle_xml(questions, code_subject)
                
                # Збереження у файл
                with TEST_OUTPUT_XML.open("w", encoding="utf-8") as f:
                    f.write(xml_output)

                print("XML-файл 'test_output.xml' успішно згенеровано!")
                        
            
            
            
            main_text = ""
            _current_zagl_n = None
            for i in range(2, -1, -1):
                if i < len(cells):
                    cell_text = process_cell(cells[i], lists, i).strip()
                    logging.info(f"Рядок {row_index + 1}, Комірка для тексту: '{cell_text}'")


                    if cell_text or "!=" in cell_text:
                        if "!=" in cell_text:
                            cell_text = cell_text.replace("!=","")
                        main_text = cell_text
                        _zagl_m = re.search(r'[Зз]аглушка(\d+)', main_text)
                        if _zagl_m:
                            _current_zagl_n = int(_zagl_m.group(1))
                        break
                    
            image_info = ""
            image_urls = {}
            if len(cells) > 3:
                images = extract_image_title_from_rich_links(cells[3])
                image_urls = extract_rich_link_urls(cells[3])

                if images:  # Перевіряємо, чи список не порожній
                    for image in images:
                        image_info = f"{html.escape(image)}"
                        logging.info(f"Рядок {row_index + 1}, Заголовок зображення: '{image}'")
                        


          


            
            if IN_HELLO_BLOCK:
                is_check_title = True
                    
                if len(cells) > 3:
                    cells = row['tableCells']
                    baner_images = extract_image_title_from_rich_links(cells[3])
                    if baner_images:
                        global BANER_NAME
                        global CART_NAME
                        BANER_NAME = baner_images[0]
                        
                        is_write_description = True
                        
                        

                # запис опису до уроку
                if is_write_description:
                    cell_text = process_hello_row(cells[2], lists)
                    is_write_description = False

                    if cell_text is not None:
                        cell_text = cell_text.replace('<p>Ти дізнаєшся:</p>', "<b>Ти дізнаєшся:</b>")
                        cell_text = cell_text.replace('<p>На уроці ти дізнаєшся:</p>', "<b>На уроці ти дізнаєшся:</b>")
                        cell_text = cell_text.replace('<p>Сьогодні ти дізнаєшся:</p>', "<b>Сьогодні ти дізнаєшся:</b>")
                        cell_text = cell_text.replace('<p>Ти пригадаєш:</p>', "<b>Ти пригадаєш:</b>")
                        cell_text = cell_text.replace('<p>Ти дізнаєшся про:</p>', "<b>Ти дізнаєшся про:</b>")
                        with DESCRIPTION_TXT.open("w", encoding="utf-8") as file:
                            file.write(cell_text)        
                            
            
                    html_output = html_output.replace('<p><p class="quote">Копірайтер</p></p>', "")
                
                
                # пропускаємо запис блоку привітання
                if CURRENT_SUBJECT != "Німецька мова 510" and CURRENT_SUBJECT != "Українська мова":
                    continue


            #     description_text = extract_image_title_from_rich_links(cells[])


            if main_text:
                
                
                
                # цей кастиль у уроках з німецької мови де презентація міняє слайд на назву фото, у тому випадку якщо дизайнер підписав як 1.png
                if CURRENT_SUBJECT == "Німецька мова":
                    for index_slide in range(1, 10):
                        find_text1 = f"Слайд {str(index_slide)}"
                        find_text2 = f"слайд {str(index_slide)}"
                        if find_text1 in main_text:
                            main_text = main_text.replace(find_text1, f"{str(index_slide)}.png")

                        if find_text2 in main_text:
                            main_text = main_text.replace(find_text2, f"{str(index_slide)}.png")


                if FACT_BLOCK:

                    # Розраховано на той випадок якщо факт знаходиться в одній клітині
                    
                    
                    if CURRENT_SUBJECT == "Математика":
                        before_text = main_text
                        main_text = insert_fact_row(main_text)
                        main_text += before_text
                        
                    sub = [
                        "Зарубіжна література",
                        "Німецька мова",
                        "Пізнаємо природу",
                        "Історія України",
                        "Українська мова",
                        "Українська література",
                    ]
                        
                    if CURRENT_SUBJECT in sub:
                        main_text = process_fact_row(main_text)
                    
                    
                if IN_EXAMPLE_BLOCK and not FACT_BLOCK:
                    if CURRENT_SUBJECT != "Німецька мова" and CURRENT_SUBJECT != "Математика" and CURRENT_SUBJECT != "Зарубіжна література":
                        number_example += 1
                        main_text = process_example_row(main_text, number_example)

                    if CURRENT_SUBJECT == "Математика":
                        number_example += 1
                        main_text = process_example_row_math(main_text, number_example)


                if TERM_MEMO_BLOCK:
                    main_text = process_term_memo_row(main_text)

                # ще один кастиль для німецької мови 11 клас на випадок якщо є якись інтерактив в теорії
                # ну і як оказалось не тільки для німецької мови
                if "<iframe" in main_text or "&lt;iframe" in main_text:
                    _prefix = ""
                    if "~~" in main_text:
                        _prefix = main_text.split("~~")[0] + "~~\n"
                    _iframe_html = process_interactive_row(row, lists)
                    if not IN_PRACTICE_BLOCK:
                        # iframe = інтерактив, навіть якщо row_title порожній і блок не
                        # розпізнався як "Інтерактив" (напр. інтерактив всередині Теорії
                        # без заголовка-секції). Якщо ж це iframe усередині "Завдання N"
                        # (Практика) — режим НЕ перемикаємо, рядок нумерується як завжди.
                        IN_INTERACTIVE_BLOCK = True
                        # назва інтерактиву часто стоїть НИЖЧЕ фрейму у ТІЙ САМІЙ клітинці —
                        # process_interactive_row її губить; підтягуємо ЗВЕРХУ як заголовок.
                        _it_title = _extract_interactive_title(row)
                        if _it_title:
                            _it_head = custom_styles[CURRENT_SUBJECT]["interactive"]["instruction"].format(instruction_text=_it_title)
                            _iframe_html = _it_head + "\n" + _iframe_html
                    main_text = _prefix + _iframe_html

                if IN_THEORY_BLOCK:
                    if "Подивись, послухай" in main_text:
                        print(f"Подивись, послухай")
                        


                # дай відповді це костиль до Німецької мови 11 клас
                # (фраза-детект ігнорує iframe-рядки поза Практикою — вони йдуть в Інтерактив;
                # але iframe УСЕРЕДИНІ Практики (IN_PRACTICE_BLOCK) нумерується як завжди)
                if IN_PRACTICE_BLOCK or ("<iframe" not in main_text and (
                    "Дай відповіді на питання!" in main_text \
                    or "Дай відповідь на питання." in main_text \
                    or "Дай відповіді на питання." in main_text \
                    or "Обери правильні варіанти відповідей." in main_text)):
                    # Порожнє завдання з прочерками (вчитель ставить «—-------» як заглушку
                    # зайвого завдання) — не рендеримо й не нумеруємо.
                    _plain_task = re.sub(r'<[^>]+>', '', main_text).strip()
                    if _plain_task and re.fullmatch(r'[—–‒―\-\s]+', _plain_task):
                        continue
                    number_task += 1
                    if main_text:
                        main_text = process_practice_row(main_text, number_task)

                if IN_ADDITIONAL_BLOCK:
                    # Порожній розділ Andere: лишився тільки мігруючий шаблон
                    # "*відео може не відтворюватись" (без @ — тобто не справжній підпис під відео).
                    # Фактично секція порожня — не рендеримо цей рядок.
                    if "@" not in main_text:
                        _plain_add = re.sub(r'<[^>]+>', '', main_text)
                        _plain_add = _plain_add.replace("*відео може не відтворюватись", "").rstrip("!").strip()
                        if _plain_add == "" or re.fullmatch(r'[—–‒―\-\s]+', _plain_add):
                            continue
                    text_additional = process_additional_row(main_text)

                    if text_additional is not None:
                        main_text = text_additional

                if "Домашнє завдання" in main_text or "Домашні завдання" in main_text:

                    main_text = process_aditional_row(main_text)

                    div_book = homework_book_embed(code_subject)
                    if div_book:
                        main_text += div_book

                if "Творчий проєкт" in main_text:
                    header_name = "Творчий проєкт"
                    main_text = process_creative_project_row(main_text, header_name)

                if CURRENT_SUBJECT == "Німецька мова 510" and IN_FINAL_BLOCK:
                    if "Hausaufgaben" in main_text:
                        main_text = process_homework_row(main_text)

                html_output += paragraph_for_subject(main_text)
                
            

            if image_info:
                
                if IN_HELLO_BLOCK:
                    continue
                    
                
                    
                for image_name in images:
                    placeholders = [
                        "<p>*photo*</p>", 
                        "<p>картинка</p>", 
                        "<p>картинка<b>\n</b></p>",
                        "<p>*картинка</p>",
                        "<p>*картинка<b>\n</b></p>",
                        "<p><b>*</b>картинка</p>",
                        "<p>*картинка персонажа</p>",
                        "<p><b>*картинка персонажа</b></p>",
                        
                        
                        
                        
                    ]
                    # PDF зі сценарію: у статтю йде картинка, зроблена з цього PDF
                    # (назва з .png — інакше insert_photo плейсхолдер не впізнає),
                    # а одразу після неї — посилання на сам PDF з Drive-URL сценарію.
                    _is_pdf = image_name.lower().endswith(".pdf")
                    _shown_name = pdf_image_name(image_name) if _is_pdf else image_name
                    replacement = f"<p class='img_article'>{_shown_name}</p>"
                    if _is_pdf:
                        _pdf_url = image_urls.get(image_name, "")
                        if _pdf_url:
                            replacement += (
                                f'\n<p><a href="{_pdf_url}" target="_blank" rel="noopener">'
                                f'Посилання на "{image_name}"</a></p>'
                            )
                        else:
                            logging.warning(
                                f"PDF '{image_name}' без URL у сценарії — посилання не вставлено"
                            )

                    for placeholder in placeholders:
                        if placeholder in html_output:
                            html_output = html_output.replace(placeholder, replacement, 1)
                            break
                    else:
                        # Якщо маркерів не залишилося – додаємо зображення в кінець
                        html_output += replacement
                        
                        
                html_output = html_output.replace(f'<p class="img_article">{BANER_NAME}</p>', "")        
                html_output = html_output.replace(f'{BANER_NAME}', "")      
                
                html_output = html_output.replace(f'<p class="img_article">{CART_NAME}</p>', "")        
                html_output = html_output.replace(f'{CART_NAME}', "")     
                
                
                
                
            # збір інфи для h5p вправ
            data_h5p_task = get_h5p_task(cells[4], lists)
            if data_h5p_task:
                name_curent_h5p_task = ""
                
                
                if IN_THEORY_BLOCK:
                    name_curent_h5p_task = f"ВП {str(h5p_counter)}"
                    
                    
                    h5p_counter +=1
                
                if IN_PRACTICE_BLOCK:
                    name_curent_h5p_task = f"Вправа {str(number_task)}"
                    
                    
                    
                code_subject_split = code_subject.split(" ")
                sub_code = code_subject_split[0]
                lesson_num = code_subject_split[1]
                                    
                sub_code_name = sub_code[:2]
                sub_code_class = sub_code[2:]
                sub_class = str(sub_code_class)
                
                
                
                if "НМ" in sub_code:
                    sub_name = "Німецька мова"
                    
                elif "УМ" in sub_code:
                    sub_name = "Українська мова"
                
                elif "УЛ" in sub_code:
                    sub_name = "Українська література"
                
                elif "ПП" in sub_code:
                    sub_name = "Пізнаємо природу"
                
                elif "ЗЛ" in sub_code:
                    sub_name = "Зарубіжна література"
                
                elif "ІУ" in sub_code:
                    sub_name = "Історія України"
                elif "М" in sub_code:
                    sub_name = "Математика"
                    
                    
                        
                    
                title_h5p = f"{sub_name}, {sub_class}, Урок {lesson_num}, {name_curent_h5p_task}"
                data_h5p_task["title"] = title_h5p

                _zagl_n = _current_zagl_n if _current_zagl_n is not None else len(h5p_task) + 1

                cached = h5p_cache.get(title_h5p, {})
                data_h5p_task["html_code"] = cached.get("html_code", "")
                data_h5p_task["url_task"] = cached.get("url_task", "")
                data_h5p_task["n"] = _zagl_n  # завжди береться з документа, кешований n ігнорується

                h5p_task.append(data_h5p_task)

    for i, task in enumerate(h5p_task, 1):
        if task["html_code"]:
            n = task.get("n") or i
            placeholder = f'<p>заглушка{n}</p>\n<div style="max-width: 720px; padding: 10px; background: white;"></div>'
            replacement = f'<div style="max-width: 720px; padding: 10px; background: white;">\n{task["html_code"]}\n</div>'
            html_output = html_output.replace(placeholder, replacement)

    # напівгібрид (rework наявних H5P): у доці є заглушкаN, але INTEGRATOR-колонка
    # порожня → h5p_task не зібрав слот. Заповнюємо слот напряму з кешу-«бази» по
    # індексу n. Для звичайних уроків плейсхолдер уже замінено вище → no-op.
    for _item in h5p_cache.values():
        _code = _item.get("html_code", "")
        _n = _item.get("n")
        if not _code or not _n:
            continue
        _ph = f'<p>заглушка{_n}</p>\n<div style="max-width: 720px; padding: 10px; background: white;"></div>'
        if _ph in html_output:
            _repl = f'<div style="max-width: 720px; padding: 10px; background: white;">\n{_code}\n</div>'
            html_output = html_output.replace(_ph, _repl)

    if h5p_task:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as file:
            json.dump(h5p_task, file, ensure_ascii=False, indent=4)

    return html_output

    
# зчитування назви уроку
def get_text_before_table(content, text_before_table):
    for element in content:
        if 'paragraph' in element:
            # Обробка текстових параграфів
            for elem in element['paragraph']['elements']:
                if 'textRun' in elem:
                    text_before_table += elem['textRun']['content']
    return text_before_table

# стоврення назви уроку
def get_name_article(text):
    if CURRENT_SUBJECT == "Українська мова" or CURRENT_SUBJECT == "Українська література":
        name_article = text.split("Урок")[-1].strip()
        name_article = name_article.replace(", тема:", ".").replace("№ ", "№")
        name_article = "Урок " + name_article
        return name_article
    
    elif CURRENT_SUBJECT == "Німецька мова":
        name_article = text.split("Німецька мова.")[-1].strip()
        return name_article
    
    elif CURRENT_SUBJECT == "Німецька мова 510":
        name_article = text.split("Німецька мова.")[-1].strip()
        name_lesson_article = text.split(".")[-1].strip()
        match = re.search(r'\d+', name_article)
        if match:
            Number_article = match.group(0)
        name_article = "Урок " + str(Number_article)+ ". " + name_lesson_article
        return name_article
    
    elif CURRENT_SUBJECT == "Пізнаємо природу":
        name_article = text.split("Пізнаємо природу.")[-1].strip()
        name_article = text.split("Урок")[-1].strip()
        name_article = name_article.replace(". Тема:", ".").replace("№ ", "№")
        name_article = "Урок " + name_article
        return name_article
    
    elif CURRENT_SUBJECT == "Зарубіжна література":
        name_article = text.split("Зарубіжна література. 5 клас.")[-1].strip()
        name_article = text.split("Урок")[-1].strip()
        name_article = text.replace("Тема: ", "")
        return name_article
    
    elif CURRENT_SUBJECT == "Історія України":
        name_article = text.split("Урок")[-1].strip()
        name_article = "Урок " + name_article
        return name_article
    
    
    elif CURRENT_SUBJECT == "Математика":
        name_article = text.split("Урок")[-1].strip()
        name_article = "Урок " + name_article
        
        return name_article
        
        
    
        
        
        

def main():
    logging.info("Початок обробки документа")
    
    


    doc = get_document_content(DOCUMENT_ID)
    content = doc.get('body').get('content', [])
    lists = doc.get('lists', {})

    html_output = ""
    for element in content:
        if 'table' in element:
            html_output += process_table_with_details(element['table'], lists)
            
            delete_lete = [
                "",
                "~~",
                "✔️",
                "▫️",
            ]
            
            for item in delete_lete:
                if item in html_output:
                    if item == "":
                        html_output = html_output.replace(item, "<br>")
                    html_output = html_output.replace(item, "")
                
                        
          


    xml_url_path = XML_URL_JSON
    if xml_url_path.exists():
        with xml_url_path.open("r", encoding="utf-8") as _f:
            try:
                xml_url_data = json.load(_f)
                if xml_url_data.get("code_subject") == code_subject:
                    test_url = xml_url_data["url"]
                    link_html = (
                        f'<a href="{test_url}" '
                        f'style="display: block; color: #3C398C;">'
                        f'Пройди тест до уроку</a>'
                    )
                    html_output = html_output.replace("<strong>Пройди тест до уроку</strong>", link_html)
            except Exception:
                pass

    # Додавання лише обгортки <div> без додаткових тегів
    wrapped_output = f'''
    <p class='img_article'>{BANER_NAME}</p>
<div class="page-set space img-space">
    {html_output}
</div>
'''

    with OUTPUT_HTML.open('w', encoding='utf-8') as f:
        f.write(wrapped_output)
    logging.info("HTML content saved to output.html")
    
    
    
    
    # зчитування назви уроку
    
    text_before_table = ""
    text_before_table = get_text_before_table(content, text_before_table)
    
    name_article = ""
    name_article = get_name_article(text_before_table)
    name_article = re.sub(r'(Урок\s+\d+)(?!\.)(\s)', r'\1.\2', name_article)
    print("")
    print(f"name_article - {name_article}")
    with NAME_ARTICLE_TXT.open("w", encoding="utf-8") as file:
        file.write(name_article.strip())


    with CODE_SUBJECT_TXT.open("w", encoding="utf-8") as file:
        file.write(code_subject)
        
    
    view_xml.generate_html_xml()
    _xml_status_report()


def _xml_status_report():
    from xml.etree import ElementTree as ET
    import os

    xml_path = TEST_OUTPUT_XML

    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    RESET  = "\033[0m"
    BOLD   = "\033[1m"

    print("\n" + "=" * 55)

    if not os.path.exists(xml_path):
        print(f"{RED}{BOLD}  [XML] Файл не знайдено: test_output.xml{RESET}")
        print("=" * 55)
        return

    if os.path.getsize(xml_path) == 0:
        print(f"{RED}{BOLD}  [XML] Файл порожній{RESET}")
        print("=" * 55)
        return

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        questions = root.findall("question")
        n_questions = len(questions)
        n_correct = sum(
            1 for q in questions
            if q.findall("answer[@fraction='100']")
        )
    except Exception as e:
        print(f"{RED}{BOLD}  [XML] Помилка читання: {e}{RESET}")
        print("=" * 55)
        return

    if n_questions == 0:
        color = RED
        status = "ПОРОЖНЬО — питань не знайдено"
    elif n_questions == QUIZ_EXPECTED_QUESTIONS and n_correct == QUIZ_EXPECTED_QUESTIONS:
        color = GREEN
        status = f"OK — {n_questions} питань, {n_correct} правильних відповідей"
    else:
        color = YELLOW
        issues = []
        if n_questions != QUIZ_EXPECTED_QUESTIONS:
            issues.append(f"питань: {n_questions} (очікувалось {QUIZ_EXPECTED_QUESTIONS})")
        if n_correct != n_questions:
            issues.append(f"без правильної відповіді: {n_questions - n_correct}")
        elif n_questions > 0:
            issues.append(f"питань: {n_questions}, правильних: {n_correct}")
        status = " | ".join(issues)

    print(f"{color}{BOLD}  [XML] {status}{RESET}")
    print("=" * 55)


docs_service = None
drive_service = None

def init_services(creds):
    global docs_service, drive_service
    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

def get_modified_time():
    f = drive_service.files().get(
        fileId=DOCUMENT_ID,
        fields="modifiedTime,version"
    ).execute()
    return f["modifiedTime"]  # або f["version"]

def watch_for_changes(interval=5):
    print("🔍 Відстеження змін (Drive modifiedTime)...")
    last = None
    while True:
        cur = get_modified_time()
        if last is None:
            last = cur

        if cur != last:
            print("📄 Є зміни — оновлюю HTML...")
            last = cur
            main()
            print("✅ HTML оновлено.")
        else:
            print(f"⏳ Немає змін. Через {interval}с ще раз.")
        sleep(interval)

if __name__ == '__main__':
    compose_subject_styles(custom_styles, all_styles)
    update_styles_with_color(custom_styles, div_color)

    init_google_service()
    main()

