import pytest

from junior.interpretation.qualification_evidence_passages import (
    QualificationEvidencePassageError,
    build_evidence_passages,
    build_evidence_passages_from_ranges,
    format_evidence_passages,
    hydrate_evidence_passage_ids,
)


def test_passages_preserve_exact_full_source_positions() -> None:
    source = "Noise\nMinimum Qualifications\n  Python required.  \nEnd"
    selected = "Minimum Qualifications\n  Python required."

    passages = build_evidence_passages(source, selected)

    assert format_evidence_passages(passages) == (
        "[P0001] Minimum Qualifications\n[P0002] Python required."
    )
    assert source[passages[1].start : passages[1].end] == "Python required."


def test_hydration_uses_source_evidence_instead_of_model_copied_text() -> None:
    source = "Minimum Qualifications\nPython required."
    passages = build_evidence_passages(source, source)
    payload = {
        "groups": [
            {
                "paths": [
                    {
                        "requirements": [
                            {"evidence_passage_ids": ["P0002"]}
                        ]
                    }
                ]
            }
        ]
    }

    hydrated = hydrate_evidence_passage_ids(payload, passages)

    evidence = hydrated["groups"][0]["paths"][0]["requirements"][0]["evidence"]
    assert evidence == [
        {
            "quote": "Python required.",
            "start": source.index("Python required."),
            "end": len(source),
        }
    ]
    assert "evidence_passage_ids" not in hydrated["groups"][0]["paths"][0][
        "requirements"
    ][0]


def test_hydration_rejects_unknown_passage_id() -> None:
    passages = build_evidence_passages("Python required.", "Python required.")
    payload = {
        "groups": [
            {
                "paths": [
                    {
                        "requirements": [
                            {"evidence_passage_ids": ["P9999"]}
                        ]
                    }
                ]
            }
        ]
    }

    with pytest.raises(QualificationEvidencePassageError, match="unknown"):
        hydrate_evidence_passage_ids(payload, passages)


def test_long_line_is_split_into_exact_sentence_passages() -> None:
    source = (
        "All applicants must pass a drug test and obtain a DOT Medical Card. "
        "This role is not eligible for visa sponsorship. "
        "Must be at least 21 years of age and possess a valid driver's license."
    )

    passages = build_evidence_passages(source, source)

    assert [item.quote for item in passages] == [
        "All applicants must pass a drug test and obtain a DOT Medical Card.",
        "This role is not eligible for visa sponsorship.",
        "Must be at least 21 years of age and possess a valid driver's license.",
    ]
    assert all(source[item.start : item.end] == item.quote for item in passages)


def test_noncontiguous_ranges_keep_exact_source_positions() -> None:
    source = (
        "Minimum Qualifications\nPython required.\nBenefits\nHealth insurance.\n"
        "Preferred Qualifications\nKubernetes is a plus."
    )
    second_start = source.index("Preferred Qualifications")

    passages = build_evidence_passages_from_ranges(
        source,
        (
            (0, source.index("Benefits")),
            (second_start, len(source)),
        ),
    )

    assert [item.quote for item in passages] == [
        "Minimum Qualifications",
        "Python required.",
        "Preferred Qualifications",
        "Kubernetes is a plus.",
    ]
    assert all(source[item.start : item.end] == item.quote for item in passages)
