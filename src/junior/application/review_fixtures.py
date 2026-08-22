"""Reviewed examples used to evaluate the native workspace before model wiring."""

from typing import Any

from junior.application.review_workspace import (
    ReviewValidationState,
    ReviewWorkspaceResult,
    build_review_workspace_result,
)
from junior.domain.documents import DocumentKind, SourceDocument
from junior.interpretation.evidence_validator import EvidenceValidationError
from junior.interpretation.qualification_evidence_validator import (
    QualificationEvidenceValidator,
)
from junior.interpretation.qualification_output_parser import (
    parse_job_qualification_output,
)

_INTERPRETER_VERSION = "reviewed-fixture-1"


def load_review_fixtures() -> tuple[ReviewWorkspaceResult, ...]:
    return (
        _alternative_paths_fixture(),
        _required_and_preferred_fixture(),
        _missing_qualifications_fixture(),
        _rejected_evidence_fixture(),
    )


def _evidence(content: str, quote: str) -> list[dict[str, object]]:
    start = content.index(quote)
    return [{"quote": quote, "start": start, "end": start + len(quote)}]


def _requirement(
    content: str,
    item_id: str,
    category: str,
    statement: str,
    normalized_value: object,
) -> dict[str, object]:
    return {
        "item_id": item_id,
        "category": category,
        "statement": statement,
        "normalized_value": normalized_value,
        "state": "stated",
        "evidence": _evidence(content, statement),
        "confidence": 0.96,
    }


def _result(
    *,
    fixture_id: str,
    title: str,
    company: str,
    content: str,
    payload: dict[str, Any],
    allow_rejection: bool = False,
) -> ReviewWorkspaceResult:
    document = SourceDocument(fixture_id, DocumentKind.JOB_POSTING, content)
    interpretation = parse_job_qualification_output(document, payload)
    validator = QualificationEvidenceValidator()
    try:
        validator.validate_job(document, interpretation)
    except EvidenceValidationError as exc:
        if not allow_rejection:
            raise
        return build_review_workspace_result(
            fixture_id=fixture_id,
            title=title,
            company=company,
            source_document=document,
            interpretation=interpretation,
            validation_state=ReviewValidationState.REJECTED,
            validation_message="Junior rejected a claim whose quote did not match.",
            rejected_claims=(str(exc),),
        )
    return build_review_workspace_result(
        fixture_id=fixture_id,
        title=title,
        company=company,
        source_document=document,
        interpretation=interpretation,
        validation_state=ReviewValidationState.VALIDATED,
        validation_message="Every displayed qualification has exact source evidence.",
    )


def _alternative_paths_fixture() -> ReviewWorkspaceResult:
    content = (
        "Basic Qualifications\n"
        "Bachelor's degree and 7 years of relevant experience, or Master's degree "
        "and 5 years of relevant experience.\n"
        "Experience operating Linux systems is required."
    )
    requirements = [
        (
            "bachelors_path",
            [
                _requirement(
                    content,
                    "bachelors",
                    "education",
                    "Bachelor's degree",
                    {"level": "bachelors"},
                ),
                _requirement(
                    content,
                    "seven_years",
                    "experience",
                    "7 years of relevant experience",
                    {"minimum_years": 7},
                ),
            ],
        ),
        (
            "masters_path",
            [
                _requirement(
                    content,
                    "masters",
                    "education",
                    "Master's degree",
                    {"level": "masters"},
                ),
                _requirement(
                    content,
                    "five_years",
                    "experience",
                    "5 years of relevant experience",
                    {"minimum_years": 5},
                ),
            ],
        ),
    ]
    return _result(
        fixture_id="fixture-alternatives",
        title="Senior Infrastructure Engineer",
        company="Example Systems",
        content=content,
        payload={
            "schema_version": "1",
            "interpreter_version": _INTERPRETER_VERSION,
            "section_state": "stated",
            "groups": [
                {
                    "group_id": "education_and_experience",
                    "priority": "required",
                    "paths": [
                        {"path_id": path_id, "requirements": items}
                        for path_id, items in requirements
                    ],
                },
                {
                    "group_id": "operating_systems",
                    "priority": "required",
                    "paths": [
                        {
                            "path_id": "linux_path",
                            "requirements": [
                                _requirement(
                                    content,
                                    "linux",
                                    "skill",
                                    "Linux systems",
                                    "linux",
                                )
                            ],
                        }
                    ],
                },
            ],
        },
    )


def _required_and_preferred_fixture() -> ReviewWorkspaceResult:
    content = (
        "Key Qualifications\nPython automation and production troubleshooting.\n"
        "Bonus Points\nExperience with Kubernetes."
    )
    return _result(
        fixture_id="fixture-required-preferred",
        title="Site Reliability Engineer",
        company="Example Cloud",
        content=content,
        payload={
            "schema_version": "1",
            "interpreter_version": _INTERPRETER_VERSION,
            "section_state": "stated",
            "groups": [
                {
                    "group_id": "key_qualifications",
                    "priority": "required",
                    "paths": [
                        {
                            "path_id": "required_path",
                            "requirements": [
                                _requirement(
                                    content, "python", "skill", "Python", "python"
                                ),
                                _requirement(
                                    content,
                                    "troubleshooting",
                                    "skill",
                                    "production troubleshooting",
                                    "production troubleshooting",
                                ),
                            ],
                        }
                    ],
                },
                {
                    "group_id": "bonus_points",
                    "priority": "preferred",
                    "paths": [
                        {
                            "path_id": "preferred_path",
                            "requirements": [
                                _requirement(
                                    content,
                                    "kubernetes",
                                    "skill",
                                    "Kubernetes",
                                    "kubernetes",
                                )
                            ],
                        }
                    ],
                },
            ],
        },
    )


def _missing_qualifications_fixture() -> ReviewWorkspaceResult:
    content = "Join our team and help build reliable services for our customers."
    return _result(
        fixture_id="fixture-missing",
        title="Platform Engineer",
        company="Example Services",
        content=content,
        payload={
            "schema_version": "1",
            "interpreter_version": _INTERPRETER_VERSION,
            "section_state": "not_stated",
            "groups": [],
        },
    )


def _rejected_evidence_fixture() -> ReviewWorkspaceResult:
    content = "Python experience is required."
    return _result(
        fixture_id="fixture-rejected",
        title="Software Engineer",
        company="Example Software",
        content=content,
        payload={
            "schema_version": "1",
            "interpreter_version": _INTERPRETER_VERSION,
            "section_state": "stated",
            "groups": [
                {
                    "group_id": "skills",
                    "priority": "required",
                    "paths": [
                        {
                            "path_id": "skills_path",
                            "requirements": [
                                {
                                    "item_id": "invented_kubernetes",
                                    "category": "skill",
                                    "statement": "Kubernetes",
                                    "normalized_value": "kubernetes",
                                    "state": "stated",
                                    "evidence": [
                                        {
                                            "quote": "Kubernetes",
                                            "start": 0,
                                            "end": 10,
                                        }
                                    ],
                                    "confidence": 0.99,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        allow_rejection=True,
    )
