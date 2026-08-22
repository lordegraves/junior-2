"""Local-only text extraction for resume files selected by the user."""

from pathlib import Path
from zipfile import BadZipFile, ZipFile

from PySide6.QtPdf import QPdfDocument


class ResumeImportError(ValueError):
    """The selected file cannot provide readable resume text."""


def import_resume_text(path: str) -> str:
    source = Path(path)
    suffix = source.suffix.casefold()
    try:
        if suffix == ".txt":
            content = source.read_text(encoding="utf-8-sig")
        elif suffix == ".docx":
            content = _read_docx(source)
        elif suffix == ".pdf":
            content = _read_pdf(source)
        else:
            raise ResumeImportError("Choose a PDF, DOCX, or plain-text resume.")
    except (OSError, UnicodeError, BadZipFile) as exc:
        raise ResumeImportError("Junior could not read the selected resume.") from exc
    content = "\n".join(line.rstrip() for line in content.splitlines()).strip()
    if not content:
        raise ResumeImportError(
            "No selectable text was found. An image-only PDF needs OCR first."
        )
    return content


def _read_docx(path: Path) -> str:
    from xml.etree import ElementTree

    with ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(document_xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(
            node.text or "" for node in paragraph.iter(f"{namespace}t")
        ).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _read_pdf(path: Path) -> str:
    document = QPdfDocument()
    if document.load(str(path)) != QPdfDocument.Error.None_:
        raise ResumeImportError("Junior could not open the selected PDF resume.")
    return "\n".join(
        document.getAllText(page).text() for page in range(document.pageCount())
    )
