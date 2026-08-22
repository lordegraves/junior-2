from dataclasses import replace

from junior.application.review_fixtures import load_review_fixtures
from junior.application.review_workspace import (
    QualificationGroupReview,
    QualificationPathReview,
    RequirementReview,
)
from junior.domain.qualifications import RequirementPriority
from junior.scoring.qualification_shadow_matcher import (
    ShadowMatchState,
    match_review_results,
)


def _resume_with(*requirements: RequirementReview):
    fixture = load_review_fixtures()[1]
    return replace(
        fixture,
        company="Resume",
        title="resume.docx",
        document_kind="resume",
        groups=(
            QualificationGroupReview(
                label="Resume Qualifications",
                priority=RequirementPriority.REQUIRED,
                paths=(
                    QualificationPathReview(
                        label="Evidence-backed items",
                        requirements=requirements,
                    ),
                ),
            ),
        ),
    )


def test_shadow_matcher_accepts_only_exact_atomic_skill_phrase() -> None:
    fixture = load_review_fixtures()[1]
    source_requirement = fixture.groups[0].paths[0].requirements[0]
    job_requirement = replace(
        source_requirement,
        label="Experience operating Kubernetes clusters",
        category="Skill",
        normalized_value=None,
    )
    job = replace(
        fixture,
        groups=(
            QualificationGroupReview(
                label="Required Skills",
                priority=RequirementPriority.REQUIRED,
                paths=(QualificationPathReview("Required", (job_requirement,)),),
            ),
        ),
    )
    resume = _resume_with(
        replace(
            source_requirement,
            label="Kubernetes",
            category="Skill",
            normalized_value=None,
        )
    )

    result = match_review_results(job, resume)

    assert result.matches[0].state is ShadowMatchState.EVIDENCED
    assert result.matches[0].resume_evidence[0].label == "Kubernetes"


def test_shadow_matcher_does_not_infer_broad_experience() -> None:
    job = load_review_fixtures()[1]
    requirement = job.groups[0].paths[0].requirements[0]
    job = replace(
        job,
        groups=(
            QualificationGroupReview(
                label="Required Experience",
                priority=RequirementPriority.REQUIRED,
                paths=(
                    QualificationPathReview(
                        "Required",
                        (replace(requirement, category="Experience"),),
                    ),
                ),
            ),
        ),
    )
    resume = _resume_with(
        replace(
            requirement,
            label="Operated large-scale infrastructure",
            normalized_value=None,
        )
    )

    result = match_review_results(job, resume)

    assert result.matches[0].state is ShadowMatchState.NEEDS_REVIEW


def test_shadow_matcher_never_scores_location_conditional_items() -> None:
    fixture = load_review_fixtures()[1]
    requirement = fixture.groups[0].paths[0].requirements[0]
    job = replace(
        fixture,
        groups=(
            QualificationGroupReview(
                label="Conditional Location Requirements",
                priority=RequirementPriority.REQUIRED,
                paths=(QualificationPathReview("Location", (requirement,)),),
            ),
        ),
    )
    resume = _resume_with(replace(requirement))

    result = match_review_results(job, resume)

    assert result.matches[0].state is ShadowMatchState.NEEDS_REVIEW
    assert "location" in result.matches[0].reason.casefold()


def test_shadow_matcher_accepts_higher_explicit_degree_level() -> None:
    fixture = load_review_fixtures()[0]
    bachelors = fixture.groups[0].paths[0].requirements[0]
    resume = _resume_with(
        replace(
            bachelors,
            label="Master of Science in Computer Science",
            normalized_value={"level": "masters"},
        )
    )

    result = match_review_results(fixture, resume)

    assert result.matches[0].state is ShadowMatchState.EVIDENCED
    assert "higher degree" in result.matches[0].reason.casefold()


def test_shadow_matcher_reports_explicit_lower_degree_as_not_found() -> None:
    fixture = load_review_fixtures()[0]
    bachelors = fixture.groups[0].paths[0].requirements[0]
    resume = _resume_with(
        replace(
            bachelors,
            label="Associate Degree in Computer Science",
            normalized_value={"level": "associate"},
        )
    )

    result = match_review_results(fixture, resume)

    assert result.matches[0].state is ShadowMatchState.NOT_FOUND


def test_shadow_matcher_requires_years_and_domain_for_timed_experience() -> None:
    fixture = load_review_fixtures()[0]
    seven_years = fixture.groups[0].paths[0].requirements[1]
    timed_requirement = replace(
        seven_years,
        label="7 years of infrastructure engineering experience",
    )
    first_group = fixture.groups[0]
    first_path = first_group.paths[0]
    fixture = replace(
        fixture,
        groups=(
            replace(
                first_group,
                paths=(
                    replace(
                        first_path,
                        requirements=(first_path.requirements[0], timed_requirement),
                    ),
                ),
            ),
        ),
    )
    resume = _resume_with(
        replace(
            seven_years,
            label="20+ years of infrastructure engineering experience",
            normalized_value={"minimum_years": 20},
        )
    )

    result = match_review_results(fixture, resume)

    assert result.matches[1].state is ShadowMatchState.EVIDENCED


def test_shadow_matcher_treats_unstated_clearance_as_unknown() -> None:
    fixture = load_review_fixtures()[1]
    source = fixture.groups[0].paths[0].requirements[0]
    clearance = replace(
        source,
        label="Active Secret clearance required",
        category="Security Clearance",
        normalized_value=None,
    )
    job = replace(
        fixture,
        groups=(
            QualificationGroupReview(
                label="Required Clearance",
                priority=RequirementPriority.REQUIRED,
                paths=(QualificationPathReview("Required", (clearance,)),),
            ),
        ),
    )
    resume = _resume_with()

    result = match_review_results(job, resume)

    assert result.matches[0].state is ShadowMatchState.NEEDS_REVIEW
    assert "silence is not failure" in result.matches[0].reason.casefold()


def test_equivalent_experience_degree_language_is_not_a_degree_failure() -> None:
    fixture = load_review_fixtures()[0]
    bachelors = replace(
        fixture.groups[0].paths[0].requirements[0],
        label="Bachelor's degree or equivalent practical experience",
    )
    job = replace(
        fixture,
        groups=(
            QualificationGroupReview(
                label="Required Education",
                priority=RequirementPriority.REQUIRED,
                paths=(QualificationPathReview("Required", (bachelors,)),),
            ),
        ),
    )
    resume = _resume_with(
        replace(
            bachelors,
            label="Associate Degree in Computer Science",
            normalized_value={"level": "associate"},
        ),
        replace(
            bachelors,
            label="20+ years operating production infrastructure",
            category="Experience",
            normalized_value={"minimum_years": 20},
        ),
    )

    result = match_review_results(job, resume)

    assert result.matches[0].state is ShadowMatchState.NEEDS_REVIEW
    assert result.matches[0].resume_evidence[0].category == "Experience"
    assert "equivalency policy" in result.matches[0].reason.casefold()


def test_skill_requirement_can_use_exact_acronym_in_resume_experience() -> None:
    fixture = load_review_fixtures()[1]
    source = fixture.groups[0].paths[0].requirements[0]
    requirement = replace(
        source,
        label="Interest in using AI applications for automation",
        category="Skill",
        normalized_value=None,
    )
    job = replace(
        fixture,
        groups=(
            QualificationGroupReview(
                label="Preferred Skills",
                priority=RequirementPriority.PREFERRED,
                paths=(QualificationPathReview("Preferred", (requirement,)),),
            ),
        ),
    )
    resume = _resume_with(
        replace(
            source,
            label="Designed an AI-assisted operational tool",
            category="Experience",
            normalized_value=None,
        )
    )

    result = match_review_results(job, resume)

    assert result.matches[0].state is ShadowMatchState.EVIDENCED
    assert result.matches[0].resume_evidence[0].category == "Experience"
