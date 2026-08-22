from junior.interpretation.qualification_evidence_resolver import (
    resolve_unique_evidence_offsets,
)


def _payload(quote: str, start: int, end: int):
    return {
        "groups": [
            {
                "paths": [
                    {
                        "requirements": [
                            {
                                "evidence": [
                                    {"quote": quote, "start": start, "end": end}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }


def _evidence(payload):
    return payload["groups"][0]["paths"][0]["requirements"][0]["evidence"][0]


def test_unique_quote_offsets_are_resolved_by_code() -> None:
    original = _payload("Python required", 99, 100)

    resolved = resolve_unique_evidence_offsets(original, "Role: Python required.")

    assert _evidence(resolved) == {
        "quote": "Python required",
        "start": 6,
        "end": 21,
    }
    assert _evidence(original) == {
        "quote": "Python required",
        "start": 99,
        "end": 100,
    }


def test_duplicate_quote_does_not_get_a_guessed_location() -> None:
    payload = _payload("Python", 99, 105)

    resolved = resolve_unique_evidence_offsets(payload, "Python and Python")

    assert _evidence(resolved)["start"] == 99


def test_missing_quote_does_not_get_invented_offsets() -> None:
    payload = _payload("Kubernetes", 0, 10)

    resolved = resolve_unique_evidence_offsets(payload, "Python required")

    assert _evidence(resolved)["quote"] == "Kubernetes"
    assert _evidence(resolved)["start"] == 0


def test_unique_word_sequence_resolves_harmless_copy_differences() -> None:
    content = "Required: Ability to support customers—seven days a week."
    payload = _payload("ability to support customers - seven days a week", 99, 100)

    resolved = resolve_unique_evidence_offsets(payload, content)

    assert _evidence(resolved) == {
        "quote": "Ability to support customers—seven days a week",
        "start": 10,
        "end": 56,
    }


def test_changed_or_reordered_words_are_not_resolved() -> None:
    content = "Ability to support customers seven days a week."
    payload = _payload("Ability to delight customers seven days a week", 99, 100)

    resolved = resolve_unique_evidence_offsets(payload, content)

    assert _evidence(resolved)["start"] == 99


def test_duplicate_word_sequence_is_not_resolved() -> None:
    content = "Support customers every day. Support customers every day."
    payload = _payload("support customers every day", 99, 100)

    resolved = resolve_unique_evidence_offsets(payload, content)

    assert _evidence(resolved)["start"] == 99
