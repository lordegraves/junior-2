"""Resolve exact quote locations without trusting model arithmetic."""

import re
from copy import deepcopy
from typing import Any

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:['’][a-z0-9]+)?", re.IGNORECASE)


def resolve_unique_evidence_offsets(
    payload: dict[str, Any],
    source_content: str,
) -> dict[str, Any]:
    """Correct offsets only when an evidence quote occurs exactly once."""

    resolved = deepcopy(payload)
    groups = resolved.get("groups")
    if not isinstance(groups, list):
        qualifications = resolved.get("qualifications")
        if isinstance(qualifications, list):
            for qualification in qualifications:
                _resolve_requirement(qualification, source_content)
        return resolved
    for group in groups:
        if not isinstance(group, dict):
            continue
        paths = group.get("paths")
        if not isinstance(paths, list):
            continue
        for path in paths:
            if not isinstance(path, dict):
                continue
            requirements = path.get("requirements")
            if not isinstance(requirements, list):
                continue
            for requirement in requirements:
                _resolve_requirement(requirement, source_content)
    return resolved


def _resolve_requirement(requirement: Any, source_content: str) -> None:
    if not isinstance(requirement, dict):
        return
    evidence_items = requirement.get("evidence")
    if not isinstance(evidence_items, list):
        return
    for evidence in evidence_items:
        if not isinstance(evidence, dict):
            continue
        quote = evidence.get("quote")
        if not isinstance(quote, str) or not quote:
            continue
        locations = _all_locations(source_content, quote)
        if len(locations) == 1:
            evidence["start"] = locations[0]
            evidence["end"] = locations[0] + len(quote)
            continue
        if locations:
            continue
        token_span = _unique_token_span(source_content, quote)
        if token_span is not None:
            start, end = token_span
            evidence["quote"] = source_content[start:end]
            evidence["start"] = start
            evidence["end"] = end


def _all_locations(content: str, quote: str) -> list[int]:
    locations: list[int] = []
    position = content.find(quote)
    while position >= 0:
        locations.append(position)
        position = content.find(quote, position + 1)
    return locations


def _unique_token_span(content: str, quote: str) -> tuple[int, int] | None:
    source_tokens = _tokens_with_spans(content)
    quote_tokens = [token for token, _start, _end in _tokens_with_spans(quote)]
    if len(quote_tokens) < 3 or len(quote_tokens) > len(source_tokens):
        return None
    matches: list[tuple[int, int]] = []
    width = len(quote_tokens)
    for index in range(len(source_tokens) - width + 1):
        candidate = [
            token
            for token, _start, _end in source_tokens[index : index + width]
        ]
        if candidate == quote_tokens:
            matches.append(
                (source_tokens[index][1], source_tokens[index + width - 1][2])
            )
    return matches[0] if len(matches) == 1 else None


def _tokens_with_spans(text: str) -> list[tuple[str, int, int]]:
    return [
        (match.group().casefold().replace("’", "'"), match.start(), match.end())
        for match in _TOKEN_PATTERN.finditer(text)
    ]
