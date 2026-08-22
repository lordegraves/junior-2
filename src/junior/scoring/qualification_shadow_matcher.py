"""Conservative, non-authoritative matching for the qualification test GUI."""

import re
from dataclasses import dataclass
from enum import StrEnum

from junior.application.review_workspace import (
    RequirementReview,
    ReviewValidationState,
    ReviewWorkspaceResult,
)


class ShadowMatchState(StrEnum):
    EVIDENCED = "evidenced"
    NOT_FOUND = "not_found"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True, slots=True)
class ShadowRequirementMatch:
    requirement: RequirementReview
    group_label: str
    path_label: str
    priority: str
    state: ShadowMatchState
    resume_evidence: tuple[RequirementReview, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class ShadowMatchResult:
    matches: tuple[ShadowRequirementMatch, ...]

    def count(self, state: ShadowMatchState) -> int:
        return sum(match.state is state for match in self.matches)


def match_review_results(
    job: ReviewWorkspaceResult,
    resume: ReviewWorkspaceResult,
) -> ShadowMatchResult:
    """Compare validated review artifacts without making a hiring decision."""
    if job.document_kind != "job" or resume.document_kind != "resume":
        raise ValueError("shadow matching requires one job and one resume")
    if (
        job.validation_state is not ReviewValidationState.VALIDATED
        or resume.validation_state is not ReviewValidationState.VALIDATED
    ):
        raise ValueError("shadow matching requires validated interpretations")

    resume_items = tuple(
        requirement
        for group in resume.groups
        for path in group.paths
        for requirement in path.requirements
    )
    matches: list[ShadowRequirementMatch] = []
    for group in job.groups:
        conditional = group.label == "Conditional Location Requirements"
        for path in group.paths:
            for requirement in path.requirements:
                state, evidence, reason = _match_requirement(
                    requirement, resume_items, conditional
                )
                matches.append(
                    ShadowRequirementMatch(
                        requirement=requirement,
                        group_label=group.label,
                        path_label=path.label,
                        priority=group.priority.value,
                        state=state,
                        resume_evidence=evidence,
                        reason=reason,
                    )
                )
    return ShadowMatchResult(tuple(matches))


def _match_requirement(
    requirement: RequirementReview,
    resume_items: tuple[RequirementReview, ...],
    conditional: bool,
) -> tuple[ShadowMatchState, tuple[RequirementReview, ...], str]:
    if conditional:
        return (
            ShadowMatchState.NEEDS_REVIEW,
            (),
            "Job-location applicability has not been resolved.",
        )

    category = requirement.category.casefold()
    same_category = tuple(
        item for item in resume_items if item.category.casefold() == category
    )
    normalized_matches = tuple(
        item
        for item in same_category
        if requirement.normalized_value is not None
        and item.normalized_value == requirement.normalized_value
    )
    if normalized_matches:
        return (
            ShadowMatchState.EVIDENCED,
            normalized_matches,
            "The validated normalized values are identical.",
        )

    if category == "skill":
        skill_matches = tuple(
            item
            for item in resume_items
            if item.category.casefold() == "skill"
            and _contains_atomic_phrase(requirement.label, item.label)
        )
        if skill_matches:
            return (
                ShadowMatchState.EVIDENCED,
                skill_matches,
                "An exact atomic skill phrase appears in the job requirement.",
            )
        acronym_matches = _match_explicit_acronyms(requirement, resume_items)
        if acronym_matches:
            return (
                ShadowMatchState.EVIDENCED,
                acronym_matches,
                "An explicit distinctive acronym appears in validated resume evidence.",
            )
        return (
            ShadowMatchState.NOT_FOUND,
            (),
            "No exact atomic skill evidence was found in the resume interpretation.",
        )

    if category == "education":
        return _match_education(requirement, resume_items)

    if category == "experience":
        return _match_experience(requirement, same_category)

    if category in {"certification", "security clearance"}:
        return _match_credential(requirement, same_category)

    return (
        ShadowMatchState.NEEDS_REVIEW,
        (),
        "The shadow adapter will not infer this qualification from broad wording.",
    )


def _contains_atomic_phrase(requirement: str, resume_skill: str) -> bool:
    needle = _canonical_text(resume_skill)
    haystack = _canonical_text(requirement)
    if not needle or len(needle) < 2:
        return False
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


def _canonical_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9+#./-]+", value.casefold()))


def _match_education(
    requirement: RequirementReview,
    resume_items: tuple[RequirementReview, ...],
) -> tuple[ShadowMatchState, tuple[RequirementReview, ...], str]:
    required_level = _degree_level(requirement)
    if required_level is None:
        return _needs_review("The required education level could not be normalized.")
    qualifying = tuple(
        item
        for item in resume_items
        if item.category.casefold() == "education"
        and (level := _degree_level(item)) is not None
        and level >= required_level
    )
    if qualifying:
        return (
            ShadowMatchState.EVIDENCED,
            qualifying,
            "The resume states an equal or higher degree level.",
        )
    education_items = tuple(
        item for item in resume_items if item.category.casefold() == "education"
    )
    if education_items:
        if re.search(
            r"\bor\s+(?:an?\s+)?equivalent\s+(?:practical\s+)?experience\b",
            requirement.label.casefold(),
        ):
            experience_evidence = tuple(
                item
                for item in resume_items
                if item.category.casefold() == "experience"
            )
            return (
                ShadowMatchState.NEEDS_REVIEW,
                experience_evidence,
                "The degree is an alternative to practical experience; Junior "
                "cannot define the employer's equivalency policy.",
            )
        return (
            ShadowMatchState.NOT_FOUND,
            education_items,
            "The stated resume education does not reach the required degree level.",
        )
    return _needs_review("No education evidence was extracted from the resume.")


def _match_experience(
    requirement: RequirementReview,
    resume_items: tuple[RequirementReview, ...],
) -> tuple[ShadowMatchState, tuple[RequirementReview, ...], str]:
    required_years = _minimum_years(requirement)
    requirement_terms = _domain_terms(requirement.label)
    qualifying: list[RequirementReview] = []
    for item in resume_items:
        overlap = requirement_terms & _domain_terms(item.label)
        enough_domain_evidence = len(overlap) >= 2
        if not enough_domain_evidence:
            continue
        resume_years = _minimum_years(item)
        if required_years is None or (
            resume_years is not None and resume_years >= required_years
        ):
            qualifying.append(item)
    if qualifying:
        reason = (
            "The resume states enough years and overlapping experience domain terms."
            if required_years is not None
            else "The resume states multiple overlapping experience domain terms."
        )
        return ShadowMatchState.EVIDENCED, tuple(qualifying), reason
    return _needs_review(
        "Duration and domain evidence were not both explicit enough to resolve."
    )


def _match_credential(
    requirement: RequirementReview,
    resume_items: tuple[RequirementReview, ...],
) -> tuple[ShadowMatchState, tuple[RequirementReview, ...], str]:
    matches = tuple(
        item
        for item in resume_items
        if _phrase_overlap(requirement.label, item.label)
    )
    if matches:
        return (
            ShadowMatchState.EVIDENCED,
            matches,
            "The same explicit credential or clearance appears in the resume.",
        )
    return _needs_review(
        "The resume does not explicitly state this credential; silence is not failure."
    )


def _degree_level(item: RequirementReview) -> int | None:
    value = item.normalized_value
    raw_level = value.get("level") if isinstance(value, dict) else None
    text = f"{raw_level or ''} {item.label}".casefold()
    levels = {
        "high school": 1,
        "associate": 2,
        "bachelor": 3,
        "master": 4,
        "doctorate": 5,
        "doctoral": 5,
        "phd": 5,
    }
    return max((rank for name, rank in levels.items() if name in text), default=None)


def _minimum_years(item: RequirementReview) -> int | None:
    value = item.normalized_value
    if isinstance(value, dict):
        years = value.get("minimum_years")
        if isinstance(years, int | float) and years >= 0:
            return int(years)
    match = re.search(r"\b(\d{1,2})\s*\+?\s*years?\b", item.label.casefold())
    return int(match.group(1)) if match else None


def _domain_terms(value: str) -> set[str]:
    ignored = {
        "a",
        "an",
        "and",
        "across",
        "at",
        "experience",
        "full",
        "in",
        "of",
        "or",
        "plus",
        "the",
        "with",
        "year",
        "years",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9+#./-]+", value.casefold())
        if len(token) >= 3 and token not in ignored and not token.isdigit()
    }


def _phrase_overlap(left: str, right: str) -> bool:
    left_terms = _domain_terms(left)
    right_terms = _domain_terms(right)
    return len(left_terms & right_terms) >= 1 and (
        left_terms <= right_terms or right_terms <= left_terms
    )


def _match_explicit_acronyms(
    requirement: RequirementReview,
    resume_items: tuple[RequirementReview, ...],
) -> tuple[RequirementReview, ...]:
    acronyms = {
        token
        for token in re.findall(
            r"(?<![A-Za-z0-9])[A-Z][A-Z0-9/+.-]{1,}(?!\w)",
            requirement.label,
        )
        if token not in {"IT", "OR"}
    }
    if not acronyms:
        return ()
    return tuple(
        item
        for item in resume_items
        if any(_contains_token(item.label, acronym) for acronym in acronyms)
    )


def _contains_token(text: str, token: str) -> bool:
    return re.search(
        rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
        text,
        flags=re.IGNORECASE,
    ) is not None


def _needs_review(
    reason: str,
) -> tuple[ShadowMatchState, tuple[RequirementReview, ...], str]:
    return ShadowMatchState.NEEDS_REVIEW, (), reason
