"""PDF з папки уроку → PNG.

Дизайнер кладе у Drive-папку уроку PDF (напр. прописи), а у статтю має піти
картинка з нього + окреме посилання на сам PDF. Плейсхолдер із розширенням
.pdf крок вставки фото ігнорує (insert_photos.looks_like_image_name
пропускає лише .png/.jpg/.jpeg/.webp/.gif), тому поряд із кожним PDF кладемо
однойменний .png — саме його чекає doc_to_html (див. pdf_image_name).

Викликається з photo_worker() — спільної точки для АІ-пайплайну
(run_pipeline_with_ai.start_photo_download) і звичайного
(insert_photos._ensure_photos_downloaded).
"""

from __future__ import annotations

from pathlib import Path


DEFAULT_DPI = 150


def _page_target(pdf_path: Path, page_index: int) -> Path:
    """Перша сторінка → «назва.png» (саме її шукає doc_to_html),
    наступні → «назва-2.png», «назва-3.png» … щоб нічого не загубилось."""
    if page_index == 0:
        return pdf_path.with_suffix(".png")
    return pdf_path.with_name(f"{pdf_path.stem}-{page_index + 1}.png")


def convert_pdf(pdf_path: Path, dpi: int = DEFAULT_DPI) -> list[Path]:
    """Один PDF → список створених PNG. Ідемпотентно: якщо PNG уже є і не
    старіший за PDF, нічого не робимо."""
    try:
        import fitz  # PyMuPDF
    except ImportError as error:
        # Показуємо саме текст помилки: ImportError буває не лише «немає пакета»,
        # а й «пакет є, але не вантажиться DLL» — раніше обидва випадки виглядали
        # як «не встановлено» і збивали з пантелику.
        print(f"[pdf2png] не можу імпортувати PyMuPDF ({error}) — пропускаю {pdf_path.name}")
        print(f"[pdf2png] якщо пакета справді нема: pip install pymupdf")
        return []

    created: list[Path] = []
    try:
        document = fitz.open(pdf_path)
    except Exception as error:
        print(f"[pdf2png] не можу відкрити {pdf_path.name}: {error}")
        return []

    with document:
        for page_index, page in enumerate(document):
            target = _page_target(pdf_path, page_index)
            if target.exists() and target.stat().st_mtime >= pdf_path.stat().st_mtime:
                continue
            try:
                page.get_pixmap(dpi=dpi).save(target)
            except Exception as error:
                print(f"[pdf2png] помилка на сторінці {page_index + 1} у {pdf_path.name}: {error}")
                continue
            created.append(target)
            print(f"[pdf2png] {pdf_path.name} стор.{page_index + 1} → {target.name}")

        if document.page_count > 1:
            print(
                f"[pdf2png] {pdf_path.name}: сторінок {document.page_count} — у статтю піде "
                f"«{_page_target(pdf_path, 0).name}», решта поряд як -2, -3 …"
            )

    return created


def convert_pdfs_to_images(directory: Path, dpi: int = DEFAULT_DPI) -> list[Path]:
    """Усі PDF у папці уроку (рекурсивно) → PNG. Повертає створені файли."""
    directory = Path(directory)
    if not directory.exists():
        return []

    created: list[Path] = []
    for pdf_path in sorted(directory.rglob("*.pdf")):
        if pdf_path.is_file():
            created.extend(convert_pdf(pdf_path, dpi=dpi))
    return created


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python pdf_to_image.py <папка або .pdf>")
        raise SystemExit(1)

    target = Path(sys.argv[1])
    made = convert_pdf(target) if target.suffix.lower() == ".pdf" else convert_pdfs_to_images(target)
    print(f"[pdf2png] створено файлів: {len(made)}")
