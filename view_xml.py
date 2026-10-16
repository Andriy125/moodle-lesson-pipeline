def generate_html_xml():
    from xml.etree import ElementTree as ET
    from paths import BASE_DIR, TEST_OUTPUT_XML

    # Завантаження XML-файлу
    tree = ET.parse(TEST_OUTPUT_XML)
    root = tree.getroot()

    # Отримуємо заголовок тесту з першого питання
    first_question = root.find("question")
    name_element = first_question.find("name/text") if first_question is not None else None
    quiz_title = name_element.text.strip() if name_element is not None else "Без назви"

    # Початок створення HTML
    html_content = f"""
    <html>
    <head>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            line-height: 1.15;
        }}
        h1 {{
            text-align: center;
            color: #333;
        }}
        .question {{
            margin-bottom: 15px;
        }}
        .question-text {{
            font-size: 16px;
            font-weight: bold;
        }}
        .answer {{
            font-size: 14px;
        }}
        .answer.correct {{
            background-color: #d4edda;
            color: #155724;
            border-color: #c3e6cb;
            font-weight: bold;
        }}
        .answer:hover {{
            background-color: #f1f1f1;
            cursor: pointer;
        }}
    </style>
    </head>
    <body>

    <h1>{quiz_title}</h1>
    """

    # Генерація HTML для кожного питання
    for question in root.findall("question"):
        question_text = question.find("questiontext").find("text").text.strip()

        # Додаємо блок питання
        html_content += f"""
        <div class="question">
        <div class="question-text">{question_text}</div>
        """

        # Додаємо відповіді
        for answer in question.findall("answer"):
            answer_text = answer.find("text").text.strip()
            is_correct = answer.get("fraction") == "100"
            html_content += f"""
            <div class="answer {'correct' if is_correct else ''}">{answer_text}</div>
            """

        html_content += "</div>"

    # Завершення HTML
    html_content += """
    </body>
    </html>
    """

    # Записуємо HTML у файл
    with (BASE_DIR / "quiz_preview.html").open("w", encoding="utf-8") as file:
        file.write(html_content)

    print("HTML-файл створено: quiz_preview.html")
