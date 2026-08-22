from junior.interpretation.qualification_section_selector import (
    select_qualification_passage,
)


def test_selector_keeps_heading_and_stops_before_company_material() -> None:
    content = (
        "Responsibilities\nBuild systems.\n"
        "Experience, Education, Skills, Abilities Requested:\n"
        "Public Trust clearance required.\n"
        "Knowledge of Linux.\n"
        "Company Information\nMarketing material."
    )

    selected = select_qualification_passage(content)

    assert selected.startswith("Experience, Education, Skills, Abilities Requested")
    assert "Public Trust clearance required" in selected
    assert "Responsibilities" not in selected
    assert "Company Information" not in selected


def test_selector_stops_before_legal_material() -> None:
    content = (
        "Minimum Qualifications\nPython required.\n"
        "Preferred Qualifications\nKubernetes helpful.\n"
        "Equal Employment Opportunity\nLegal text.\n"
        "All applicants must hold a valid driver's license."
    )

    selected = select_qualification_passage(content)

    assert "Minimum Qualifications" in selected
    assert "Preferred Qualifications" in selected
    assert "Equal Employment Opportunity" not in selected
    assert "All applicants must hold a valid driver's license" not in selected


def test_selector_stops_before_benefits_after_qualifications() -> None:
    content = (
        "Minimum Qualifications\nPython required.\n"
        "Benefits + Perks\nStock options for regular employees.\n"
        "Equal Employment Opportunity\nLegal text."
    )

    selected = select_qualification_passage(content)

    assert selected == "Minimum Qualifications\nPython required."


def test_selector_prefers_real_minimum_section_over_earlier_job_metadata() -> None:
    content = (
        "Job Qualifications:\nSkills:\nNetwork systems\nExperience:\n5 years\n"
        "Job Description:\nDesign and troubleshoot systems.\n"
        "Responsibilities:\nMaintain routers.\n"
        "Minimum Qualifications:\nBachelor's degree.\nCisco knowledge.\n"
        "Benefits:\nHealth insurance."
    )

    selected = select_qualification_passage(content)

    assert selected == (
        "Minimum Qualifications:\nBachelor's degree.\nCisco knowledge."
    )


def test_selector_stops_before_why_join_marketing_section() -> None:
    content = (
        "Minimum Qualifications:\nPython required.\n"
        "Preferred Qualifications:\nKubernetes helpful.\n"
        "Why Join GDIT?\nProfessional growth and benefits.\n"
        "Total Rewards at GDIT:\nHealth coverage."
    )

    selected = select_qualification_passage(content)

    assert selected == (
        "Minimum Qualifications:\nPython required.\n"
        "Preferred Qualifications:\nKubernetes helpful."
    )


def test_selector_uses_bounded_fallback_without_inventing_a_section() -> None:
    content = "General posting text. " * 2_000

    selected = select_qualification_passage(content)

    assert selected == content[:16_000]


def test_selector_prefers_later_explicit_general_qualification_heading() -> None:
    content = (
        "We're looking for advocates with at least 2 years of customer-facing "
        "experience.\n"
        "Shift Requirement: Must be available to work weekends.\n"
        "Benefits + Perks\nHealth insurance.\n"
        "General qualifications and requirements\n"
        "Must possess a valid driver's license."
    )

    selected = select_qualification_passage(content)

    assert selected.startswith("We're looking for advocates")
    assert "at least 2 years of customer-facing experience" in selected
    assert "Shift Requirement" in selected
    assert "General qualifications and requirements" in selected
    assert "Benefits + Perks" not in selected
    assert "valid driver's license" in selected


def test_nvidia_required_heading_stops_before_recruiting_text() -> None:
    content = (
        "What you'll be doing:\nMaintain cooling systems.\n"
        "What we need to see:\n5+ years of experience.\n"
        "Ways to stand out from the crowd:\nHPC experience is a plus!\n"
        "This posting is for an existing vacancy.\n"
        "NVIDIA uses AI tools in its recruiting processes."
    )

    selected = select_qualification_passage(content)

    assert selected == (
        "What we need to see:\n5+ years of experience.\n"
        "Ways to stand out from the crowd:\nHPC experience is a plus!"
    )


def test_selector_excludes_pay_and_benefits_between_qualification_blocks() -> None:
    content = (
        "What we need to see:\nFive years of experience required.\n"
        "Ways to stand out:\nHPC experience is a plus.\n"
        "Your base salary will be determined based on location.\n"
        "You will also be eligible for equity and benefits.\n"
        "This posting is for an existing vacancy."
    )

    selected = select_qualification_passage(content)

    assert "Five years of experience required" in selected
    assert "HPC experience is a plus" in selected
    assert "base salary" not in selected
    assert "equity and benefits" not in selected
