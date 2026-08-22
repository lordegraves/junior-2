from zipfile import ZipFile

import pytest

from junior.infrastructure.resume_file_importer import (
    ResumeImportError,
    import_resume_text,
)


def test_imports_plain_text_resume(tmp_path) -> None:
    path = tmp_path / "resume.txt"
    path.write_text("Python\nFive years of experience", encoding="utf-8")

    assert import_resume_text(str(path)) == "Python\nFive years of experience"


def test_imports_docx_paragraph_text(tmp_path) -> None:
    path = tmp_path / "resume.docx"
    xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>Python</w:t></w:r></w:p>
  <w:p><w:r><w:t>Five years of experience</w:t></w:r></w:p></w:body>
</w:document>"""
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)

    assert import_resume_text(str(path)) == "Python\nFive years of experience"


def test_rejects_resume_without_selectable_text(tmp_path) -> None:
    path = tmp_path / "resume.txt"
    path.write_text("   ", encoding="utf-8")

    with pytest.raises(ResumeImportError, match="No selectable text"):
        import_resume_text(str(path))
