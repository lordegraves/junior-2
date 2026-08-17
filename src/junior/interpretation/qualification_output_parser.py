"""Strictly parse model-produced qualification JSON into domain records."""

import math
from typing import Any

from junior.domain.document_interpretations import (
    JobQualificationInterpretation,
    ResumeQualificationInterpretation,
)
from junior.domain.documents import DocumentKind, EvidenceReference, SourceDocument
from junior.domain.facts import FactState, JsonValue
from junior.domain.qualifications import (
    QualificationCategory,
    QualificationGroup,
    QualificationItem,
    QualificationPath,
    RequirementPriority,
)

QUALIFICATION_SCHEMA_VERSION = "1"


class QualificationOutputError(ValueError):
    """The model response does not match Junior's required qualification format."""


def parse_job_qualification_output(
    document: SourceDocument,
    payload: Any,
) -> JobQualificationInterpretation:
    if document.kind is not DocumentKind.JOB_POSTING:
        raise QualificationOutputError("job output requires a job-posting document")
    root = _object_with_exact_keys(
        payload,
        required={
            "schema_version",
            "interpreter_version",
            "section_state",
            "groups",
        },
        context="job qualification output",
    )
    _require_schema_version(root["schema_version"])
    state = _enum_value(FactState, root["section_state"], "section_state")
    try:
        groups_raw = _list(root["groups"], "groups")
        groups = tuple(_parse_group(document, item) for item in groups_raw)
        return JobQualificationInterpretation(
            document.document_id,
            QUALIFICATION_SCHEMA_VERSION,
            _text(root["interpreter_version"], "interpreter_version"),
            state,
            groups,
        )
    except ValueError as exc:
        raise QualificationOutputError(str(exc)) from exc


def parse_resume_qualification_output(
    document: SourceDocument,
    payload: Any,
) -> ResumeQualificationInterpretation:
    if document.kind is not DocumentKind.RESUME:
        raise QualificationOutputError("resume output requires a resume document")
    root = _object_with_exact_keys(
        payload,
        required={"schema_version", "interpreter_version", "qualifications"},
        context="resume qualification output",
    )
    _require_schema_version(root["schema_version"])
    try:
        qualifications = tuple(
            _parse_item(document, item)
            for item in _list(root["qualifications"], "qualifications")
        )
        return ResumeQualificationInterpretation(
            document.document_id,
            QUALIFICATION_SCHEMA_VERSION,
            _text(root["interpreter_version"], "interpreter_version"),
            qualifications,
        )
    except ValueError as exc:
        if isinstance(exc, QualificationOutputError):
            raise
        raise QualificationOutputError(str(exc)) from exc


def _parse_group(
    document: SourceDocument,
    raw: Any,
) -> QualificationGroup:
    item = _object_with_exact_keys(
        raw,
        required={"group_id", "priority", "paths"},
        context="qualification group",
    )
    return QualificationGroup(
        group_id=_text(item["group_id"], "group_id"),
        priority=_enum_value(RequirementPriority, item["priority"], "priority"),
        paths=tuple(
            _parse_path(document, path)
            for path in _list(item["paths"], "paths")
        ),
    )


def _parse_path(document: SourceDocument, raw: Any) -> QualificationPath:
    item = _object_with_exact_keys(
        raw,
        required={"path_id", "requirements"},
        context="qualification path",
    )
    return QualificationPath(
        path_id=_text(item["path_id"], "path_id"),
        requirements=tuple(
            _parse_item(document, requirement)
            for requirement in _list(item["requirements"], "requirements")
        ),
    )


def _parse_item(document: SourceDocument, raw: Any) -> QualificationItem:
    item = _object_with_exact_keys(
        raw,
        required={
            "item_id",
            "category",
            "statement",
            "normalized_value",
            "state",
            "evidence",
            "confidence",
        },
        context="qualification item",
    )
    confidence = item["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise QualificationOutputError("confidence must be a number")
    normalized_value = _json_value(item["normalized_value"], "normalized_value")
    try:
        return QualificationItem(
            item_id=_text(item["item_id"], "item_id"),
            category=_enum_value(
                QualificationCategory,
                item["category"],
                "category",
            ),
            statement=_text(item["statement"], "statement"),
            normalized_value=normalized_value,
            state=_enum_value(FactState, item["state"], "state"),
            evidence=tuple(
                _parse_evidence(document, evidence)
                for evidence in _list(item["evidence"], "evidence")
            ),
            confidence=float(confidence),
        )
    except ValueError as exc:
        raise QualificationOutputError(str(exc)) from exc


def _parse_evidence(
    document: SourceDocument,
    raw: Any,
) -> EvidenceReference:
    item = _object_with_exact_keys(
        raw,
        required={"quote", "start", "end"},
        context="evidence reference",
    )
    start = item["start"]
    end = item["end"]
    if isinstance(start, bool) or not isinstance(start, int):
        raise QualificationOutputError("evidence start must be an integer")
    if isinstance(end, bool) or not isinstance(end, int):
        raise QualificationOutputError("evidence end must be an integer")
    try:
        return EvidenceReference(
            document.document_id,
            _text(item["quote"], "quote"),
            start,
            end,
            document.version,
        )
    except ValueError as exc:
        raise QualificationOutputError(str(exc)) from exc


def _object_with_exact_keys(
    value: Any,
    *,
    required: set[str],
    context: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise QualificationOutputError(f"{context} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise QualificationOutputError(f"{context} field names must be text")
    keys = set(value)
    missing = required - keys
    extra = keys - required
    if missing:
        raise QualificationOutputError(
            f"{context} is missing fields: {', '.join(sorted(missing))}"
        )
    if extra:
        raise QualificationOutputError(
            f"{context} contains unsupported fields: {', '.join(sorted(extra))}"
        )
    return value


def _list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise QualificationOutputError(f"{field_name} must be a list")
    return value


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualificationOutputError(f"{field_name} must be non-empty text")
    return value


def _enum_value(enum_type: type, value: Any, field_name: str) -> Any:
    if not isinstance(value, str):
        raise QualificationOutputError(f"{field_name} must be text")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise QualificationOutputError(f"unsupported {field_name}: {value}") from exc


def _require_schema_version(value: Any) -> None:
    if value != QUALIFICATION_SCHEMA_VERSION:
        raise QualificationOutputError(
            f"unsupported qualification schema version: {value}"
        )


def _json_value(value: Any, field_name: str) -> JsonValue:
    if isinstance(value, float) and not math.isfinite(value):
        raise QualificationOutputError(f"{field_name} contains a non-finite number")
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_json_value(item, field_name) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item, field_name) for key, item in value.items()}
    raise QualificationOutputError(f"{field_name} must contain JSON-compatible data")
