"""Read a copied Junior RC6 raw-scan ZIP without accessing RC6 user data."""

import hashlib
import io
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from junior.application.evaluation_sample import EvaluationPosting, EvaluationSample

_TEXT_NAME = "target-scan-raw.txt"
_POSTING_DIVIDER = "=" * 80
_MAX_ARCHIVE_BYTES = 750 * 1024 * 1024
_MAX_DESCRIPTION_CHARACTERS = 200_000
_TARGET_PER_CATEGORY = 4
_TARGET_SAMPLE_SIZE = 20
_HEADER_PATTERN = re.compile(r"^([^:]+):\s?(.*)$")


class RawScanImportError(ValueError):
    """The selected archive is not a supported, safe RC6 raw-scan export."""


@dataclass(frozen=True, slots=True)
class _RawPosting:
    company: str
    title: str
    source_url: str
    posting_id: str
    description: str


def import_rc6_evaluation_sample(path: str | Path) -> EvaluationSample:
    archive_path = Path(path)
    buckets: dict[str, list[tuple[str, EvaluationPosting]]] = defaultdict(list)
    eligible = 0
    seen_ids: set[str] = set()
    with zipfile.ZipFile(archive_path) as archive:
        if archive.namelist() != [_TEXT_NAME]:
            raise RawScanImportError(
                "Choose an RC6 raw-scan ZIP downloaded from the Reports page."
            )
        member = archive.getinfo(_TEXT_NAME)
        if member.file_size > _MAX_ARCHIVE_BYTES:
            raise RawScanImportError(
                "The raw-scan export is too large to import safely."
            )
        with archive.open(member) as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8", errors="strict")
            source_build, jobs_in_export = _read_export_header(text)
            for raw in _iter_postings(text):
                posting = _to_evaluation_posting(raw)
                if posting is None or posting.posting_id in seen_ids:
                    continue
                seen_ids.add(posting.posting_id)
                eligible += 1
                rank = hashlib.sha256(posting.posting_id.encode()).hexdigest()
                buckets[posting.sample_category].append((rank, posting))

    selected: list[EvaluationPosting] = []
    selected_ids: set[str] = set()
    for category in _CATEGORY_ORDER:
        candidates = sorted(buckets.get(category, ()))
        for _rank, posting in candidates[:_TARGET_PER_CATEGORY]:
            if posting.posting_id not in selected_ids:
                selected.append(posting)
                selected_ids.add(posting.posting_id)
    if len(selected) < _TARGET_SAMPLE_SIZE:
        remaining = sorted(
            candidate
            for candidates in buckets.values()
            for candidate in candidates
            if candidate[1].posting_id not in selected_ids
        )
        selected.extend(
            posting
            for _rank, posting in remaining[: _TARGET_SAMPLE_SIZE - len(selected)]
        )
    return EvaluationSample(
        source_build=source_build,
        jobs_in_export=jobs_in_export,
        eligible_jobs=eligible,
        postings=tuple(selected),
    )


def _read_export_header(text: TextIO) -> tuple[str, int]:
    first = text.readline().rstrip("\r\n")
    if first != "Junior raw scan export":
        raise RawScanImportError("The selected ZIP is not a Junior raw-scan export.")
    build_line = text.readline().rstrip("\r\n")
    build = _header_value(build_line, "Junior build")
    text.readline()
    text.readline()
    jobs_text = _header_value(text.readline().rstrip("\r\n"), "Jobs collected")
    try:
        jobs = int(jobs_text)
    except ValueError as exc:
        raise RawScanImportError("The export job count is not valid.") from exc
    for line in text:
        if line.rstrip("\r\n") == _POSTING_DIVIDER:
            return build, jobs
    return build, jobs


def _iter_postings(text: TextIO):
    current: list[str] = []
    for line in text:
        clean = line.rstrip("\r\n")
        if clean == _POSTING_DIVIDER:
            if current:
                yield _parse_posting(current)
            current = []
        else:
            current.append(clean)
    if current:
        yield _parse_posting(current)


def _parse_posting(lines: list[str]) -> _RawPosting:
    fields: dict[str, str] = {}
    description_start = None
    for index, line in enumerate(lines):
        if line == "Job description:":
            description_start = index + 1
            break
        match = _HEADER_PATTERN.match(line)
        if match:
            fields[match.group(1)] = match.group(2)
    if description_start is None:
        raise RawScanImportError("A posting in the export has no description marker.")
    required = ("Company", "Title", "Source URL", "Junior job ID")
    if any(not fields.get(name, "").strip() for name in required):
        raise RawScanImportError("A posting in the export is missing identity fields.")
    return _RawPosting(
        company=fields["Company"].strip(),
        title=fields["Title"].strip(),
        source_url=fields["Source URL"].strip(),
        posting_id=fields["Junior job ID"].strip(),
        description="\n".join(lines[description_start:]).strip(),
    )


def _to_evaluation_posting(raw: _RawPosting) -> EvaluationPosting | None:
    description = raw.description
    if (
        description == "Not provided"
        or len(description) < 150
        or len(description) > _MAX_DESCRIPTION_CHARACTERS
    ):
        return None
    category = _sample_category(description)
    return EvaluationPosting(
        posting_id=raw.posting_id,
        company=raw.company,
        title=raw.title,
        description=description,
        source_url=raw.source_url,
        sample_category=category,
    )


def _sample_category(description: str) -> str:
    lowered = description.casefold()
    if any(term in lowered for term in _SECURITY_TERMS):
        return "clearance or work authorization"
    if any(term in lowered for term in _ALTERNATIVE_TERMS):
        return "alternative qualification path"
    if any(term in lowered for term in _PREFERRED_TERMS):
        return "preferred or bonus qualifications"
    if any(term in lowered for term in _QUALIFICATION_HEADINGS):
        return "qualification heading"
    return "general posting"


def _header_value(line: str, expected: str) -> str:
    prefix = f"{expected}:"
    if not line.startswith(prefix):
        raise RawScanImportError(f"The export is missing its {expected} header.")
    return line[len(prefix) :].strip()


_CATEGORY_ORDER = (
    "clearance or work authorization",
    "alternative qualification path",
    "preferred or bonus qualifications",
    "qualification heading",
    "general posting",
)
_SECURITY_TERMS = (
    "security clearance",
    "public trust",
    "authorized to work",
    "work authorization",
    "visa sponsorship",
    "citizenship required",
)
_ALTERNATIVE_TERMS = (
    "bachelor's degree or",
    "bachelors degree or",
    "master's degree or",
    "equivalent experience",
    "degree in lieu of",
)
_PREFERRED_TERMS = (
    "preferred qualifications",
    "bonus points",
    "nice to have",
    "desired qualifications",
)
_QUALIFICATION_HEADINGS = (
    "minimum qualifications",
    "basic qualifications",
    "required qualifications",
    "key qualifications",
    "skills and abilities",
)
