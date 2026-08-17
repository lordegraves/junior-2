"""Source documents and traceable passages used as interpretation evidence."""

from dataclasses import dataclass
from enum import StrEnum


class DocumentKind(StrEnum):
    JOB_POSTING = "job_posting"
    RESUME = "resume"
    CAREERS_PAGE = "careers_page"


@dataclass(frozen=True, slots=True)
class SourceDocument:
    document_id: str
    kind: DocumentKind
    content: str
    source_uri: str | None = None
    version: str = "1"

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id is required")
        if not self.content.strip():
            raise ValueError("document content is required")
        if not self.version.strip():
            raise ValueError("document version is required")


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    document_id: str
    quote: str
    start: int
    end: int
    document_version: str = "1"

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("evidence offsets must identify a non-empty passage")
        if not self.document_version.strip():
            raise ValueError("evidence document_version is required")
