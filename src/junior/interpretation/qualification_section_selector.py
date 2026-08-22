"""Select bounded qualification-focused source ranges for local-model reading."""

import re
from dataclasses import dataclass

_MAX_MODEL_CHARACTERS = 16_000
_EXPLICIT_START_PATTERNS = (
    re.compile(r"(?im)^.*\bminimum qualifications?\b.*$"),
    re.compile(r"(?im)^.*\bbasic qualifications?\b.*$"),
    re.compile(r"(?im)^.*\brequired qualifications?\b.*$"),
    re.compile(r"(?im)^.*\bkey qualifications?\b.*$"),
    re.compile(r"(?im)^.*\bgeneral qualifications? and requirements?\b.*$"),
    re.compile(r"(?im)^.*\bwhat we need to see\b.*$"),
    re.compile(r"(?im)^.*\bexperience,? education,? skills,? abilities\b.*$"),
    re.compile(r"(?im)^.*\bwhat you(?:'|’)ll (?:need|bring)\b.*$"),
)
_FALLBACK_START_PATTERNS = (
    re.compile(
        r"(?im)^.*\bwe(?:'|’)re looking for\b.*"
        r"\b(?:experience|qualification|required)\b.*$"
    ),
    re.compile(r"(?im)^.*\bshift requirement\b.*$"),
    re.compile(r"(?im)^.*\bpreferred qualifications?\b.*$"),
    re.compile(r"(?im)^.*\bwho you are\b.*$"),
    re.compile(r"(?im)^.*\bqualifications?\b.*$"),
)
_END_PATTERN = re.compile(
    r"(?im)^(?:benefits?(?:\s*[+&]\s*perks)?|compensation(?:\s*[+&]\s*benefits)?|"
    r"what (?:we|the company) (?:offer|provides?)|company information|"
    r"why (?:join|work (?:at|with))\b.*|total rewards(?: at .*)?|"
    r"our identity verification process|about our work|"
    r"about (?:us|the company|our company)|equal employment opportunity|"
    r"affirmative action|application instructions?|how to apply|"
    r"applications? for this job|this posting is for an existing vacancy|"
    r".*uses ai tools? in (?:its|the) recruiting process(?:es)?|"
    r"job description|responsibilities(?: include| and duties)?|"
    r"similar searchable job titles|keywords|your base salary|salary range|"
    r"you will also be eligible for (?:equity|benefits)|"
    r"widely considered to be one of|applications? will be accepted|"
    r"at .{1,80}, we (?:are|have|believe|use)|"
    r"we are pushing the boundaries|our global teams)\s*:?.*$"
)


@dataclass(frozen=True, slots=True)
class QualificationSectionRange:
    """One exact, independently bounded portion of the source posting."""

    start: int
    end: int


def select_qualification_section_ranges(
    content: str,
) -> tuple[QualificationSectionRange, ...]:
    """Return every useful qualification block without joining unrelated text."""

    explicit_starts = {
        match.start()
        for pattern in _EXPLICIT_START_PATTERNS
        for match in pattern.finditer(content)
    }
    # A generic "Job Qualifications" metadata label is useful only when the
    # posting has no clearer section. Strong fallback wording still matters
    # before a later explicit section, as in postings that state experience or
    # shift requirements before a separate physical-requirements block.
    fallback_patterns = (
        _FALLBACK_START_PATTERNS[:-1]
        if explicit_starts
        else _FALLBACK_START_PATTERNS
    )
    fallback_starts = {
        match.start()
        for pattern in fallback_patterns
        for match in pattern.finditer(content)
    }
    starts = sorted(explicit_starts | fallback_starts)
    if not starts:
        return (QualificationSectionRange(0, min(len(content), _MAX_MODEL_CHARACTERS)),)

    ranges: list[QualificationSectionRange] = []
    for index, start in enumerate(starts):
        next_start = starts[index + 1] if index + 1 < len(starts) else len(content)
        end_match = _END_PATTERN.search(content, start + 1, next_start)
        end = end_match.start() if end_match else next_start
        end = min(end, start + _MAX_MODEL_CHARACTERS)
        if content[start:end].strip():
            ranges.append(QualificationSectionRange(start, end))
    return _merge_touching_ranges(ranges)


def _merge_touching_ranges(
    ranges: list[QualificationSectionRange],
) -> tuple[QualificationSectionRange, ...]:
    merged: list[QualificationSectionRange] = []
    for item in ranges:
        if merged and item.start <= merged[-1].end:
            prior = merged[-1]
            merged[-1] = QualificationSectionRange(
                prior.start,
                max(prior.end, item.end),
            )
        else:
            merged.append(item)
    return tuple(merged)


def select_qualification_passage(content: str) -> str:
    """Return selected blocks for compatibility with existing callers and tests."""

    return "\n".join(
        content[item.start : item.end].strip()
        for item in select_qualification_section_ranges(content)
    )
