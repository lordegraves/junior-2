import pytest

from junior.domain.documents import DocumentKind, EvidenceReference, SourceDocument
from junior.domain.facts import FactState
from junior.domain.qualifications import RequirementPriority
from junior.interpretation.evidence_validator import (
    EvidenceValidationError,
    validate_evidence_reference,
)
from junior.interpretation.qualification_evidence_validator import (
    QualificationEvidenceValidator,
)
from junior.interpretation.qualification_output_parser import (
    QualificationOutputError,
    parse_job_qualification_output,
    parse_resume_qualification_output,
)


def _evidence(content: str, quote: str) -> list[dict[str, object]]:
    start = content.index(quote)
    return [{"quote": quote, "start": start, "end": start + len(quote)}]


def _item(
    content: str,
    *,
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
        "confidence": 0.95,
    }


def test_job_contract_preserves_alternative_qualification_paths() -> None:
    content = (
        "Bachelor's degree and 7 years of experience, or Master's degree "
        "and 5 years of experience."
    )
    document = SourceDocument("job-1", DocumentKind.JOB_POSTING, content)
    payload = {
        "schema_version": "1",
        "interpreter_version": "test-interpreter-1",
        "section_state": "stated",
        "groups": [
            {
                "group_id": "minimum_education_and_experience",
                "priority": "required",
                "paths": [
                    {
                        "path_id": "bachelors_path",
                        "requirements": [
                            _item(
                                content,
                                item_id="bachelors_degree",
                                category="education",
                                statement="Bachelor's degree",
                                normalized_value={"level": "bachelors"},
                            ),
                            _item(
                                content,
                                item_id="seven_years",
                                category="experience",
                                statement="7 years of experience",
                                normalized_value={"minimum_years": 7},
                            ),
                        ],
                    },
                    {
                        "path_id": "masters_path",
                        "requirements": [
                            _item(
                                content,
                                item_id="masters_degree",
                                category="education",
                                statement="Master's degree",
                                normalized_value={"level": "masters"},
                            ),
                            _item(
                                content,
                                item_id="five_years",
                                category="experience",
                                statement="5 years of experience",
                                normalized_value={"minimum_years": 5},
                            ),
                        ],
                    },
                ],
            }
        ],
    }

    interpretation = parse_job_qualification_output(document, payload)
    QualificationEvidenceValidator().validate_job(document, interpretation)

    group = interpretation.groups[0]
    assert group.priority is RequirementPriority.REQUIRED
    assert len(group.paths) == 2
    assert [len(path.requirements) for path in group.paths] == [2, 2]


def test_required_and_preferred_groups_remain_separate() -> None:
    content = "Key Qualifications: Python. Bonus Points: Kubernetes."
    document = SourceDocument("job-2", DocumentKind.JOB_POSTING, content)
    payload = {
        "schema_version": "1",
        "interpreter_version": "test-interpreter-1",
        "section_state": "stated",
        "groups": [
            {
                "group_id": "key_qualifications",
                "priority": "required",
                "paths": [
                    {
                        "path_id": "required_path",
                        "requirements": [
                            _item(
                                content,
                                item_id="python",
                                category="skill",
                                statement="Python",
                                normalized_value="python",
                            )
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
                            _item(
                                content,
                                item_id="kubernetes",
                                category="skill",
                                statement="Kubernetes",
                                normalized_value="kubernetes",
                            )
                        ],
                    }
                ],
            },
        ],
    }

    interpretation = parse_job_qualification_output(document, payload)

    assert [group.priority for group in interpretation.groups] == [
        RequirementPriority.REQUIRED,
        RequirementPriority.PREFERRED,
    ]


def test_missing_qualification_section_stays_missing() -> None:
    document = SourceDocument(
        "job-3",
        DocumentKind.JOB_POSTING,
        "The posting contains no qualification section.",
    )

    interpretation = parse_job_qualification_output(
        document,
        {
            "schema_version": "1",
            "interpreter_version": "test-interpreter-1",
            "section_state": "not_stated",
            "groups": [],
        },
    )

    assert interpretation.section_state is FactState.NOT_STATED
    assert interpretation.groups == ()


def test_parser_rejects_fields_outside_the_contract() -> None:
    document = SourceDocument("job-4", DocumentKind.JOB_POSTING, "Python")
    payload = {
        "schema_version": "1",
        "interpreter_version": "test-interpreter-1",
        "section_state": "not_stated",
        "groups": [],
        "recommendation": "top_match",
    }

    with pytest.raises(QualificationOutputError, match="unsupported fields"):
        parse_job_qualification_output(document, payload)


def test_false_job_evidence_is_rejected_before_scoring() -> None:
    document = SourceDocument("job-5", DocumentKind.JOB_POSTING, "Python required")
    payload = {
        "schema_version": "1",
        "interpreter_version": "test-interpreter-1",
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
                                "item_id": "python",
                                "category": "skill",
                                "statement": "Python",
                                "normalized_value": "python",
                                "state": "stated",
                                "evidence": [
                                    {"quote": "Kubernetes", "start": 0, "end": 10}
                                ],
                                "confidence": 0.99,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    interpretation = parse_job_qualification_output(document, payload)

    with pytest.raises(EvidenceValidationError, match="does not match"):
        QualificationEvidenceValidator().validate_job(document, interpretation)


def test_resume_contract_requires_evidence_for_every_claim() -> None:
    content = "Operated Kubernetes clusters for five years."
    document = SourceDocument("resume-1", DocumentKind.RESUME, content)
    payload = {
        "schema_version": "1",
        "interpreter_version": "test-interpreter-1",
        "qualifications": [
            _item(
                content,
                item_id="kubernetes_experience",
                category="skill",
                statement="Kubernetes",
                normalized_value={"skill": "kubernetes"},
            )
        ],
    }

    interpretation = parse_resume_qualification_output(document, payload)
    QualificationEvidenceValidator().validate_resume(document, interpretation)

    assert interpretation.qualifications[0].evidence[0].quote == "Kubernetes"


def test_evidence_from_an_old_document_version_is_rejected() -> None:
    document = SourceDocument(
        "job-versioned",
        DocumentKind.JOB_POSTING,
        "Python required",
        version="2",
    )
    evidence = EvidenceReference(
        "job-versioned",
        "Python",
        0,
        6,
        document_version="1",
    )

    with pytest.raises(EvidenceValidationError, match="another document version"):
        validate_evidence_reference(document, evidence)
