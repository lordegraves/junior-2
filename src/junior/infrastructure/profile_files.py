"""Manage user-selected résumé files inside Junior's private data directory."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from junior.infrastructure.resume_file_importer import import_resume_text


@dataclass(frozen=True, slots=True)
class ManagedResume:
    source_path: str
    normalized_text_path: str
    character_count: int


def import_managed_resume(
    source_path: str | Path, data_directory: str | Path
) -> ManagedResume:
    source = Path(source_path).expanduser().resolve()
    content = import_resume_text(str(source))
    resume_directory = Path(data_directory).expanduser().resolve() / "resumes"
    resume_directory.mkdir(parents=True, exist_ok=True)
    destination = resume_directory / f"active-resume{source.suffix.casefold()}"
    normalized = resume_directory / "active-resume.normalized.txt"
    temporary = resume_directory / f".{uuid4().hex}{source.suffix.casefold()}"
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
        normalized.write_text(content, encoding="utf-8")
    finally:
        temporary.unlink(missing_ok=True)
    return ManagedResume(str(destination), str(normalized), len(content))
