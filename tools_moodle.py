from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from time import sleep
from typing import List, Dict, Union
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from pathlib import Path
import re

import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import hashlib
import unicodedata
from urllib.parse import urlparse, parse_qs
try:
    import openpyxl
    from openpyxl.styles import Alignment
    from openpyxl.styles import Font
    from openpyxl.styles import PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:
    openpyxl = None
    Alignment = None
    Font = None
    PatternFill = None
    get_column_letter = None
from multiprocessing import Pool
from selenium.webdriver.common.keys import Keys
try:
    import comtypes.client
except ImportError:
    comtypes = None
from paths import CHROMEDRIVER_PATH, GOOGLE_DRIVE_FILE_SERVICE_ACCOUNT, MOODLE_BASE_URL, MOODLE_PASSWORD, MOODLE_USERNAME

service_path = Service(str(CHROMEDRIVER_PATH))
_browser_port = os.environ.get("BROWSER_PORT")
if _browser_port:
    _chrome_opts = webdriver.ChromeOptions()
    _chrome_opts.add_experimental_option("debuggerAddress", f"localhost:{_browser_port}")
    browser = webdriver.Chrome(service=service_path, options=_chrome_opts)
    browser.quit = lambda: None  # не закривати Chrome при завершенні скрипту
else:
    browser = webdriver.Chrome(service=service_path)

def click_element(path):
    for sec in range(300):
        sleep(0.1)
        try:
            element = WebDriverWait(browser, 5).until(EC.element_to_be_clickable((By.XPATH, path)))
            element.click()
            break
        except:
            continue

def click_element_not_xpath(element):
    for sec in range(300):
        sleep(0.1)
        try:
            founded_element = WebDriverWait(browser, 5).until(EC.element_to_be_clickable(element))
            founded_element.click()
            break
        except:
            continue

def click_element_class(class_name):
    for sec in range(300):
        sleep(0.1)
        try:
            founded_element = WebDriverWait(browser, 5).until(EC.element_to_be_clickable((By.CLASS_NAME, class_name)))
            founded_element.click()
            break
        except:
            continue

def click_hiden_element(path):
    button = browser.find_element(by=By.XPATH, value= path)
    sleep(0.1)
    browser.execute_script("$(arguments[0]).click();", button)


def delete_element_html(element_xpath):
    element = browser.find_element(by=By.XPATH, value=element_xpath)

    browser.execute_script("""
    var element = arguments[0];
    element.parentNode.removeChild(element);
    """, element)

def find_num(text):
    num = ''.join(char for char in text if char.isdigit())
    return int(num) if num else -1

def get_clear_name_subject(subject_name):
    separators = [ " (", ","]
    for separator in separators:
        if separator in subject_name:
            subject_name = subject_name.split(separator)[0]
            
            # костиль
            if " (" in separator and "," in subject_name:
                subject_name = subject_name.split(",")[0]

            break
    return subject_name


def _focus_chrome_window():
    """ВИМКНЕНО: кліки переведені на JS (execute_script arguments[0].click()), які
    НЕ залежать від фокуса вікна. SetForegroundWindow на Windows ненадійний (тихо
    фейлиться без foreground-привілею) → давав інтермітентні фейли кліків і крав
    фокус під час роботи. Лишаємо no-op, щоб пайплайн працював у фоні."""
    return
    try:
        import ctypes
        import ctypes.wintypes

        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

        hwnds = []

        @WNDENUMPROC
        def enum_cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                cls = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(hwnd, cls, 64)
                if cls.value == "Chrome_WidgetWin_1":
                    if user32.GetWindowTextLengthW(hwnd) > 0:
                        hwnds.append(hwnd)
            return True

        user32.EnumWindows(enum_cb, 0)

        if hwnds:
            hwnd = hwnds[0]
            if user32.IsIconic(hwnd):         # згорнуто — відновлюємо
                user32.ShowWindow(hwnd, 9)    # SW_RESTORE
            else:
                user32.ShowWindow(hwnd, 5)    # SW_SHOW — активує без зміни розміру
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def go_to_site(url, is_second_monitor=False):
    browser.get(url)
    if is_second_monitor:
        browser.set_window_position(2000, 0)

    try:
        browser.maximize_window()
    except Exception:
        pass

    _focus_chrome_window()

    # Чекаємо поки URL стабілізується (login-редирект або цільова сторінка)
    try:
        WebDriverWait(browser, 5).until(
            lambda d: "login" in d.current_url or d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass

    if "login" not in browser.current_url:
        return  # вже авторизовані

    if not MOODLE_PASSWORD:
        print("Moodle відкрив сторінку логіну. Увійди вручну в Chrome, потім натисни Enter тут.")
        input()
        return

    email = '/html/body/div[2]/div[2]/div/div/section/div/div/div/div/form[1]/div[1]/input'
    WebDriverWait(browser, 15).until(
        EC.presence_of_element_located((By.XPATH, email))
    ).send_keys(MOODLE_USERNAME)

    pas = '/html/body/div[2]/div[2]/div/div/section/div/div/div/div/form[1]/div[2]/div/input'
    browser.find_element(by=By.XPATH, value=pas).send_keys(MOODLE_PASSWORD)

    enter = '/html/body/div[2]/div[2]/div/div/section/div/div/div/div/form[1]/div[3]/button'
    browser.find_element(by=By.XPATH, value=enter).click()


def get_url_subject():
    class_array = []
    try:
        list_sujbect_xpath = "/html/body/div[2]/div[3]/div/div[2]/div/section/div/aside/section/div/div/div[1]/div[2]/div/div/div[1]/div/ul/li"
        browser.find_element(by=By.XPATH, value=list_sujbect_xpath)
    except:
        list_sujbect_xpath = "/html/body/div[4]/div[3]/div/div[2]/div/section/div/aside/section/div/div/div[1]/div[2]/div/div/div[1]/div/ul/li"


    wait_element(list_sujbect_xpath)
    div_elements = browser.find_elements(by=By.XPATH, value = list_sujbect_xpath)
    number_elements = int(len(div_elements))
    for i in range(1, number_elements+1):

        subject_url_xpath = list_sujbect_xpath + f"[{str(i)}]/div/div/a"
        while True:
            try:
                subject_url = browser.find_element(by=By.XPATH, value=subject_url_xpath).get_attribute("href")
                subject_name = browser.find_element(by=By.XPATH, value=subject_url_xpath).text
                dictionary = {
                        "number_class": find_num(subject_name),
                        "subject_name": subject_name,
                        "subject_url": subject_url
                     }
                class_array.append(dictionary)
                break
            except:
                continue
    return class_array

def get_url_courses():
    # /html/body/div[2]/div[3]/div/div[2]/div/section/div/div[2]/div[2]/div/div[1]/div[1]/h3/a
    # /html/body/div[2]/div[3]/div/div[2]/div/section/div/div[2]/div[2]/div/div[7]/div[1]/h3/a
    class_array = []
    list_sujbect_xpath = "/html/body/div[2]/div[3]/div/div[2]/div/section/div/div[2]/div[2]/div/div"
    wait_element(list_sujbect_xpath)
    div_elements = browser.find_elements(by=By.XPATH, value = list_sujbect_xpath)
    category_elements = int(len(div_elements))
    for i in range(1, category_elements+1):

        subject_text_xpath = list_sujbect_xpath + f"[{str(i)}]/div[1]/h3/a"


        # /html/body/div[2]/div[3]/div/div[2]/div/section/div/div[2]/div[2]/div/div[2]/div[2]/div/div[7]/div[1]/div[1]/a
        # /html/body/div[2]/div[3]/div/div[2]/div/section/div/div[2]/div[2]/div/div[8]/div[2]/div/div[11]/div[1]/div[1]/a
        subject_in_categiry_xpath = "/html/body/div[2]/div[3]/div/div[2]/div/section/div/div[2]/div[2]/div/div[8]/div[2]/div/div"

        subject_url_xpath = list_sujbect_xpath + f"[{str(i)}]/div[1]/h3/a"

        while True:
            try:
                subject_url = browser.find_element(by=By.XPATH, value=subject_url_xpath).get_attribute("href")
                subject_name = browser.find_element(by=By.XPATH, value=subject_text_xpath).text
                dictionary = {
                        "number_class": find_num(subject_name),
                        "subject_name": subject_name,
                        "subject_url": subject_url
                     }
                class_array.append(dictionary)
                break
            except:
                continue
    return class_array

def send_subject_for_find(name_subject):
    sleep(1)
    input_find_xpath = "/html/body/div[2]/div[3]/div/div[2]/div/section/div/aside/section/div/div/div[1]/div[1]/div/div[2]/div/div/input"
    try:
        input_text(input_find_xpath, name_subject)
        wait_xp = "/html/body/div[2]/div[3]/div/div[2]/div/section/div/aside/section/div/div/div[1]/div[2]/div/div/div[1]/div/ul/li[1]/div/div[2]/a"

    except:
        input_find_xpath = "/html/body/div[4]/div[3]/div/div[2]/div/section/div/aside/section/div/div/div[1]/div[1]/div/div[2]/div/div/input"

        input_text(input_find_xpath, name_subject)
        wait_xp = "/html/body/div[4]/div[3]/div/div[2]/div/section/div/aside/section/div/div/div[1]/div[2]/div/div/div[1]/div/ul/li[1]/div/div[2]/a"


    wait_element(wait_xp)
    sleep(1)
    


def go_to_subject(class_array, number_class, subject_name = ""):
    url_class = False
    for value_class_array in class_array:
        if number_class == value_class_array["number_class"]:


            if subject_name in value_class_array["subject_name"]:
                url_class = value_class_array["subject_url"]
                browser.get(url_class)


        
    return url_class
    
def enable_edit_mode():
    body_classes = browser.find_element(By.TAG_NAME, "body").get_attribute("class") or ""
    if "editing" in body_classes:
        return  # вже увімкнено
    div_text_xpath = "/html/body/div[2]/nav/div/div[2]/form/div/label"
    click_element(div_text_xpath)

def wait_element(xpath):
    WebDriverWait(browser, 40).until(EC.visibility_of_element_located((By.XPATH, xpath)))
    
def wait_element_class(class_name):
    WebDriverWait(browser, 40).until(EC.visibility_of_element_located((By.CLASS_NAME, class_name)))

def wait_element_id(id):
    WebDriverWait(browser, 40).until(EC.visibility_of_element_located((By.ID, id)))


def wait_load_subject():
    # очікування повної прогрузки сторінки

    for sec in range(300):
        try:
            sleep(0.1)
            # в якості очікувача моніторю чи з'явилась зелена кнопка додати в предметі.
            add_bnt_xpath = "/html/body/div[4]/div[5]/div/div[3]/div/section/div/div/div/ul"
            browser.find_element(by=By.XPATH, value=add_bnt_xpath)
            break
        except:
            continue



def get_info_title(xpath, is_section=False):
    title_text_xpath = xpath + "/div[1]/div[1]/div[2]/h3"
    if is_section: 
        title_text_xpath = xpath + "/div[1]/div/div[2]/h3"
    
    title_text = browser.find_element(By.XPATH, title_text_xpath).text

    type_material = "title"
    name_material = title_text
    material_xpath = title_text_xpath

    absolute_index_material = None
    linked_material = None
    additional_info = None
    subscription_material = None
    local_material_index = None
    section_index = None
    data_id = None
    count_material_section = 0
    

    dictionary = {
        "absolute_index_material": absolute_index_material,       # тут отримання індексу матеріалу
        "section_index": section_index,       # тут отримання індексу секції (розділу)
        "local_material_index": local_material_index,       # тут отримання локального індексу матеріалу у секції (розділу)
        "data_id" : data_id,                    # id матеріалу, потрібно для знаходження місце положення кнопки додати
        "type_material": type_material,         # тут отримання типу матеріалу
        "name_material": name_material,         # тут отримання назви матеріалу
        "linked_material": linked_material,     # тут отримання інформації чи зв'язаний цей матеріал
        "additional_info": additional_info,     # тут отримання додаткової інформації (Чернетка або Неопубліковані зміни)
        "subscription_material": subscription_material, # тут отримання поля підпису матеріалу
        "material_xpath": material_xpath,       # тут отримання XPath матеріалу
        "count_material_section": count_material_section # а ця штука треба щоб знати скільки є матеріалів у розділі (секції)
    }
    return dictionary


def get_info_material(sector_material_xpath, index_material):
    log = False
    if log: print(f"\n")
    if log: print(f"index_material - {index_material}")
  


    subscription_material = "" # ця зміна зберігає підпис до матеріалу
    file_extension = None

    for index_li_elements_ul_material in range(1, index_material+1):


        if index_material == 1:
            material_text_xpath = sector_material_xpath + f"/div[2]/div[2]/div[2]/div/div/span[1]/a[1]/span"
            li_div_xpath = sector_material_xpath

        else:
            material_text_xpath = sector_material_xpath + f"[{ str(index_li_elements_ul_material) }]/div[2]/div[2]/div[2]/div/div/span/a[1]/span"
            li_div_xpath = sector_material_xpath + f"[{ str(index_li_elements_ul_material) }]"

        
        name_material_text = browser.find_element(By.XPATH, material_text_xpath).text
        material_xpath = material_text_xpath
        name_material = name_material_text.split('\n')[0]
        type_material = name_material_text.split('\n')[-1]
        data_id = browser.find_element(By.XPATH, li_div_xpath).get_attribute("data-id")


        # тип файлу
        # /html/body/div[4]/div[5]/div/div[3]/div/section/div/div[1]/div/ul/li[1]/div[2]/ul/li[3]/div[2]/div[2]/div[2]/div/div/div/span[2]/span
        type_file_text = ""
        if "Файл" in type_material:
            type_file_text_xpath = sector_material_xpath + f"[{ str(index_li_elements_ul_material) }]" + "/div[2]/div[2]/div[2]/div/div/span[2]/span"
            material_xpath = type_file_text_xpath
            type_file_text = browser.find_element(By.XPATH, type_file_text_xpath).text
            file_extension = type_file_text

# /html/body/div[4]/div[5]/div/div[3]/div/section/div/div[1]/div/ul/li[1]/div[1]/div[2]/div[1]/h3
    # Словник відповідності між шуканими рядками та типами матеріалу
    material_mapping = {
        'id=longread': 'longread',
        'Завдання': 'task',
        'SCORM пакет': 'scorm',
        'id=doc': 'word',
        'id=pdf': 'pdf',
        'id=link': 'link',
        'id=ppt': 'ppt',
        'Форум' : "Форум",
        'Тест' : "Тест",
        'Файл' : "Файл"
    }

    # Пошук в рядку та встановлення типу матеріалу
    for key, value in material_mapping.items():
        if key in type_material:
            type_material = value
            break
    else:

        type_material = None
        if log: print(f"Не знайшло тип завдання")
        if log: print(f"type_material - {type_material}")


    if "Введіть опис" in subscription_material:
        subscription_material = None

    absolute_index_material = None
    section_index = None
    local_material_index = index_li_elements_ul_material
    dictionary = {
        "absolute_index_material": absolute_index_material,       # тут отримання абсолютного індексу матеріалу
        "section_index": section_index,       # тут отримання індексу секції (розділу)
        "local_material_index": local_material_index,       # тут отримання локального індексу матеріалу у секції (розділу)
        "data_id" : data_id,                    # id матеріалу, потрібно для знаходження місце положення кнопки додати
        "type_material": type_material,         # тут отримання типу матеріалу
        "file_extension": file_extension,         # тут отримання розширення матеріалу
        "name_material": name_material,         # тут отримання назви матеріалу
        # "linked_material": linked_material,     # тут отримання інформації чи зв'язаний цей матеріал
        "subscription_material": subscription_material, # тут отримання поля підпису матеріалу
        "material_xpath": material_xpath,       # тут отримання XPath матеріалу
    }

    return dictionary


def get_list_materials(is_section=False) -> List[Dict[str, Union[int, str]]]:
    """
    Аналіз матеріалу в предметі.
    Функція, яка нічого не приймає, але повертає список словників з наступною інформацією:

    - absolute_index_material: індекс матеріалу, int
    - type_material: тип матеріалу, string
    - name_material: назва матеріалу, string
    - linked_material: посилання на пов'язаний матеріал, bool
    - additional_info: додаткова інформація про матеріал, string
    - subscription_material: підписка на матеріал, string
    - material_xpath: xpath до матеріалу, string
    
    """
    log = False
    # щоб адекватно рахувало кількість елементів я брав xdd526__item xdd526__item_section" там при копіюванні цифри є [1], щоб норм рахувало я викидав оці []
    # Знаходимо всі елементи li в ul за допомогою XPath
    absolute_material_xpath = "/html/body/div[4]/div[5]/div/div[3]/div/section/div/div/div/ul/li"
                          #    /html/body/div[4]/div[5]/div/div[3]/div/section/div/div/div/ul/li[1]/div[1]/div[2]/ul
                             # /html/body/div[4]/div[5]/div/div[3]/div/section/div/div/div/ul/li[1]/div[1]/div[2]/ul/li[1]


    if is_section:
        absolute_material_xpath = "/html/body/div[4]/div[5]/div/div[3]/div/section/div/div/div/div[1]/ul/li"
                                 # /html/body/div[4]/div[5]/div/div[3]/div/section/div/div[1]/div/div[1]/ul/li

    section_elements = browser.find_elements(By.XPATH, absolute_material_xpath)
    section_elements_count = len(section_elements)
    
    material_array = []
    # тут +1 до material_count треба бо range на останьому елементі обрубує якраз
    
    absolute_index_material = 0

    for index_section in range(1, section_elements_count+1):
        absolute_index_material += 1
        section_xpath = absolute_material_xpath + f"[{index_section}]"


        # Підрахунок кількості матеріалу у заголовку
        materials_xpath = section_xpath + "/div[1]/div[2]/ul/li"
        
        materials_list = browser.find_elements(By.XPATH, materials_xpath)
        materials_list_count = len(materials_list)
        if log: print("Кількість матеріалу в розділі:", materials_list_count)


        if is_section:
            section_xpath = absolute_material_xpath

            # а тут дізнаємось номер розділу, якщо сканується розділ, а не вся сторінка
            url = browser.current_url
            # Розбираємо URL
            parsed_url = urlparse(url)

            # Отримуємо параметри з URL
            params = parse_qs(parsed_url.query)

            # Дістаємо значення параметра "section"
            section_value = int(params.get("section", [None])[0])
            
            # а цей кастиль треба щоб не поламати стару логіку  
            index_section =  section_value + 1 


        dictionary = get_info_title(section_xpath, is_section)
        dictionary["absolute_index_material"] = absolute_index_material
        dictionary["section_index"] = index_section - 1
        dictionary["count_material_section"] = materials_list_count
        material_array.append(dictionary)


        if materials_list_count > 0:

            for index_material in range(1, materials_list_count+1):
                absolute_index_material += 1

                dictionary = get_info_material(materials_xpath, index_material)
                dictionary["absolute_index_material"] = absolute_index_material
                dictionary["section_index"] = index_section -1


                material_array.append(dictionary)


    return material_array


def generate_activity_or_resource_url(url, target_activity, material_context_info):
    section_index = material_context_info["section_index"]
    data_id = "0"


    target_url = url + f"&add={target_activity}&section={section_index}&beforemod={data_id}"

    return target_url


def add_scorm(url, backup_value, First_start):
    log = True
    name_material = backup_value["name_material"]
    list_file = backup_value["list_file"]
    
    url = url.replace("view.php","mod.php")


    target_activity = "scorm"
    url_activity = generate_activity_or_resource_url(url, target_activity, backup_value)
    browser.get(url_activity)
    sleep(1)

    name_scrom_input_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input"
    browser.find_element(By.XPATH, name_scrom_input_xpath).send_keys(name_material)

    for file in list_file:
        file_name = file["file_name"]

        if ".zip" not in file_name :
            continue
        # а цей кастиль з file_path треба аби уникнути обмеження вінди на 260 символів, бо повна адреса файлу в такому варіанті перескакує за ці межі
        file_path = "\\\\?\\" + file["file_path"]

        if log: print("Натискаю на кнопку завантажити")
        btn_downoald_file_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[2]/div[2]/div[1]/div[2]/fieldset/div[1]/div[4]/div[1]/div[2]/div/div"
        click_element(btn_downoald_file_xpath)


        for tres in range(300):
            sleep(0.1)

            try:
                file_input = browser.find_element(By.NAME, "repo_upload_file")

                # Передаємо шлях до файлу у вхідний елемент
                file_input.send_keys(file_path)

                break
            except:
                try:
                    file_input = browser.find_element(By.NAME, "repo_upload_file")

                    browser.execute_script("arguments[0].value = arguments[1];", file_input, file_path)
                    break
                except:
                    continue

                continue

        btn_dowload_that_file = browser.find_element(By.CLASS_NAME, "fp-upload-btn")

        click_element_not_xpath(btn_dowload_that_file)


        #                                 # /html/body/div[11]/div[3]/div/div[2]/div/div/div[2]/div/div[2]/div/div/form/div/div[1]/div/input


        #         # Передаємо шлях до файлу у вхідний елемент


    # закриваємо 
    save_and_back_btn_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/div[4]/div[2]/div[1]/div/div[1]/span/input"
    click_element(save_and_back_btn_xpath)


def add_task(url, backup_value, moodle_value, number_class, subject_name):
    log = True
    describe_task_text = backup_value["subscription_material"]
    name_material = backup_value["name_material"]
    list_file = backup_value["list_file"]
    section_index = backup_value["section_index"]

    url = url.replace("view.php","mod.php")

    target_activity = "assign"
    url_activity = generate_activity_or_resource_url(url, target_activity, moodle_value)
    browser.get(url_activity)
    sleep(1)

    name_task_input_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input"
    wait_element(name_task_input_xpath)
    browser.find_element(By.XPATH, name_task_input_xpath).send_keys(name_material)

    # Вставляємо посилання на файл


    # Вказати параметри
    main_folder_id = '1iH8Ov_3SanWgL2jVV_YxJ3NIoSec6w24'  # ID вашої основної папки
    class_name = str(number_class) + ' клас'  # Назва класу
    subject_name = get_clear_name_subject(subject_name)  # Назва предмету
    len_list_file = len(list_file)
    file_path = None

    for file in list_file:
        file_name = file["file_name"]

        if ".txt" in file_name:
            continue

        file_path = file["file_path"]
        
        if len_list_file > 2:
            if ".docx" in file_name: 
                file_path = file["file_path"]
                break
            
            if ".doc" in file_name: 
                file_path = file["file_path"]
                break

            if ".pdf" in file_name: 
                file_path = file["file_path"]
                break


    if log: print(f"file_path - {file_path}")
    # if 
    # Виклик функції
    if file_path and ".doc" in file_name:
        if log: print(f"section_index - {section_index}")

        file_id = organize_and_upload(main_folder_id, class_name, subject_name, section_index, file_path)


        url_file_task_GD = f"https://docs.google.com/document/d/{file_id}/preview"

        text_task_file_ifrime = f'<iframe src="{url_file_task_GD}" width="100%" height="1000"></iframe>'

        # """

        instrument_btn_edidor_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[2]/div[2]/div[1]/div[1]/div[1]/div[1]/div[1]/div[1]/button[5]"
        click_element(instrument_btn_edidor_xpath)

        source_code_div_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[2]/div[2]/div[1]/div[1]/div[2]/div/div/div/div/div[1]/div[2]"
        click_element(source_code_div_xpath)

        text_tiitl_x = "tox-dialog__title"
        tt = browser.find_element(By.CLASS_NAME, text_tiitl_x).text
        if log: print(f"tt - {tt}")


        editor_container = browser.find_element(By.ID, 'id_introeditor_codeMirrorContainer')
        shadow_root = browser.execute_script('return arguments[0].shadowRoot', editor_container)

        CSS_SELECTOR = "div > div > div.cm-scroller > div.cm-content > div"
        editor_container = shadow_root.find_element(By.CSS_SELECTOR, CSS_SELECTOR)

        if log: print(f"Символи пишу крч")

        editor_container.send_keys(text_task_file_ifrime)

        if log: print(f"прожимаю кнопку Зберегти")
                                                # /html/body/div[9]/div/div[2]/div[3]/div[2]/button[2]
        button = browser.find_element(By.XPATH, "//button[@title='Зберегти' and contains(@class, 'tox-button')]")
        # /html/body/div[10]/div/div[2]/div[3]/div[2]/button[2]
        click_element_not_xpath(button)


    if log: print(f"вставляємо опис файлу")

    # вставляємо опис файлу

    describe_task_ifrime_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[4]/div[2]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/iframe"
    iframe_element = browser.find_element(By.XPATH, describe_task_ifrime_xpath)
    browser.switch_to.frame(iframe_element)
    if log: print(f"вхожу у iframe_element")
    

    if describe_task_text:
        body_ifrime_xpath = "/html/body"
        describe_task_text = describe_task_text.split("Інструкція:\n")[-1]

        describe_task_text = describe_task_text.replace('\n', '<br>')
        browser.execute_script("""
        document.querySelector('body').innerHTML = arguments[0];
        """, describe_task_text)

        browser.switch_to.default_content()
        if log: print(f"вийшов з iframe")


    if log: print(f"Завантаження файлу")

    # Завантаження файлу
    for file in list_file:
        file_name = file["file_name"]

        if ".txt" in file_name:
            continue

        # а цей кастиль з file_path треба аби уникнути обмеження вінди на 260 символів, бо повна адреса файлу в такому варіанті перескакує за ці межі
        file_path = "\\\\?\\" + file["file_path"]


        btn_downoald_file_class = "dndupload-arrow"
        click_element_class(btn_downoald_file_class)

        #                          # /html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[5]/div[2]/fieldset/div/div[2]/div[1]/div[1]/div[1]/a
        

        sleep(1)

        # /html/body/div[12]/div[3]/div/div[2]/div/div/div[1]/div[2] # Завантажити файл
        download_file_nav_item_xpath = "/html/body/div[14]/div[3]/div/div[2]/div/div/div[1]/div[4]/a" # Завантажити файл
        click_element(download_file_nav_item_xpath)


        material_input_xpath = "/html/body/div[14]/div[3]/div/div[2]/div/div/div[2]/div/div[2]/div/div/form/div/div[1]/div/input"
        file_input = browser.find_element(By.XPATH, material_input_xpath)

        # Передаємо шлях до файлу у вхідний елемент
        file_input.send_keys(file_path)

        sleep(1)

        btn_dowload_that_file_xpath = "/html/body/div[14]/div[3]/div/div[2]/div/div/div[2]/div/div[2]/div/div/div/button"
        click_element(btn_dowload_that_file_xpath)


    # Поприбирати галочкі
    end_date_task_pass_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[2]/div[2]/div[2]/div[2]/fieldset/div/label"
    click_element(end_date_task_pass_xpath)

    remind_date_task_pass_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[2]/div[2]/div[4]/div[2]/fieldset/div/label"
    click_element(remind_date_task_pass_xpath)

    # виставляємо оцінки
    mark_div_element_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[8]/div[1]/div/a"
    click_element(mark_div_element_xpath)

    max_score_input_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[8]/div[2]/div[1]/div[2]/fieldset/div/div[3]/span/input"
    wait_element(max_score_input_xpath)
    browser.find_element(By.XPATH, max_score_input_xpath).clear()
    input_text(max_score_input_xpath, 12)

    passing_score_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[8]/div[2]/div[4]/div[2]/input"
    input_text(passing_score_xpath, 4)


    # закриваємо 
    save_and_back_btn_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/div[4]/div[2]/div[1]/div/div[1]/span/input"
    click_element(save_and_back_btn_xpath)
    
    
def add_file_kr(url, path_file, file_name_moodle, section_index):
    
    url = url.replace("view.php","mod.php")

    target_activity = "assign"
    target_url = url + f"&add={target_activity}&section={section_index}&beforemod=0"
    
    browser.get(target_url)
    sleep(1)
    
    
    # ввод імені
    name_task_input_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input"
    wait_element(name_task_input_xpath)
    browser.find_element(By.XPATH, name_task_input_xpath).send_keys(file_name_moodle)

    
    for index in range(2):
        btn_downoald_file_class = "fp-btn-add"
        click_element_class(btn_downoald_file_class)

        #                          # /html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[5]/div[2]/fieldset/div/div[2]/div[1]/div[1]/div[1]/a
        

        sleep(1)

        # /html/body/div[12]/div[3]/div/div[2]/div/div/div[1]/div[2] # Завантажити файл
        download_file_nav_item_xpath = "/html/body/div[14]/div[3]/div/div[2]/div/div/div[1]/div[4]/a" # Завантажити файл
        click_element(download_file_nav_item_xpath)


        material_input_xpath = "/html/body/div[14]/div[3]/div/div[2]/div/div/div[2]/div/div[2]/div/div/form/div/div[1]/div/input"
        file_input = browser.find_element(By.XPATH, material_input_xpath)

        # Передаємо шлях до файлу у вхідний елемент
        if index == 1:
            path_file = path_file.replace("docx", "pdf") 
            
        file_input.send_keys(path_file)

        sleep(1)

        btn_dowload_that_file_xpath = "/html/body/div[14]/div[3]/div/div[2]/div/div/div[2]/div/div[2]/div/div/div/button"
        click_element(btn_dowload_that_file_xpath)

    # Поприбирати галочкі
    start_date_task_pass_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[2]/div[2]/div[1]/div[2]/fieldset/div/label"
    click_element(start_date_task_pass_xpath)
    
    end_date_task_pass_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[2]/div[2]/div[2]/div[2]/fieldset/div/label"
    click_element(end_date_task_pass_xpath)

    remind_date_task_pass_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[2]/div[2]/div[4]/div[2]/fieldset/div/label"
    click_element(remind_date_task_pass_xpath)

    # додаємо поле тексту
    text_online_path = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[3]/div[2]/div[1]/div[2]/fieldset/div/label[1]"
    click_element(text_online_path)
    
    
    # виставляємо оцінки
    mark_div_element_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[8]/div[1]/div/a"
    click_element(mark_div_element_xpath)

    max_score_input_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[8]/div[2]/div[1]/div[2]/fieldset/div/div[3]/span/input"
    wait_element(max_score_input_xpath)
    browser.find_element(By.XPATH, max_score_input_xpath).clear()
    input_text(max_score_input_xpath, 12)

    passing_score_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[8]/div[2]/div[4]/div[2]/input"
    input_text(passing_score_xpath, 4)


    # закриваємо 
    save_and_back_btn_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/div[4]/div[2]/div[1]/div/div[1]/span/input"
    click_element(save_and_back_btn_xpath)
    


def check_file_in_subject(path):

    file_list = os.listdir(path)

    # -1 тому, що синхронізую індекс роздліу, секції з мудлом, бо там він починається з 0
    cout_title = -1

    # тут мені треба число файлів між розділами
    local_material_index = 0


    def get_file_name(file_index):
        
        file_name = f"[{ str(file_index) }]"
        for file in file_list:
            if file_name in file:
                return file

    file_count = len(file_list)

    list_material = []
    for file_index in range(1, int(file_count+1)):

        file_name = get_file_name(file_index)
        
        # Кастиль для пропуску індесу з неіснуючими файлами
        #  ці файли з платформи не викачало, розберусь пізніше
        if not file_name:
            continue


        material_path = os.path.join(path, file_name)
        material_list = os.listdir(material_path)

        absolute_index_material = file_index
        subscription_material = None


        if "РОЗДІЛ" in file_name:
            local_material_index = 0

            cout_title += 1
            section_index = cout_title
            type_material = "title"
            name_material = file_name.split("-- РОЗДІЛ -- ")[-1]
        else:
            local_material_index +=1
            name_material = file_name.split("] ")[-1]


        list_file = []
        for index_file, material_item in enumerate(material_list):

            if "Опис завдання.txt" in material_item or "Підпис матеріалу.txt" in material_item:
                file_path = os.path.join(material_path, material_item)
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    subscription_material = content


            if "Підпис матеріалу.txt" in material_item: continue


            if ".zip" in material_item: type_material = "scorm"

            
            # оцей кастиль треба бо у папці з розділом може валятись файл з описом розділу і прога поки ідентифікує розділ як файл, а не розділ
            elif "Розділ.txt" in material_item: type_material = "title"
            
            
            else: type_material = "Файл"
            


            file_path = os.path.join(material_path, material_item)

            dictionary_file = {
                "index" : index_file,
                "file_name" : material_item,
                "file_path" : file_path
                }
                
            list_file.append(dictionary_file)
            

        dictionary = {
        "absolute_index_material": absolute_index_material,       # тут отримання абсолютного індексу матеріалу
        "section_index": section_index,       # тут отримання індексу секції (розділу)
        "local_material_index": local_material_index,       # тут отримання локального індексу матеріалу у секції (розділу)
        "type_material": type_material,         # тут отримання типу матеріалу
        "name_material": name_material,         # тут отримання назви матеріалу
        "subscription_material": subscription_material, # тут отримання поля підпису матеріалу
        "list_file": list_file
        }

        list_material.append(dictionary) 

    return list_material
    

def rename_section(backup_value, moodle_value):


    name_section = backup_value["name_material"]
    material_xpath = moodle_value["material_xpath"]
    # /html/body/div[4]/div[5]/div/div[3]/div/section/div/div/div/ul/li[2]/div[1]/div[1]/div[2]/h3/span/a/span
    section_name_xpath = material_xpath + "/span/a/span"
    click_element(section_name_xpath)

    section_name_input_xpath = material_xpath + "/span/input"
    wait_element(section_name_input_xpath)


    input_section = browser.find_element(By.XPATH, section_name_input_xpath)
    input_section.send_keys(name_section)
    input_section.send_keys(Keys.ENTER)

    sleep(2)


def add_page(url, backup_value, moodle_value):
    log = False

    name_page = backup_value["name_material"]
    describe_page_text = backup_value["subscription_material"]
    list_file = backup_value["list_file"]


    url = url.replace("view.php","mod.php")

    target_activity = "page"
    url_activity = generate_activity_or_resource_url(url, target_activity, moodle_value)
    browser.get(url_activity)
    sleep(1)

    # Вводимо ім'я сторінки
    name_page_input_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input"
    browser.find_element(By.XPATH, name_page_input_xpath).send_keys(name_page)

    if log: print(f"вставляємо опис файлу")

    # вставляємо зміст файлу

    describe_task_ifrime_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[2]/div[2]/div/div[2]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/iframe"
    iframe_element = browser.find_element(By.XPATH, describe_task_ifrime_xpath)
    browser.switch_to.frame(iframe_element)
    if log: print(f"вхожу у iframe_element")
    

    if describe_page_text:
        body_ifrime_xpath = "/html/body"
        describe_page_text = describe_page_text.split("Інструкція:\n")[-1]

        describe_page_text = describe_page_text.replace('\n', '<br>')
        browser.execute_script("""
        document.querySelector('body').innerHTML = arguments[0];
        """, describe_page_text)

        browser.switch_to.default_content()
        if log: print(f"вийшов з iframe")


    if log: print(f"Завантаження файлу")

    sleep(1)

    # # Завантаження файлу


        


    #     # /html/body/div[12]/div[3]/div/div[2]/div/div/div[1]/div[2] # Завантажити файл


    #                         # /html/body/div[14]/div[3]/div/div[2]/div/div/div[2]/div/div[2]/div/div/form/div/div[1]/div/input

    #     # Передаємо шлях до файлу у вхідний елемент


    save_and_back_btn_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/div[4]/div[2]/div[1]/div/div[1]/span/input"
    click_element(save_and_back_btn_xpath)


def add_file(url, backup_value, moodle_value):
    log = False

    name_file = backup_value["name_material"]
    describe_page_text = backup_value["subscription_material"]
    list_file = backup_value["list_file"]
    
    url = url.replace("view.php","mod.php")


    target_activity = "resource"
    url_activity = generate_activity_or_resource_url(url, target_activity, moodle_value)
    browser.get(url_activity)
    sleep(1)

    # Вводимо ім'я сторінки
    name_file_input_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input"
    browser.find_element(By.XPATH, name_file_input_xpath).send_keys(name_file)

    if log: print(f"вставляємо опис файлу")

    # вставляємо опис файлу

    describe_task_ifrime_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[2]/div[2]/div/div[2]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/iframe"
    iframe_element = browser.find_element(By.XPATH, describe_task_ifrime_xpath)
    browser.switch_to.frame(iframe_element)
    if log: print(f"вхожу у iframe_element")
    

    body_ifrime_xpath = "/html/body"
    browser.find_element(By.XPATH, body_ifrime_xpath).send_keys(describe_page_text)

    browser.switch_to.default_content()
    if log: print(f"вийшов з iframe")

    sleep(1)

    # Завантаження файлу
    for file in list_file:
        file_name = file["file_name"]
        if ".txt" in file_name:
            continue

        file_path = file["file_path"]
        
        btn_downoald_file_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[4]/div[2]/fieldset/div/div[2]/div[1]/div[1]/div[1]/a"
                                #    /html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[4]/div[2]/fieldset/div/div[2]/div[1]/div[1]/div[1]
        click_element(btn_downoald_file_xpath)

        sleep(1)

        # /html/body/div[12]/div[3]/div/div[2]/div/div/div[1]/div[2] # Завантажити файл
        download_file_nav_item_xpath = "/html/body/div[11]/div[3]/div/div[2]/div/div/div[1]/div[4]/a" # Завантажити файл
        click_element(download_file_nav_item_xpath)


        material_input_xpath = "/html/body/div[11]/div[3]/div/div[2]/div/div/div[2]/div/div[2]/div/div/form/div/div[1]/div/input"
                            # /html/body/div[14]/div[3]/div/div[2]/div/div/div[2]/div/div[2]/div/div/form/div/div[1]/div/input
        file_input = browser.find_element(By.XPATH, material_input_xpath)

        # Передаємо шлях до файлу у вхідний елемент
        file_input.send_keys(file_path)

        sleep(1)

        btn_dowload_that_file_xpath = "/html/body/div[11]/div[3]/div/div[2]/div/div/div[2]/div/div[2]/div/div/div/button"
        click_element(btn_dowload_that_file_xpath)


    save_and_back_btn_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/div[4]/div[2]/div[1]/div/div[1]/span/input"
    click_element(save_and_back_btn_xpath)


def close_existing_word_sessions(file_path):
    """
    Закриває попередню сесію Word, якщо вказаний файл відкритий.
    """
    try:
        # Підключення до вже запущеного екземпляра Word (якщо є)
        word = comtypes.client.GetActiveObject("Word.Application")
        for doc in word.Documents:
            # Перевірка, чи відкритий файл
            if doc.FullName == str(file_path):
                print(f"Закриваємо попередню сесію для файлу: {file_path}")
                doc.Close(SaveChanges=False)
        word.Quit()
    except Exception as e:
        # Якщо Word не запущено або файл не відкритий, ігноруємо
        print(f"Не вдалося знайти відкриті сесії Word для {file_path}. Помилка: {e}")

def word_to_pdf(input_file):
    try:
        # Перетворення шляху в об'єкт Path
        input_path = Path(input_file)
        # Генерація вихідного шляху з розширенням .pdf
        output_file = input_path.with_suffix('.pdf')
        
        # Закриття попередніх сесій, якщо файл відкритий
        close_existing_word_sessions(input_path)

        # Створення нового об'єкта Word
        word = comtypes.client.CreateObject('Word.Application')
        word.Visible = False

        # Відкриття документа
        doc = word.Documents.Open(input_file, ReadOnly=False)

        # Експорт у PDF
        doc.SaveAs(str(output_file), FileFormat=17)  # 17 - формат PDF
        doc.Close()
        word.Quit()

        print(f"Файл успішно конвертовано у PDF: {output_file}")
        return str(output_file)
    except Exception as e:
        print(f"Помилка: {e}")


def add_file_KTP(url, backup_value, moodle_value):

    log = False
    list_file = backup_value["list_file"]

    for file in list_file:

        file_name = file["file_name"]
        if ".txt" in file_name:
            continue

        file_path = file["file_path"]    
        if ".pdf" not in file_path:
            file_path = word_to_pdf(file_path)
        
        file_name_without_extension = os.path.splitext(os.path.basename(file_path))[0]
        name_file = file_name_without_extension
    
        
        url = url.replace("view.php","mod.php")


        target_activity = "resource"
        url_activity = generate_activity_or_resource_url(url, target_activity, moodle_value)
        browser.get(url_activity)
        sleep(1)

        # Вводимо ім'я сторінки
        name_file_input_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input"
        browser.find_element(By.XPATH, name_file_input_xpath).send_keys(name_file)

        if log: print(f"вставляємо опис файлу")


        # Завантаження файлу
        
        btn_downoald_file_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[4]/div[2]/fieldset/div/div[2]/div[1]/div[1]/div[1]/a"
                                #    /html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[4]/div[2]/fieldset/div/div[2]/div[1]/div[1]/div[1]
        click_element(btn_downoald_file_xpath)

        sleep(1)
 
        input_atribute_name = "repo_upload_file"
        file_input = browser.find_element(By.NAME, input_atribute_name)

        # Передаємо шлях до файлу у вхідний елемент
        file_input.send_keys(file_path)

        sleep(1)

        btn_dowload_that_file_class = "fp-upload-btn"
        click_element_class(btn_dowload_that_file_class)

        # ----------------------------------
                # виставляємо вигляд у іншій сторінці
        Viev_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[2]/div[1]/div"
        click_element(Viev_xpath)

        select_viev_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[2]/div[2]/div[1]/div[2]/select"
        wait_element(select_viev_xpath)
        
        select_element = browser.find_element(By.XPATH, select_viev_xpath)
        select = Select(select_element)
        select.select_by_value("5")


        save_and_back_btn_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/div[4]/div[2]/div[1]/div/div[1]/span/input"
        click_element(save_and_back_btn_xpath)


def add_subject_book(url, backup_value, moodle_value):

    log = False
    list_file = backup_value["list_file"]

    if len(list_file) > 2:
        if ".txt" in list_file and len(list_file) > 2:
            input("а нук стоять якого фіга")


    for file in list_file:

        file_name = file["file_name"]
        if ".txt" in file_name:
            continue
        
        print(f"file_name - {file_name}")

        file_path = file["file_path"]
        name_file = "Підручник"
        
        if len(list_file) > 2:
            file_name_without_extension = os.path.splitext(os.path.basename(file_path))[0]
            name_file = "Підручник: " + file_name_without_extension

        describe_page_text = backup_value["subscription_material"]
        
        url = url.replace("view.php","mod.php")


        target_activity = "resource"
        url_activity = generate_activity_or_resource_url(url, target_activity, moodle_value)
        browser.get(url_activity)
        sleep(1)

        # Вводимо ім'я сторінки
        name_file_input_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input"
        browser.find_element(By.XPATH, name_file_input_xpath).send_keys(name_file)

        if log: print(f"вставляємо опис файлу")

        # вставляємо опис файлу

        describe_task_ifrime_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[2]/div[2]/div[1]/div[1]/div[1]/div[1]/div[2]/div[1]/iframe"
        iframe_element = browser.find_element(By.XPATH, describe_task_ifrime_xpath)
        browser.switch_to.frame(iframe_element)
        if log: print(f"вхожу у iframe_element")
        

        body_ifrime_xpath = "/html/body"
        browser.find_element(By.XPATH, body_ifrime_xpath).send_keys(describe_page_text)

        browser.switch_to.default_content()
        if log: print(f"вийшов з iframe")

        sleep(1)

        # Завантаження файлу
        


        
        btn_downoald_file_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[4]/div[2]/fieldset/div/div[2]/div[1]/div[1]/div[1]/a"
                                #    /html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[4]/div[2]/fieldset/div/div[2]/div[1]/div[1]/div[1]
        click_element(btn_downoald_file_xpath)

        sleep(1)


        input_atribute_name = "repo_upload_file"
        file_input = browser.find_element(By.NAME, input_atribute_name)

        # Передаємо шлях до файлу у вхідний елемент
        file_input.send_keys(file_path)

        sleep(1)

        btn_dowload_that_file_class = "fp-upload-btn"
        click_element_class(btn_dowload_that_file_class)


        # ----------------------------------

        # виставляємо вигляд у іншій сторінці
        Viev_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[2]/div[1]/div"
        click_element(Viev_xpath)

        select_viev_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/fieldset[2]/div[2]/div[1]/div[2]/select"
        wait_element(select_viev_xpath)
        
        select_element = browser.find_element(By.XPATH, select_viev_xpath)
        select = Select(select_element)
        select.select_by_value("5")


        save_and_back_btn_xpath = "/html/body/div[5]/div[5]/div/div[3]/div/section/div/form/div[4]/div[2]/div[1]/div/div[1]/span/input"
        click_element(save_and_back_btn_xpath)



# Шлях до файлу облікових даних
KEY_FILE = str(GOOGLE_DRIVE_FILE_SERVICE_ACCOUNT)

# Список доступів
scope = ['https://www.googleapis.com/auth/drive']

# Аутентифікація з використанням сервісного акаунта
credentials = service_account.Credentials.from_service_account_file(KEY_FILE, scopes=scope)
service = build('drive', 'v3', credentials=credentials)

# Функція для обчислення MD5-хешу локального файлу
def calculate_file_md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

# Функція для нормалізації Unicode тексту
def normalize_unicode(text):
    # Нормалізація тексту до форми NFC
    return unicodedata.normalize('NFC', text).strip().lower()

# Функція для пошуку файлу за назвою і перевірки його хешу
def find_matching_file(file_path, parent_id):
    file_name = file_path.split('\\')[-1]
    local_file_md5 = calculate_file_md5(file_path)
    print("MD5 хеш локального файлу:", local_file_md5)

    # Отримання списку всіх файлів у папці
    results = service.files().list(
        q=f"'{parent_id}' in parents and trashed=false",
        spaces='drive',
        fields='files(id, name, md5Checksum)'
    ).execute()
    files = results.get('files', [])

    # Посилання на папку
    folder_link = f"https://drive.google.com/drive/folders/{parent_id}"

    # Перевірка на відповідність імені серед знайдених файлів
    for file in files:
        normalized_file_name = normalize_unicode(file['name'])
        normalized_local_file_name = normalize_unicode(file_name)
        
        print(f"")
        print(f"file_name (локальний) - {normalized_local_file_name}")
        print(f"file['name'] (Google Диск) - {normalized_file_name}")
        print(f"file['name'] == file_name - {normalized_file_name == normalized_local_file_name}")

        if normalized_file_name == normalized_local_file_name:
            if 'md5Checksum' in file and file['md5Checksum'] == local_file_md5:
                print("Знайдено файл з такою ж назвою. MD5 хеш на Google Диску:", file.get('md5Checksum', 'Немає хешу'))
                print("Файл з таким же вмістом уже існує. ID файлу:", file['id'])
                return file['id']  # Повертає ID, якщо знайдено відповідність за назвою та хешем

    # Перевірка на відповідність хешу незалежно від назви файлу
    for file in files:
        if 'md5Checksum' in file and file['md5Checksum'] == local_file_md5:
            print(f"Перевірка файлу '{file['name']}' з MD5 хешем на Google Диску:", file.get('md5Checksum', 'Немає хешу'))
            print("Файл з таким же вмістом (MD5) уже існує, незалежно від назви. ID файлу:", file['id'])
            
            file_link = f"https://drive.google.com/file/d/{file['id']}/view?usp=sharing"
            print("Посилання на файл:", file_link)
            print("Посилання на папку:", folder_link)

            print(f"")            
            print("Посилання на файл у вінді:", file_path)
            print(f"")

            print("А нук мітнись на гугл диск і перевір що за нафіг")
            print("У тому випадку якщо все ок то просто жми Enter")
            input("")
            return file['id']  # Повертає ID, якщо знайдено відповідність за хешем

    return None  # Повертає None, якщо немає збігів

# Функція для завантаження файлу
def upload_file(file_path, parent_id, file_name=None):
    if not file_name:
        file_name = file_path.split('\\')[-1]  # Використовується ім'я файлу з шляху, якщо не задано інше

    # Завантаження файлу
    file_metadata = {
        'name': file_name,
        'parents': [parent_id]
    }
    media = MediaFileUpload(file_path, resumable=True)
    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()

    # Надаємо загальний доступ на редагування
    permission = {
        'type': 'anyone',
        'role': 'writer'
    }
    service.permissions().create(
        fileId=uploaded_file['id'],
        body=permission
    ).execute()

    file_link = uploaded_file['webViewLink']
    return uploaded_file['id'], file_link  # Повертається ID файлу і повне посилання

# Основна логіка для організації та завантаження файлу
def organize_and_upload(main_folder_id, class_name, subject_name, section_index, file_path):
    # Знайти папку класу
    class_folders = list_subfolders(main_folder_id)
    class_folder = next((folder for folder in class_folders if folder['name'] == class_name), None)
    if not class_folder:
        class_folder_id = create_folder(class_name, main_folder_id)
    else:
        class_folder_id = class_folder['id']

    # Знайти папку предмету
    subject_folders = list_subfolders(class_folder_id)
    subject_folder = next((folder for folder in subject_folders if folder['name'] == subject_name), None)
    if not subject_folder:
        subject_folder_id = create_folder(subject_name, class_folder_id)
    else:
        subject_folder_id = subject_folder['id']

    # Знайти або створити папку теми
    theme_folders = list_subfolders(subject_folder_id)
    if len(theme_folders) < 6:
        theme_folder_name = f"Тема {len(theme_folders) + 1}"
    else:
        theme_folder_name = f"Тема {section_index}"

    theme_folder = next((folder for folder in theme_folders if folder['name'] == theme_folder_name), None)
    if not theme_folder:
        theme_folder_id = create_folder(theme_folder_name, subject_folder_id)
    else:
        theme_folder_id = theme_folder['id']

    # Перевірка, чи існує файл з тим самим вмістом
    existing_file_id = find_matching_file(file_path, theme_folder_id)
    if existing_file_id:
        return existing_file_id

    # Завантаження файлу у папку теми, якщо його ще немає
    id_file, file_link = upload_file(file_path, theme_folder_id)
    print("Файл завантажено. Посилання на файл:", file_link)

    return id_file  # Повертається лише ID файлу

# Додаткові допоміжні функції
def list_subfolders(parent_id):
    results = service.files().list(
        q=f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        spaces='drive',
        fields='files(id, name)',
        orderBy='name'
    ).execute()
    return results.get('files', [])

def create_folder(name, parent_id):
    folder_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    folder = service.files().create(
        body=folder_metadata,
        fields='id'
    ).execute()
    return folder['id']



def input_text(xpath, text):
    browser.find_element(By.XPATH, xpath).send_keys(text)

def get_img_corse(number_class, name_subject):
    file_path = r"D:\бекапи\ноут 18.01.2025\Завантаження\Обкладинки"

    print(f"name_subject - {name_subject}")
    clear_name_subject = get_clear_name_subject(name_subject)
    clear_name_subject = clear_name_subject.lower()
    
    clear_name_subject_split = clear_name_subject.split(" ")
    if len(clear_name_subject_split) == 3:
        clear_name_subject = clear_name_subject_split[0]
    
    # if "" in clear_name_subject
    print(f"clear_name_subject - {clear_name_subject}")


     # Шлях до файлу, який потрібно завантажити
    school_degree = ""
    if number_class < 5:
        school_degree = "початкова"
    elif number_class > 9:
        school_degree = "старша"
    else:
        school_degree = "середня"

    if "важлива інформація" in clear_name_subject:
        school_degree = "для всіх"
        clear_name_subject = "важлива інформація"


    file_path_cover_img = ""
    file_path_thumbnail_img = ""
    for files in os.listdir(file_path):
        full_file_path = os.path.join(file_path, files)
        if school_degree in files:
            sub_name = files.split('_')[1]
            if " " in clear_name_subject:
                clear_name_subject_split = clear_name_subject.split(" ")
                
                    
                if clear_name_subject_split[0] in files and clear_name_subject_split[1] in files:
                    
                    if "1920" in files:
                        file_path_cover_img = full_file_path
                    elif "640" in files:
                        file_path_thumbnail_img = full_file_path

            elif clear_name_subject in files:
                if "1920" in files:
                        file_path_cover_img = full_file_path
                elif "640" in files:
                    file_path_thumbnail_img = full_file_path

    return file_path_thumbnail_img, file_path_cover_img

def create_subject(name_subject_text, number_class, section_count):
    log = True
    url_create_subject = f"{MOODLE_BASE_URL}/course/edit.php?category=0"
    browser.get(url_create_subject)

    first_div = "3"
    second_div = "3"
    # Повна назва курсу
    name_subject_input_xpath = f"/html/body/div[{first_div}]/div[{second_div}]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input"
    # /html/body/div[3]/div[3]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[1]/div[2]/input
    wait_element(name_subject_input_xpath)
    clear_name_subject_text = name_subject_text.replace(", DS", "")
    input_text(name_subject_input_xpath, clear_name_subject_text)

    # Коротка назва курсу
    short_name_subject_input_xpath = f"/html/body/div[{first_div}]/div[{second_div}]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[2]/div[2]/input"
    clear_name_subject_text = get_clear_name_subject(name_subject_text)
    short_name = get_short_name(clear_name_subject_text)
    if "Мистецтво" in clear_name_subject_text:
        short_name = "Мс"

    if "Географія" in clear_name_subject_text:
        short_name = "Гео"

    short_name_subject = short_name + f"{str(number_class)}"
    input_text(short_name_subject_input_xpath, short_name_subject)

    # Категорія курсу
    category_course_text = f"{ str(number_class) } клас"
    category_course_input_xpath = f"/html/body/div[{first_div}]/div[{second_div}]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[3]/div[2]/div[3]/input"
    input_text(category_course_input_xpath, category_course_text)
    input_text(category_course_input_xpath, Keys.ENTER)

    # вимикаємо "Дата завершення курсу" 
    course_completion_date_xpath = f"/html/body/div[{first_div}]/div[{second_div}]/div/div[3]/div/section/div/form/fieldset[1]/div[2]/div[7]/div[2]/fieldset/div/label"
    click_element(course_completion_date_xpath)

    # Грузимо картінку
    img_course_path, baner_course_path = get_img_corse(number_class, name_subject_text)

    btn_downoald_file_xpath = f"/html/body/div[{first_div}]/div[{second_div}]/div/div[3]/div/section/div/form/fieldset[2]/div[2]/div[2]/div[2]/fieldset/div[1]/div[2]/div[1]/div[1]/div[1]"
    click_element(btn_downoald_file_xpath)

    sleep(1)

    # /html/body/div[12]/div[3]/div/div[2]/div/div/div[1]/div[2] # Завантажити файл

    file_input = browser.find_element(By.NAME, "repo_upload_file")

    # Передаємо шлях до файлу у вхідний елемент
    file_input.send_keys(img_course_path)

    sleep(1)

    btn_dowload_that_file = browser.find_element(By.CLASS_NAME, "fp-upload-btn")

    click_element_not_xpath(btn_dowload_that_file)


    # налаштування формату курсу
    # +1 так як відкрили вікно з завантаженням зоображення
    if log: print("Нажимаю формат курсу")
    first_div = "4"
    format_course_div_xpath = f"/html/body/div[{first_div}]/div[{second_div}]/div/div[3]/div/section/div/form/fieldset[3]/div[1]/div"
    click_element(format_course_div_xpath)

    if log: print("нажимаю на список з формату")

    format_xpath = f"/html/body/div[{first_div}]/div[{second_div}]/div/div[3]/div/section/div/form/fieldset[3]/div[2]/div[1]/div[2]/div[1]/button"
    wait_element(format_xpath)
    click_element(format_xpath)

    if log: print("змінюю на формат плитками")
    option_plate_xpath = f"/html/body/div[{first_div}]/div[{second_div}]/div/div[3]/div/section/div/form/fieldset[3]/div[2]/div[1]/div[2]/div[1]/div/div/div/div[6]/div[2]"
    wait_element(option_plate_xpath)
    click_element(option_plate_xpath)

    first_div = "3"

    section_number_xpath = f"/html/body/div[{first_div}]/div[{second_div}]/div/div[3]/div/section/div/form/fieldset[3]/div[2]/div[3]/div[2]/select"
    wait_element(section_number_xpath)

    select_element = browser.find_element(By.XPATH, section_number_xpath)
    select = Select(select_element)
    select.select_by_value(str(section_count-1))


    progress_every_plate_xpath = f"/html/body/div[{first_div}]/div[{second_div}]/div/div[3]/div/section/div/form/fieldset[3]/div[2]/div[8]/div[2]/select"
    select_element = browser.find_element(By.XPATH, progress_every_plate_xpath)
    select = Select(select_element)
    select.select_by_value("2")
# /html/body/div[9]/div[3]/div/div[2]/div/div/div[2]/div/div[2]/div/div/form/div/div[1]/div/input
    save_course_btn_xpath = f"/html/body/div[{first_div}]/div[{second_div}]/div/div[3]/div/section/div/form/div[3]/div[2]/div[1]/div/div[1]/span/input"
    click_element(save_course_btn_xpath)


def get_short_name(subject):
    # Створюємо коротку назву з перших літер кожного слова
    return ''.join(word[0].upper() for word in subject.split())


def get_count_elements(xpath, tag_name):
    div_element = browser.find_element(By.XPATH, xpath)
    elements_details = div_element.find_elements(By.TAG_NAME, tag_name)
    
    return len(elements_details)


