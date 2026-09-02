"""Profile-guided resume evidence matching migrated from Junior 1.x."""

from dataclasses import dataclass

from junior.domain.lifecycle import CandidateProfile, JobPosting


@dataclass(frozen=True)
class ResumeMatchResult:
    label: str
    evidence: tuple[str, ...]
    gaps: tuple[str, ...]


def match_resume_to_posting(
    posting: JobPosting,
    candidate_profile: CandidateProfile | None,
    resume_text: str | None,
) -> ResumeMatchResult:
    if candidate_profile is None or not resume_text:
        return ResumeMatchResult("Unknown", (), ())
    normalized_resume = _clean(resume_text).lower()
    posting_text = _posting_text(posting)
    evidence = tuple(
        strength
        for strength in _dedupe(
            candidate_profile.core_strengths + candidate_profile.credible_adjacent
        )
        if _term_matches(_clean(strength).lower(), normalized_resume)
        and _term_matches(_clean(strength).lower(), posting_text)
    )
    title = _clean(posting.title).lower()
    gaps = tuple(
        gap
        for gap in _dedupe(candidate_profile.learning_or_gap)
        if _should_report_gap(_clean(gap).lower(), title, posting_text)
    )
    return ResumeMatchResult(_classify(evidence, gaps), evidence, gaps)


def _should_report_gap(gap: str, title: str, posting_text: str) -> bool:
    if gap == "security engineering":
        return any(
            marker in title
            for marker in (
                "security engineer",
                "infrastructure security",
                "cloud security",
                "platform security",
            )
        )
    return _term_matches(gap, posting_text)


def _classify(evidence: tuple[str, ...], gaps: tuple[str, ...]) -> str:
    if len(evidence) >= 4 and not gaps:
        return "Very Strong"
    if len(evidence) >= 3 and len(gaps) <= 1:
        return "Strong"
    if evidence:
        return "Medium"
    return "Weak"


def _term_matches(term: str, text: str) -> bool:
    if term in text:
        return True
    words = tuple(word for word in term.split() if len(word) >= 3)
    return bool(words) and all(word in text for word in words)


def _posting_text(posting: JobPosting) -> str:
    return _clean(
        " ".join(
            filter(
                None,
                (
                    posting.title,
                    posting.location,
                    posting.remote_status,
                    posting.salary_text,
                    posting.description,
                ),
            )
        )
    ).lower()


def _clean(value: str) -> str:
    return " ".join(value.split())


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
