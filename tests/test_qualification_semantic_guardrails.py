from junior.interpretation.qualification_semantic_guardrails import (
    apply_explicit_category_guardrails,
    apply_resume_qualification_guardrails,
)


def _payload(statements: list[tuple[str, str]]):
    return {
        "groups": [
            {
                "paths": [
                    {
                        "requirements": [
                            {
                                "statement": statement,
                                "category": category,
                                "evidence": [
                                    {"quote": statement, "start": 0, "end": 1}
                                ],
                            }
                            for statement, category in statements
                        ]
                    }
                ]
            }
        ]
    }


def _categories(payload):
    requirements = payload["groups"][0]["paths"][0]["requirements"]
    return [item["category"] for item in requirements]


def test_resume_guardrails_reject_metadata_and_correct_impossible_categories() -> None:
    content = (
        "Selected Projects\n"
        "Junior - Local-First Job Discovery Platform\n"
        "GitHub: https://example.invalid/junior\n"
        "Built a Python scanning pipeline.\n"
        "Education\nAssociate Degree - Computer Science"
    )
    statements = [
        "Selected Projects",
        "Junior - Local-First Job Discovery Platform",
        "GitHub: https://example.invalid/junior",
        "Built a Python scanning pipeline.",
        "Associate Degree - Computer Science",
    ]
    qualifications = []
    for index, statement in enumerate(statements):
        start = content.index(statement)
        qualifications.append(
            {
                "item_id": f"item_{index}",
                "category": "work_authorization" if index < 4 else "education",
                "statement": statement,
                "normalized_value": None,
                "state": "stated",
                "evidence": [
                    {
                        "quote": statement,
                        "start": start,
                        "end": start + len(statement),
                    }
                ],
                "confidence": 0.8,
            }
        )

    corrected = apply_resume_qualification_guardrails(
        {"qualifications": qualifications}, content
    )

    assert [item["statement"] for item in corrected["qualifications"]] == [
        "Built a Python scanning pipeline.",
        "Associate Degree - Computer Science",
    ]
    assert [item["category"] for item in corrected["qualifications"]] == [
        "skill",
        "education",
    ]


def test_resume_guardrails_keep_distinct_skills_from_one_evidence_passage() -> None:
    evidence = "Technologies: Python, Kubernetes, Ansible"
    qualifications = []
    for index, skill in enumerate(("Python", "Kubernetes", "Ansible")):
        qualifications.append(
            {
                "item_id": f"skill_{index}",
                "category": "skill",
                "statement": skill,
                "normalized_value": skill.casefold(),
                "state": "stated",
                "evidence": [
                    {"quote": evidence, "start": 0, "end": len(evidence)}
                ],
                "confidence": 0.9,
            }
        )

    corrected = apply_resume_qualification_guardrails(
        {"qualifications": qualifications}, evidence
    )

    assert [item["statement"] for item in corrected["qualifications"]] == [
        "Python",
        "Kubernetes",
        "Ansible",
    ]


def test_resume_guardrails_atomize_explicit_competency_and_technology_lists() -> None:
    content = (
        "Clayton Example\n"
        "Core CompetenciesHPC • Cluster Engineering • Infrastructure Automation\n"
        "Technologies\n"
        "OS: RHEL, Rocky, Ubuntu • Automation: Ansible, Terraform • Python, Bash\n"
        "Professional Experience\nBuilt reliable systems."
    )
    name = "Clayton Example"
    payload = {
        "qualifications": [
            {
                "item_id": "name",
                "category": "skill",
                "statement": name,
                "normalized_value": name,
                "state": "stated",
                "evidence": [{"quote": name, "start": 0, "end": len(name)}],
                "confidence": 0.8,
            }
        ]
    }

    corrected = apply_resume_qualification_guardrails(payload, content)

    assert [item["statement"] for item in corrected["qualifications"]] == [
        "HPC",
        "Cluster Engineering",
        "Infrastructure Automation",
        "RHEL",
        "Rocky",
        "Ubuntu",
        "Ansible",
        "Terraform",
        "Python",
        "Bash",
    ]
    assert all(
        item["category"] == "skill" for item in corrected["qualifications"]
    )


def test_explicit_phrases_correct_small_model_category_errors() -> None:
    original = _payload(
        [
            ("Knowledge of systems engineering principles.", "education"),
            ("Ability to perform validation activities.", "experience"),
            ("Public Trust clearance required.", "skill"),
            ("Five years of experience.", "skill"),
            ("Bachelor's degree required.", "skill"),
            ("Must pass pre-employment qualifications.", "work_authorization"),
        ]
    )

    corrected = apply_explicit_category_guardrails(original)

    assert _categories(corrected) == [
        "skill",
        "skill",
        "security_clearance",
        "experience",
        "education",
        "other",
    ]
    assert _categories(original) == [
        "education",
        "experience",
        "skill",
        "skill",
        "skill",
        "work_authorization",
    ]


def test_unclear_wording_is_left_for_model_or_user_review() -> None:
    payload = _payload([("Relevant professional background.", "other")])

    corrected = apply_explicit_category_guardrails(payload)

    assert _categories(corrected) == ["other"]


def test_source_evidence_replaces_model_invented_display_statement() -> None:
    payload = _payload([("Valid driver's license required.", "skill")])
    requirement = payload["groups"][0]["paths"][0]["requirements"][0]
    requirement["statement"] = "Invented model summary"

    corrected = apply_explicit_category_guardrails(payload)
    result = corrected["groups"][0]["paths"][0]["requirements"][0]

    assert result["statement"] == "Valid driver's license required."
    assert result["category"] == "certification"


def test_unproven_alternatives_become_one_all_required_path() -> None:
    first = _payload([("Must be at least 21 years old.", "other")])
    second = _payload([("Valid driver's license required.", "skill")])
    payload = {
        "groups": [
            {
                "paths": [
                    {
                        "path_id": "option_1",
                        "requirements": first["groups"][0]["paths"][0][
                            "requirements"
                        ],
                    },
                    {
                        "path_id": "option_2",
                        "requirements": second["groups"][0]["paths"][0][
                            "requirements"
                        ],
                    },
                ]
            }
        ]
    }

    corrected = apply_explicit_category_guardrails(payload)

    paths = corrected["groups"][0]["paths"]
    assert len(paths) == 1
    assert len(paths[0]["requirements"]) == 2
    assert paths[0]["requirements"][1]["category"] == "certification"


def test_explicit_or_preserves_alternative_paths() -> None:
    first = _payload(
        [("Bachelor's degree or equivalent experience.", "education")]
    )
    second = _payload([("Or seven years of experience.", "experience")])
    payload = {
        "groups": [
            {
                "paths": [
                    {
                        "path_id": "degree",
                        "requirements": first["groups"][0]["paths"][0][
                            "requirements"
                        ],
                    },
                    {
                        "path_id": "experience",
                        "requirements": second["groups"][0]["paths"][0][
                            "requirements"
                        ],
                    },
                ]
            }
        ]
    }

    corrected = apply_explicit_category_guardrails(payload)

    assert len(corrected["groups"][0]["paths"]) == 2


def test_boilerplate_heading_is_not_a_qualification() -> None:
    payload = _payload(
        [
            ("Legal stuff", "skill"),
            ("General qualifications and requirements", "skill"),
            ("Must pass a drug test.", "other"),
        ]
    )

    corrected = apply_explicit_category_guardrails(payload)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == [
        "Must pass a drug test."
    ]


def test_carvana_physical_and_work_rules_receive_explicit_categories() -> None:
    payload = _payload(
        [
            ("Ability to perform physically demanding tasks.", "skill"),
            ("This role is not eligible for visa sponsorship.", "other"),
            ("Must be able to read, write, speak and understand English.", "other"),
        ]
    )

    corrected = apply_explicit_category_guardrails(payload)

    assert _categories(corrected) == [
        "physical",
        "work_authorization",
        "skill",
    ]


def test_carvana_role_copy_and_duties_are_not_applicant_requirements() -> None:
    content = (
        "About the Role:\n"
        "Deliver vehicles straight to customers' doors with our custom car haulers.\n"
        "Complete customer paperwork and thorough notes in our tracking system.\n"
        "Candidates must obtain a Notary within the first 90 days.\n"
        "General qualifications and requirements\n"
        "Must be able to read, write, speak and understand English."
    )
    statements = [
        "Deliver vehicles straight to customers' doors with our custom car haulers.",
        "Complete customer paperwork and thorough notes in our tracking system.",
        "Candidates must obtain a Notary within the first 90 days.",
        "Must be able to read, write, speak and understand English.",
    ]
    payload = _payload([(statement, "other") for statement in statements])
    for requirement in payload["groups"][0]["paths"][0]["requirements"]:
        quote = requirement["evidence"][0]["quote"]
        start = content.index(quote)
        requirement["evidence"][0].update({"start": start, "end": start + len(quote)})

    corrected = apply_explicit_category_guardrails(payload, content)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == statements[2:]


def test_unheaded_imperative_responsibilities_are_not_requirements() -> None:
    duties = [
        "Lead the successful implementation of large-scale change initiatives.",
        "Design and manage operational cadences, processes, and programs.",
        "Deliver persuasive, data-driven presentations to executives.",
        "Cultivate trusted partnerships with cross-functional teams.",
        "Synthesize actionable insights from sophisticated business modeling.",
    ]
    qualification = "Project management experience is required."
    payload = _payload(
        [(statement, "skill") for statement in [*duties, qualification]]
    )

    corrected = apply_explicit_category_guardrails(payload)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == [qualification]


def test_organizational_description_is_not_a_requirement() -> None:
    narrative = (
        "GBO includes the commercial arms of Ads sellers, business development "
        "teams, and customer services and support."
    )
    qualification = "Five years of project management experience required."
    payload = _payload([(narrative, "experience"), (qualification, "experience")])

    corrected = apply_explicit_category_guardrails(payload)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == [qualification]


def test_carvana_marketing_and_rewards_are_not_applicant_requirements() -> None:
    payload = _payload(
        [
            (
                "We're looking for Customer Advocates with at least 2 years of "
                "customer-facing experience to build an exciting career at Carvana - "
                "the fastest-growing used automotive retailer in U.S. history.",
                "experience",
            ),
            (
                "We offer significant growth opportunities based on performance.",
                "other",
            ),
            ("At least 2 years of customer-facing experience.", "experience"),
        ]
    )

    corrected = apply_explicit_category_guardrails(payload)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == [
        "At least 2 years of customer-facing experience."
    ]


def test_company_narrative_after_qualifications_is_not_a_requirement() -> None:
    content = (
        "Preferred qualifications:\n"
        "Familiarity with trade operational instruments.\n"
        "Artificial intelligence will be one of humanity's most transformative "
        "inventions.\n"
        "At Google DeepMind, we are a pioneering AI lab with exceptional teams.\n"
        "We use our technologies for widespread public benefit and discovery."
    )
    statements = [
        "Familiarity with trade operational instruments.",
        "Artificial intelligence will be one of humanity's most transformative "
        "inventions.",
        "At Google DeepMind, we are a pioneering AI lab with exceptional teams.",
        "We use our technologies for widespread public benefit and discovery.",
    ]
    payload = _payload(
        [
            (statements[0], "skill"),
            (statements[1], "education"),
            (statements[2], "experience"),
            (statements[3], "experience"),
        ]
    )
    for requirement in payload["groups"][0]["paths"][0]["requirements"]:
        quote = requirement["evidence"][0]["quote"]
        start = content.index(quote)
        requirement["evidence"][0].update({"start": start, "end": start + len(quote)})

    corrected = apply_explicit_category_guardrails(payload, content)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == statements[:1]


def test_overlapping_broad_evidence_keeps_specific_sentence_items() -> None:
    payload = _payload(
        [
            ("Notary required. State rules apply. See details.", "certification"),
            ("State rules apply.", "other"),
            ("See details.", "other"),
        ]
    )
    requirements = payload["groups"][0]["paths"][0]["requirements"]
    requirements[0]["evidence"] = [
        {"quote": "Notary required.", "start": 0, "end": 16},
        {"quote": "State rules apply.", "start": 17, "end": 35},
        {"quote": "See details.", "start": 36, "end": 48},
    ]
    requirements[1]["evidence"] = [
        {"quote": "State rules apply.", "start": 17, "end": 35}
    ]
    requirements[2]["evidence"] = [
        {"quote": "See details.", "start": 36, "end": 48}
    ]

    corrected = apply_explicit_category_guardrails(payload)
    result = corrected["groups"][0]["paths"][0]["requirements"]

    assert [item["statement"] for item in result] == [
        "Notary required.",
        "State rules apply.",
        "See details.",
    ]


def test_repeated_exact_requirement_is_displayed_once() -> None:
    payload = _payload(
        [
            ("Must understand English.", "skill"),
            ("Must understand English.", "skill"),
        ]
    )
    requirements = payload["groups"][0]["paths"][0]["requirements"]
    requirements[1]["evidence"][0] = {
        "quote": "Must understand English.",
        "start": 100,
        "end": 124,
    }

    corrected = apply_explicit_category_guardrails(payload)

    result = corrected["groups"][0]["paths"][0]["requirements"]
    assert len(result) == 1


def test_independent_required_groups_display_as_one_all_required_path() -> None:
    first = _payload([("Must know Python.", "skill")])["groups"][0]
    first["group_id"] = "skills"
    first["priority"] = "required"
    second = _payload([("Must hold a license.", "certification")])["groups"][0]
    second["group_id"] = "licenses"
    second["priority"] = "required"

    corrected = apply_explicit_category_guardrails({"groups": [first, second]})

    assert len(corrected["groups"]) == 1
    group = corrected["groups"][0]
    assert group["group_id"] == "combined_required_requirements"
    assert len(group["paths"]) == 1
    assert len(group["paths"][0]["requirements"]) == 2


def test_multi_passage_model_item_becomes_atomic_source_requirements() -> None:
    payload = _payload([("Combined model summary", "other")])
    requirement = payload["groups"][0]["paths"][0]["requirements"][0]
    requirement["evidence"] = [
        {"quote": "Must hold a license.", "start": 0, "end": 20},
        {"quote": "Must pass a drug test.", "start": 21, "end": 43},
    ]

    corrected = apply_explicit_category_guardrails(payload)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == [
        "Must hold a license.",
        "Must pass a drug test.",
    ]


def test_repeated_years_of_experience_wording_is_deduplicated() -> None:
    payload = _payload(
        [
            (
                "We're looking for advocates with at least 2 years of "
                "customer-facing experience.",
                "experience",
            ),
            (
                "Team players need at least 2 years of customer-facing experience.",
                "experience",
            ),
        ]
    )
    payload["groups"][0]["paths"][0]["requirements"][1]["evidence"][0][
        "start"
    ] = 100

    corrected = apply_explicit_category_guardrails(payload)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert len(requirements) == 1


def test_compensation_and_benefit_language_is_not_a_qualification() -> None:
    payload = _payload(
        [
            ("You can progress from $17/hr to $19/hr.", "schedule"),
            ("Wellness program to support physical health.", "other"),
            (
                "If you have a bachelors degree we offer student loan repayment.",
                "education",
            ),
            ("Must hold a valid driver's license.", "certification"),
        ]
    )

    corrected = apply_explicit_category_guardrails(payload)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == [
        "Must hold a valid driver's license."
    ]


def test_equal_employment_harassment_text_is_not_a_qualification() -> None:
    payload = _payload(
        [
            (
                "Carvana also prohibits harassment of applicants or employees "
                "based on protected categories.",
                "other",
            ),
            ("Must hold a valid driver's license.", "certification"),
        ]
    )

    corrected = apply_explicit_category_guardrails(payload)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == [
        "Must hold a valid driver's license."
    ]


def test_metadata_company_and_recruiting_text_are_not_qualifications() -> None:
    payload = _payload(
        [
            ("Work Location:", "work_authorization"),
            ("USA CO Denver", "work_authorization"),
            ("Minimum Qualifications:", "education"),
            ("Skills:", "skill"),
            ("Studies have shown that some people apply selectively.", "education"),
            ("Please check with your recruiter for more details.", "other"),
            ("Think you've got what it takes to join our team?", "other"),
            ("Must hold a valid driver's license.", "certification"),
        ]
    )

    corrected = apply_explicit_category_guardrails(payload)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == [
        "Must hold a valid driver's license.",
    ]


def test_interview_instruction_is_not_a_work_schedule_requirement() -> None:
    payload = _payload(
        [
            ("You are expected to be on camera during virtual interviews.", "schedule"),
            ("Must be available to work weekends.", "schedule"),
        ]
    )

    corrected = apply_explicit_category_guardrails(payload)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == [
        "Must be available to work weekends."
    ]


def test_evidence_backed_item_cannot_claim_it_was_not_stated() -> None:
    payload = _payload([("Must know Python.", "skill")])
    payload["groups"][0]["paths"][0]["requirements"][0]["state"] = "not_stated"

    corrected = apply_explicit_category_guardrails(payload)

    requirement = corrected["groups"][0]["paths"][0]["requirements"][0]
    assert requirement["state"] == "stated"


def test_location_specific_licenses_are_not_universal_requirements() -> None:
    payload = _payload(
        [
            ("Must hold a valid driver's license.", "certification"),
            (
                "Illinois employees must obtain a Chauffeur's license.",
                "certification",
            ),
            (
                "California employees must obtain a Vehicle Verifier license.",
                "certification",
            ),
        ]
    )
    payload["groups"][0]["group_id"] = "licenses"
    payload["groups"][0]["priority"] = "required"

    corrected = apply_explicit_category_guardrails(payload)

    assert [group["group_id"] for group in corrected["groups"]] == [
        "combined_required_requirements",
        "conditional_location_requirements",
    ]
    universal = corrected["groups"][0]["paths"][0]["requirements"]
    conditional = corrected["groups"][1]["paths"][0]["requirements"]
    assert len(universal) == 1
    assert len(conditional) == 2


def test_equivalent_english_language_requirements_are_deduplicated() -> None:
    payload = _payload(
        [
            ("Must read, write, speak and understand English.", "skill"),
            ("Must be able to read, write, speak, and understand English.", "skill"),
        ]
    )
    requirements = payload["groups"][0]["paths"][0]["requirements"]
    requirements[1]["evidence"][0]["start"] = 100

    corrected = apply_explicit_category_guardrails(payload)

    result = corrected["groups"][0]["paths"][0]["requirements"]
    assert len(result) == 1


def test_source_headings_override_model_required_priority() -> None:
    content = (
        "What we need to see:\n5+ years of experience.\n"
        "Ways to stand out from the crowd:\nHPC experience is a plus!"
    )
    payload = _payload(
        [
            ("5+ years of experience.", "experience"),
            ("HPC experience is a plus!", "experience"),
        ]
    )
    payload["groups"][0]["priority"] = "required"
    requirements = payload["groups"][0]["paths"][0]["requirements"]
    requirements[0]["evidence"][0].update({"start": 21, "end": 44})
    requirements[1]["evidence"][0].update({"start": 79, "end": 104})

    corrected = apply_explicit_category_guardrails(payload, content)

    assert [group["priority"] for group in corrected["groups"]] == [
        "required",
        "preferred",
    ]


def test_incidental_or_words_do_not_create_pick_one_paths() -> None:
    payload = {
        "groups": [
            {
                "priority": "required",
                "paths": [
                    _payload(
                        [("Bachelor's degree or equivalent experience.", "education")]
                    )["groups"][0]["paths"][0],
                    _payload([("Eight years in routing or switching.", "experience")])[
                        "groups"
                    ][0]["paths"][0],
                    _payload(
                        [("DOE Q or TS clearance required.", "security_clearance")]
                    )["groups"][0]["paths"][0],
                ],
            }
        ]
    }

    corrected = apply_explicit_category_guardrails(payload)

    assert len(corrected["groups"][0]["paths"]) == 1
    assert len(corrected["groups"][0]["paths"][0]["requirements"]) == 3


def test_recruiting_process_statements_are_removed() -> None:
    payload = _payload(
        [
            ("This posting is for an existing vacancy.", "other"),
            ("NVIDIA uses AI tools in its recruiting processes.", "other"),
            ("Five years of experience required.", "experience"),
        ]
    )

    corrected = apply_explicit_category_guardrails(payload)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == [
        "Five years of experience required."
    ]


def test_compensation_and_benefit_statements_are_removed() -> None:
    payload = _payload(
        [
            ("Your base salary will be determined based on location.", "experience"),
            ("You will also be eligible for equity and benefits.", "education"),
            ("Five years of experience required.", "experience"),
        ]
    )

    corrected = apply_explicit_category_guardrails(payload)

    requirements = corrected["groups"][0]["paths"][0]["requirements"]
    assert [item["statement"] for item in requirements] == [
        "Five years of experience required."
    ]


def test_explicit_required_wording_overrides_preferred_heading() -> None:
    content = (
        "Preferred Qualifications:\nCisco certification is a plus.\n"
        "US Citizenship required."
    )
    payload = _payload(
        [
            ("Cisco certification is a plus.", "certification"),
            ("US Citizenship required.", "work_authorization"),
        ]
    )
    requirements = payload["groups"][0]["paths"][0]["requirements"]
    for requirement in requirements:
        quote = requirement["evidence"][0]["quote"]
        start = content.index(quote)
        requirement["evidence"][0].update(
            {"start": start, "end": start + len(quote)}
        )

    corrected = apply_explicit_category_guardrails(payload, content)

    priorities = {
        requirement["statement"]: group["priority"]
        for group in corrected["groups"]
        for path in group["paths"]
        for requirement in path["requirements"]
    }
    assert priorities == {
        "Cisco certification is a plus.": "preferred",
        "US Citizenship required.": "required",
    }


def test_equivalent_age_and_license_requirements_are_deduplicated() -> None:
    payload = _payload(
        [
            (
                "Must be 18 years of age and have a valid driver's license.",
                "certification",
            ),
            (
                "Must be at least 18 years of age and possess a valid "
                "driver's license.",
                "certification",
            ),
        ]
    )
    payload["groups"][0]["paths"][0]["requirements"][1]["evidence"][0][
        "start"
    ] = 100

    corrected = apply_explicit_category_guardrails(payload)

    assert len(corrected["groups"][0]["paths"][0]["requirements"]) == 1
