"""Give the model stable references to exact source passages."""

import re
from dataclasses import dataclass
from typing import Any


class QualificationEvidencePassageError(ValueError):
    """The model referenced evidence Junior did not provide."""


@dataclass(frozen=True, slots=True)
class QualificationEvidencePassage:
    passage_id: str
    quote: str
    start: int
    end: int


def build_evidence_passages(
    source_content: str,
    selected_passage: str,
) -> tuple[QualificationEvidencePassage, ...]:
    """Split selected text into numbered lines with exact full-source positions."""

    selected_start = source_content.find(selected_passage)
    if selected_start < 0:
        raise QualificationEvidencePassageError(
            "the selected qualification passage is not in the source document"
        )

    passages: list[QualificationEvidencePassage] = []
    relative_position = 0
    for raw_line in selected_passage.splitlines(keepends=True):
        line = raw_line.strip()
        leading = len(raw_line) - len(raw_line.lstrip())
        for sentence_match in _sentence_matches(line):
            quote = sentence_match.group().strip()
            sentence_leading = len(sentence_match.group()) - len(
                sentence_match.group().lstrip()
            )
            start = (
                selected_start
                + relative_position
                + leading
                + sentence_match.start()
                + sentence_leading
            )
            passages.append(
                QualificationEvidencePassage(
                    passage_id=f"P{len(passages) + 1:04d}",
                    quote=quote,
                    start=start,
                    end=start + len(quote),
                )
            )
        relative_position += len(raw_line)
    return tuple(passages)


def build_evidence_passages_from_ranges(
    source_content: str,
    ranges: tuple[tuple[int, int], ...],
) -> tuple[QualificationEvidencePassage, ...]:
    """Build one ordered evidence list from non-contiguous exact source ranges."""

    passages: list[QualificationEvidencePassage] = []
    for range_start, range_end in ranges:
        if not (0 <= range_start <= range_end <= len(source_content)):
            raise QualificationEvidencePassageError(
                "a selected qualification range is outside the source document"
            )
        selected = source_content[range_start:range_end]
        relative_position = 0
        for raw_line in selected.splitlines(keepends=True):
            line = raw_line.strip()
            leading = len(raw_line) - len(raw_line.lstrip())
            for sentence_match in _sentence_matches(line):
                quote = sentence_match.group().strip()
                sentence_leading = len(sentence_match.group()) - len(
                    sentence_match.group().lstrip()
                )
                start = (
                    range_start
                    + relative_position
                    + leading
                    + sentence_match.start()
                    + sentence_leading
                )
                passages.append(
                    QualificationEvidencePassage(
                        passage_id=f"P{len(passages) + 1:04d}",
                        quote=quote,
                        start=start,
                        end=start + len(quote),
                    )
                )
            relative_position += len(raw_line)
    return tuple(passages)


def _sentence_matches(line: str):
    if not line:
        return ()
    # Split only when sentence punctuation is followed by a likely new sentence.
    # This avoids breaking common abbreviations and decimal values unnecessarily.
    return tuple(re.finditer(r".+?(?:[.!?](?=\s+[A-Z*])|$)", line))


def format_evidence_passages(
    passages: tuple[QualificationEvidencePassage, ...],
) -> str:
    """Render passages for the model without asking it to reproduce source text."""

    return "\n".join(f"[{item.passage_id}] {item.quote}" for item in passages)


def hydrate_evidence_passage_ids(
    payload: dict[str, Any],
    passages: tuple[QualificationEvidencePassage, ...],
) -> dict[str, Any]:
    """Replace model-selected passage IDs with exact evidence records."""

    passage_by_id = {item.passage_id: item for item in passages}
    try:
        for group in payload["groups"]:
            for path in group["paths"]:
                for requirement in path["requirements"]:
                    passage_ids = requirement.pop("evidence_passage_ids")
                    if not isinstance(passage_ids, list) or not passage_ids:
                        raise QualificationEvidencePassageError(
                            "qualification evidence passage IDs must be a "
                            "non-empty list"
                        )
                    evidence = []
                    seen: set[str] = set()
                    for passage_id in passage_ids:
                        if not isinstance(passage_id, str) or passage_id in seen:
                            raise QualificationEvidencePassageError(
                                "qualification evidence passage IDs must be unique text"
                            )
                        seen.add(passage_id)
                        passage = passage_by_id.get(passage_id)
                        if passage is None:
                            raise QualificationEvidencePassageError(
                                "the model referenced an unknown evidence passage"
                            )
                        evidence.append(
                            {
                                "quote": passage.quote,
                                "start": passage.start,
                                "end": passage.end,
                            }
                        )
                    requirement["evidence"] = evidence
    except (KeyError, TypeError) as exc:
        raise QualificationEvidencePassageError(
            "the model returned an incomplete evidence reference"
        ) from exc
    return payload
