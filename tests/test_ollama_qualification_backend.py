import json
from unittest.mock import patch

import pytest

from junior.domain.documents import DocumentKind, SourceDocument
from junior.infrastructure.ollama_qualification_backend import (
    LocalModelUnavailableError,
    OllamaQualificationBackend,
)


def test_ollama_adapter_extracts_resume_with_hydrated_evidence() -> None:
    content = "Skills\nBuilt Python services.\nEducation\nBachelor's degree."
    document = SourceDocument("resume", DocumentKind.RESUME, content)
    response = {
        "message": {
            "content": json.dumps(
                {
                    "schema_version": "1",
                    "interpreter_version": "ollama-resume-experiment-1",
                    "qualifications": [
                        {
                            "item_id": "python",
                            "category": "skill",
                            "statement": "Built Python services.",
                            "normalized_value": "python",
                            "state": "stated",
                            "evidence_passage_ids": ["P0002"],
                            "confidence": 0.9,
                        }
                    ],
                }
            )
        }
    }

    with patch(
        "junior.infrastructure.ollama_qualification_backend.urlopen",
        return_value=FakeResponse(response),
    ):
        result = OllamaQualificationBackend().propose_resume_qualifications(document)

    evidence = result["qualifications"][0]["evidence"][0]
    assert evidence["quote"] == "Built Python services."
    assert content[evidence["start"] : evidence["end"]] == evidence["quote"]


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._content = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self._content


class RawFakeResponse(FakeResponse):
    def __init__(self, content: bytes) -> None:
        self._content = content


def test_ollama_adapter_requests_json_from_loopback() -> None:
    model_payload = {
        "schema_version": "1",
        "interpreter_version": "ollama-experiment-1",
        "section_state": "not_stated",
        "groups": [],
    }
    envelope = {"message": {"content": json.dumps(model_payload)}}
    document = SourceDocument("job", DocumentKind.JOB_POSTING, "A job posting")

    with patch(
        "junior.infrastructure.ollama_qualification_backend.urlopen",
        return_value=FakeResponse(envelope),
    ) as request:
        result = OllamaQualificationBackend().propose_job_qualifications(document)

    sent = json.loads(request.call_args.args[0].data)
    assert sent["stream"] is False
    assert sent["options"]["num_ctx"] == 8192
    assert sent["options"]["num_predict"] == 4096
    assert sent["format"]["type"] == "object"
    assert sent["format"]["additionalProperties"] is False
    assert set(sent["format"]["required"]) == {
        "schema_version",
        "interpreter_version",
        "section_state",
        "groups",
    }
    group_schema = sent["format"]["properties"]["groups"]["items"]
    assert group_schema["properties"]["paths"]["minItems"] == 1
    path_schema = group_schema["properties"]["paths"]["items"]
    assert path_schema["properties"]["requirements"]["minItems"] == 1
    requirement_schema = path_schema["properties"]["requirements"]["items"]
    assert "evidence_passage_ids" in requirement_schema["required"]
    assert "evidence" not in requirement_schema["properties"]
    assert "<job_posting>" in sent["messages"][1]["content"]
    assert result == model_payload


def test_ollama_adapter_retries_one_unreadable_response() -> None:
    model_payload = {
        "schema_version": "1",
        "interpreter_version": "ollama-experiment-1",
        "section_state": "not_stated",
        "groups": [],
    }
    envelope = {"message": {"content": json.dumps(model_payload)}}
    document = SourceDocument("job", DocumentKind.JOB_POSTING, "A job posting")

    with patch(
        "junior.infrastructure.ollama_qualification_backend.urlopen",
        side_effect=[RawFakeResponse(b"not json"), FakeResponse(envelope)],
    ) as request:
        result = OllamaQualificationBackend().propose_job_qualifications(document)

    assert request.call_count == 2
    retry_body = json.loads(request.call_args.args[0].data)
    assert "previous response could not be read" in retry_body["messages"][-1][
        "content"
    ].casefold()
    assert result == model_payload


def test_ollama_adapter_sends_qualification_section_instead_of_page_noise() -> None:
    model_payload = {
        "schema_version": "1",
        "interpreter_version": "ollama-experiment-1",
        "section_state": "not_stated",
        "groups": [],
    }
    envelope = {"message": {"content": json.dumps(model_payload)}}
    document = SourceDocument(
        "job",
        DocumentKind.JOB_POSTING,
        (
            "Responsibilities\nBuild systems.\n"
            "Minimum Qualifications\nPython required.\n"
            "Company Information\nMarketing text."
        ),
    )

    with patch(
        "junior.infrastructure.ollama_qualification_backend.urlopen",
        return_value=FakeResponse(envelope),
    ) as request:
        OllamaQualificationBackend().propose_job_qualifications(document)

    prompt = json.loads(request.call_args.args[0].data)["messages"][1]["content"]
    assert "Minimum Qualifications" in prompt
    assert "Responsibilities" not in prompt
    assert "Company Information" not in prompt
    assert "[P0001] Minimum Qualifications" in prompt
    assert "[P0002] Python required." in prompt


def test_ollama_adapter_hydrates_selected_passage_id_with_exact_source() -> None:
    model_payload = {
        "schema_version": "1",
        "interpreter_version": "ollama-experiment-1",
        "section_state": "stated",
        "groups": [
            {
                "group_id": "required",
                "priority": "required",
                "paths": [
                    {
                        "path_id": "path-1",
                        "requirements": [
                            {
                                "item_id": "python",
                                "category": "skill",
                                "statement": "Python",
                                "normalized_value": "python",
                                "state": "stated",
                                "evidence_passage_ids": ["P0002"],
                                "confidence": 0.9,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    envelope = {"message": {"content": json.dumps(model_payload)}}
    content = "Minimum Qualifications\nPython required."
    document = SourceDocument("job", DocumentKind.JOB_POSTING, content)

    with patch(
        "junior.infrastructure.ollama_qualification_backend.urlopen",
        return_value=FakeResponse(envelope),
    ):
        result = OllamaQualificationBackend().propose_job_qualifications(document)

    requirement = result["groups"][0]["paths"][0]["requirements"][0]
    assert requirement["evidence"] == [
        {
            "quote": "Python required.",
            "start": content.index("Python required."),
            "end": len(content),
        }
    ]
    assert "evidence_passage_ids" not in requirement


def test_ollama_adapter_extracts_long_sections_in_ordered_batches() -> None:
    def payload(item_id: str, passage_id: str) -> dict[str, object]:
        return {
            "schema_version": "1",
            "interpreter_version": "ollama-experiment-1",
            "section_state": "stated",
            "groups": [
                {
                    "group_id": "required",
                    "priority": "required",
                    "paths": [
                        {
                            "path_id": "path-1",
                            "requirements": [
                                {
                                    "item_id": item_id,
                                    "category": "skill",
                                    "statement": item_id,
                                    "normalized_value": item_id,
                                    "state": "stated",
                                    "evidence_passage_ids": [passage_id],
                                    "confidence": 0.9,
                                }
                            ],
                        }
                    ],
                }
            ],
        }

    first = {"message": {"content": json.dumps(payload("first", "P0001"))}}
    second = {"message": {"content": json.dumps(payload("middle", "P0006"))}}
    third = {"message": {"content": json.dumps(payload("last", "P0011"))}}
    content = "\n".join(f"Requirement {number}." for number in range(1, 12))
    document = SourceDocument("job", DocumentKind.JOB_POSTING, content)

    with patch(
        "junior.infrastructure.ollama_qualification_backend.urlopen",
        side_effect=[FakeResponse(first), FakeResponse(second), FakeResponse(third)],
    ) as request:
        result = OllamaQualificationBackend().propose_job_qualifications(document)

    assert request.call_count == 3
    assert [group["group_id"] for group in result["groups"]] == [
        "batch_01_required",
        "batch_02_required",
        "batch_03_required",
    ]
    requirements = [
        item
        for group in result["groups"]
        for path in group["paths"]
        for item in path["requirements"]
    ]
    assert [item["item_id"] for item in requirements] == [
        "batch_01_first",
        "batch_02_middle",
        "batch_03_last",
    ]
    assert requirements[2]["evidence"][0]["quote"] == "Requirement 11."


def test_ollama_adapter_supplements_clear_requirements_model_skipped() -> None:
    empty_payload = {
        "schema_version": "1",
        "interpreter_version": "ollama-experiment-1",
        "section_state": "not_stated",
        "groups": [],
    }
    envelope = {"message": {"content": json.dumps(empty_payload)}}
    content = (
        "General qualifications and requirements\n"
        "Must pass a drug test.\n"
        "This role is not eligible for visa sponsorship.\n"
        "Ability to lift 50lbs."
    )
    document = SourceDocument("job", DocumentKind.JOB_POSTING, content)

    with patch(
        "junior.infrastructure.ollama_qualification_backend.urlopen",
        return_value=FakeResponse(envelope),
    ):
        result = OllamaQualificationBackend().propose_job_qualifications(document)

    requirements = result["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == [
        "Must pass a drug test.",
        "This role is not eligible for visa sponsorship.",
        "Ability to lift 50lbs.",
    ]
    assert all(item["confidence"] == 1.0 for item in requirements)


def test_ollama_adapter_recovers_explicit_required_and_preferred_lists() -> None:
    empty_payload = {
        "schema_version": "1",
        "interpreter_version": "ollama-experiment-1",
        "section_state": "not_stated",
        "groups": [],
    }
    envelope = {"message": {"content": json.dumps(empty_payload)}}
    required = [
        "Bachelor's degree or equivalent practical experience.",
        "5 years of experience in international logistics management.",
        "2 years of experience coordinating multi-jurisdictional shipping programs.",
        "Experience in managing international customs documentation frameworks.",
    ]
    preferred = [
        "6 years of experience managing global logistics pipelines.",
        "Familiarity or interest in leveraging automated tools or AI applications.",
        "Familiarity with trade operational instruments such as ATA Carnets.",
        "Track record of partnering with executive stakeholders.",
    ]
    content = "\n".join(
        [
            "Minimum qualifications:",
            *required,
            "Preferred qualifications:",
            *preferred,
            "We are pushing the boundaries across multiple domains.",
            "Lead complex, multi-shipment programs across teams.",
        ]
    )
    document = SourceDocument("job", DocumentKind.JOB_POSTING, content)

    with patch(
        "junior.infrastructure.ollama_qualification_backend.urlopen",
        return_value=FakeResponse(envelope),
    ):
        result = OllamaQualificationBackend().propose_job_qualifications(document)

    recovered = {
        group["priority"]: [
            item["statement"]
            for path in group["paths"]
            for item in path["requirements"]
        ]
        for group in result["groups"]
    }
    assert recovered == {"required": required, "preferred": preferred}


def test_ollama_adapter_refuses_non_local_endpoint() -> None:
    with pytest.raises(ValueError, match="must be local"):
        OllamaQualificationBackend(endpoint="https://models.example.com")


def test_ollama_adapter_reports_timeout_separately() -> None:
    document = SourceDocument("job", DocumentKind.JOB_POSTING, "A job posting")

    with (
        patch(
            "junior.infrastructure.ollama_qualification_backend.urlopen",
            side_effect=TimeoutError,
        ),
        pytest.raises(LocalModelUnavailableError, match="five minutes"),
    ):
        OllamaQualificationBackend().propose_job_qualifications(document)


def test_semantic_review_receives_posting_and_first_pass_record() -> None:
    model_payload = {
        "schema_version": "1",
        "interpreter_version": "ollama-experiment-1",
        "section_state": "stated",
        "groups": [
            {
                "group_id": "required",
                "priority": "required",
                "paths": [
                    {
                        "path_id": "path-1",
                        "requirements": [
                            {
                                "item_id": "python",
                                "category": "other",
                                "statement": "Python required.",
                                "normalized_value": "python",
                                "state": "stated",
                                "evidence": [
                                    {
                                        "quote": "Python required.",
                                        "start": 0,
                                        "end": 16,
                                    }
                                ],
                                "confidence": 0.7,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    review_payload = {
        "interpreter_version": "ollama-semantic-review-1",
        "section_state": "stated",
        "group_reviews": [],
        "item_reviews": [
            {
                "item_id": "python",
                "category": "skill",
                "normalized_value": "python",
                "state": "stated",
                "confidence": 0.95,
            }
        ],
    }
    envelope = {"message": {"content": json.dumps(review_payload)}}
    document = SourceDocument(
        "job", DocumentKind.JOB_POSTING, "Python required."
    )

    with patch(
        "junior.infrastructure.ollama_qualification_backend.urlopen",
        return_value=FakeResponse(envelope),
    ) as request:
        result = OllamaQualificationBackend().review_job_qualification_semantics(
            document, model_payload
        )

    sent = json.loads(request.call_args.args[0].data)
    user_prompt = sent["messages"][1]["content"]
    assert "<job_posting>" in user_prompt
    assert "<proposed_qualifications>" in user_prompt
    assert "semantic reviewer" in sent["messages"][0]["content"]
    assert sent["format"]["required"] == [
        "interpreter_version",
        "section_state",
        "group_reviews",
        "item_reviews",
    ]
    requirement = result["groups"][0]["paths"][0]["requirements"][0]
    assert requirement["category"] == "skill"
    assert requirement["confidence"] == 0.95
    assert requirement["statement"] == "Python required."
    assert requirement["evidence"] == model_payload["groups"][0]["paths"][0][
        "requirements"
    ][0]["evidence"]


def test_semantic_review_cannot_delete_an_unreviewed_item() -> None:
    proposed = {
        "schema_version": "1",
        "interpreter_version": "ollama-experiment-1",
        "section_state": "stated",
        "groups": [
            {
                "group_id": "required",
                "priority": "required",
                "paths": [
                    {
                        "path_id": "path-1",
                        "requirements": [
                            {
                                "item_id": "license",
                                "category": "certification",
                                "statement": "Driver's license required.",
                                "normalized_value": "driver license",
                                "state": "stated",
                                "evidence": [
                                    {
                                        "quote": "Driver's license required.",
                                        "start": 0,
                                        "end": 26,
                                    }
                                ],
                                "confidence": 0.9,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    review = {
        "interpreter_version": "ollama-semantic-review-1",
        "section_state": "stated",
        "group_reviews": [],
        "item_reviews": [],
    }
    envelope = {"message": {"content": json.dumps(review)}}
    document = SourceDocument(
        "job", DocumentKind.JOB_POSTING, "Driver's license required."
    )

    with patch(
        "junior.infrastructure.ollama_qualification_backend.urlopen",
        return_value=FakeResponse(envelope),
    ):
        result = OllamaQualificationBackend().review_job_qualification_semantics(
            document, proposed
        )

    assert result == proposed


def test_semantic_review_ignores_unknown_correction_identifier() -> None:
    proposed = {
        "schema_version": "1",
        "interpreter_version": "ollama-experiment-1",
        "section_state": "stated",
        "groups": [],
    }
    review = {
        "interpreter_version": "ollama-semantic-review-1",
        "section_state": "stated",
        "group_reviews": [],
        "item_reviews": [
            {
                "item_id": "not-an-existing-item",
                "category": "skill",
                "normalized_value": "ignored",
                "state": "stated",
                "confidence": 1.0,
            }
        ],
    }
    envelope = {"message": {"content": json.dumps(review)}}
    document = SourceDocument("job", DocumentKind.JOB_POSTING, "A posting")

    with patch(
        "junior.infrastructure.ollama_qualification_backend.urlopen",
        return_value=FakeResponse(envelope),
    ):
        result = OllamaQualificationBackend().review_job_qualification_semantics(
            document, proposed
        )

    assert result == proposed


def test_semantic_review_failure_preserves_validated_extraction() -> None:
    proposed = {
        "schema_version": "1",
        "interpreter_version": "ollama-experiment-1",
        "section_state": "stated",
        "groups": [
            {
                "group_id": "required",
                "priority": "required",
                "paths": [
                    {
                        "path_id": "path-1",
                        "requirements": [
                            {
                                "item_id": "python",
                                "category": "skill",
                                "statement": "Python required.",
                                "normalized_value": "python",
                                "state": "stated",
                                "evidence": [
                                    {
                                        "quote": "Python required.",
                                        "start": 0,
                                        "end": 16,
                                    }
                                ],
                                "confidence": 0.9,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    envelope = {"message": {"content": "{not complete"}}
    document = SourceDocument(
        "job", DocumentKind.JOB_POSTING, "Python required."
    )

    with patch(
        "junior.infrastructure.ollama_qualification_backend.urlopen",
        return_value=FakeResponse(envelope),
    ):
        result = OllamaQualificationBackend().review_job_qualification_semantics(
            document, proposed
        )

    assert result == proposed
