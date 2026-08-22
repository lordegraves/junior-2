"""Correct explicit qualification meaning with deterministic source rules."""

import re
from copy import deepcopy
from typing import Any


def apply_resume_qualification_guardrails(
    payload: dict[str, Any], source_content: str = ""
) -> dict[str, Any]:
    """Keep resume items evidence-worded and reject impossible categories."""

    corrected = deepcopy(payload)
    qualifications = corrected.get("qualifications")
    if not isinstance(qualifications, list):
        return corrected
    retained = []
    seen: set[str] = set()
    for item in qualifications:
        if not isinstance(item, dict):
            continue
        evidence_text = _evidence_text(item)
        proposed_statement = item.get("statement")
        display_text = (
            proposed_statement.strip()
            if isinstance(proposed_statement, str)
            and proposed_statement.strip()
            and proposed_statement.strip() in evidence_text
            else evidence_text
        )
        lowered = " ".join(display_text.casefold().split()).strip(" :.-")
        if not lowered or _is_resume_metadata(lowered, item, source_content):
            continue
        key = _statement_dedup_key(display_text)
        if key in seen:
            continue
        seen.add(key)
        item["statement"] = display_text
        item["state"] = (
            "ambiguous" if item.get("state") == "ambiguous" else "stated"
        )
        item["category"] = _resume_category(item.get("category"), lowered)
        retained.append(item)
    retained.extend(_resume_list_skills(source_content, retained))
    corrected["qualifications"] = retained
    return corrected


def _is_resume_metadata(
    statement: str, item: dict[str, Any], source_content: str
) -> bool:
    if statement in {
        "professional summary",
        "core competencies",
        "technologies",
        "professional experience",
        "selected projects",
        "education",
    }:
        return True
    if statement.startswith("core competencies") or statement.count("•") >= 3:
        return True
    contact_pattern = (
        r"\b(?:[\w.+-]+@[\w.-]+|\(?\d{3}\)?[-\s]\d{3}[-\s]\d{4})\b"
    )
    if re.search(contact_pattern, statement):
        return True
    if re.fullmatch(r"(?:linkedin|github):?\s+\S+", statement):
        return True
    if "github:" in statement and not re.search(
        r"\b(?:built|designed|developed|implemented|deployed|operated)\b", statement
    ):
        return True
    evidence = item.get("evidence")
    ends = [
        reference.get("end")
        for reference in evidence
        if isinstance(reference, dict) and isinstance(reference.get("end"), int)
    ] if isinstance(evidence, list) else []
    starts = [
        reference.get("start")
        for reference in evidence
        if isinstance(reference, dict) and isinstance(reference.get("start"), int)
    ] if isinstance(evidence, list) else []
    if starts and min(starts) == 0 and re.fullmatch(
        r"[a-z]+(?:\s+[a-z]+){1,3}", statement
    ):
        return True
    if source_content and ends:
        following_line = source_content[max(ends) :].lstrip().splitlines()[0:1]
        if following_line and following_line[0].casefold().startswith("github:"):
            return True
    return False


def _resume_list_skills(
    source_content: str, existing: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Turn explicit competency/technology lists into atomic evidenced skills."""

    existing_keys = {
        _statement_dedup_key(str(item.get("statement", ""))) for item in existing
    }
    additions: list[dict[str, Any]] = []
    in_technologies = False
    for line_number, raw_line in enumerate(source_content.splitlines()):
        line = raw_line.strip()
        if line.casefold() == "technologies":
            in_technologies = True
            continue
        if line.casefold().startswith("professional experience"):
            in_technologies = False
        if line.casefold().startswith("core competencies"):
            list_text = line[len("Core Competencies") :]
            is_competency_list = True
        elif in_technologies:
            list_text = line
            is_competency_list = False
        else:
            continue
        candidates: list[str] = []
        for group in list_text.split("•"):
            value_text = group.split(":", 1)[-1]
            if is_competency_list:
                candidates.append(value_text.strip())
            else:
                candidates.extend(_split_resume_values(value_text))
        line_start = source_content.find(raw_line)
        for index, skill in enumerate(candidates):
            if not skill or len(skill) > 80:
                continue
            start = source_content.find(skill, line_start, line_start + len(raw_line))
            key = _statement_dedup_key(skill)
            if start < 0 or not key or key in existing_keys:
                continue
            existing_keys.add(key)
            additions.append(
                {
                    "item_id": f"deterministic_skill_{line_number}_{index}",
                    "category": "skill",
                    "statement": skill,
                    "normalized_value": skill.casefold(),
                    "state": "stated",
                    "evidence": [
                        {"quote": skill, "start": start, "end": start + len(skill)}
                    ],
                    "confidence": 1.0,
                }
            )
    return additions


def _split_resume_values(value_text: str) -> list[str]:
    values: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(value_text):
        if character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        elif character == "," and depth == 0:
            values.append(value_text[start:index].strip())
            start = index + 1
    values.append(value_text[start:].strip())
    return [value for value in values if value]


def _resume_category(model_category: Any, statement: str) -> str:
    explicit = _explicit_category(statement)
    if explicit is not None:
        return explicit
    if re.search(r"\b(?:19|20)\d{2}\b", statement) and re.search(
        r"\b(?:present|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
        statement,
    ):
        return "experience"
    if model_category == "work_authorization" and not re.search(
        r"\b(?:citizen|visa|sponsor|authorized to work|work authorization|"
        r"permanent resident|green card)\b",
        statement,
    ):
        return "skill"
    if model_category == "security_clearance" and not re.search(
        r"\b(?:clearance|public trust|background investigation)\b", statement
    ):
        return "skill"
    if model_category == "education" and not re.search(
        r"\b(?:degree|college|university|diploma|education)\b", statement
    ):
        return "skill"
    return model_category if isinstance(model_category, str) else "other"


def apply_explicit_category_guardrails(
    payload: dict[str, Any], source_content: str = ""
) -> dict[str, Any]:
    """Apply only corrections that exact source wording can prove."""

    corrected = deepcopy(payload)
    groups = corrected.get("groups")
    if not isinstance(groups, list):
        return corrected
    _split_multi_evidence_requirements(groups)
    _remove_overlapping_and_duplicate_evidence(groups)
    if source_content:
        groups = _apply_source_priorities(groups, source_content)
        corrected["groups"] = groups
    for group in groups:
        for requirement in _requirements(group):
            evidence_text = _evidence_text(requirement)
            if not evidence_text:
                continue
            # Display source wording, never a model-invented qualification label.
            requirement["statement"] = evidence_text
            if requirement.get("state") in {"not_stated", "not_applicable"}:
                # An evidence-backed item necessarily describes stated source text.
                requirement["state"] = "stated"
            category = _explicit_category(evidence_text)
            if category is not None:
                requirement["category"] = category
        _remove_boilerplate_requirements(group, source_content)
        _collapse_unproven_alternative_paths(group)
    corrected["groups"] = [
        group
        for group in groups
        if isinstance(group, dict) and group.get("paths")
    ]
    corrected["groups"] = _merge_simple_groups_by_priority(corrected["groups"])
    corrected["groups"] = _separate_location_conditional_requirements(
        corrected["groups"]
    )
    if not corrected["groups"]:
        corrected["section_state"] = "not_stated"
    return corrected


def _requirements(group: Any):
    if not isinstance(group, dict) or not isinstance(group.get("paths"), list):
        return
    for path in group["paths"]:
        if not isinstance(path, dict):
            continue
        requirements = path.get("requirements")
        if not isinstance(requirements, list):
            continue
        for requirement in requirements:
            if isinstance(requirement, dict):
                yield requirement


def _explicit_category(statement: str) -> str | None:
    lowered = " ".join(statement.casefold().split())
    if "public trust" in lowered or "security clearance" in lowered:
        return "security_clearance"
    if lowered.startswith("experience ") or " years of experience" in lowered:
        return "experience"
    education_terms = (
        "bachelor's degree",
        "bachelors degree",
        "master's degree",
        "masters degree",
        "doctoral degree",
        "phd",
        "high school diploma",
    )
    if any(term in lowered for term in education_terms):
        return "education"
    physical_terms = (
        "physically demanding",
        "walk/stand",
        "walk and stand",
        "lift and carry",
        "lifting and carrying",
        "reach with arms",
        "kneel",
        "crouch",
        "manual dexterity",
        "visual acuity",
    )
    if any(term in lowered for term in physical_terms) or re.search(
        r"\b(?:lift|carry|pulling)\b.{0,30}\b\d+\s*(?:lb|lbs|pounds)\b",
        lowered,
    ):
        return "physical"
    if lowered.startswith(("knowledge of ", "ability to ", "skill in ", "skills in ")):
        return "skill"
    certification_terms = (
        "driver's license",
        "driver’s license",
        "chauffeur's license",
        "chauffeur’s license",
        "vehicle verifier license",
        "notary",
        "medical card",
        "certification",
        "certificate",
    )
    if any(term in lowered for term in certification_terms):
        return "certification"
    if "clean driving record" in lowered or "state-specific requirements" in lowered:
        return "other"
    if any(
        term in lowered
        for term in (
            "visa sponsorship",
            "authorized to work",
            "work authorization",
            "eligible to work",
        )
    ):
        return "work_authorization"
    if any(
        term in lowered
        for term in (
            "available to work",
            "weekend",
            "work schedule",
            "shift requirement",
        )
    ):
        return "schedule"
    if re.search(r"\b(?:read|write|speak).{0,45}\benglish\b", lowered):
        return "skill"
    if "pre-employment qualification" in lowered:
        return "other"
    return None


def _evidence_text(requirement: dict[str, Any]) -> str:
    evidence = requirement.get("evidence")
    if not isinstance(evidence, list):
        return ""
    quotes = [
        item.get("quote", "").strip()
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("quote"), str)
    ]
    return " ".join(quote for quote in quotes if quote)


def _remove_boilerplate_requirements(
    group: Any, source_content: str = ""
) -> None:
    if not isinstance(group, dict) or not isinstance(group.get("paths"), list):
        return
    retained_paths = []
    for path in group["paths"]:
        if not isinstance(path, dict) or not isinstance(path.get("requirements"), list):
            continue
        path["requirements"] = [
            requirement
            for requirement in path["requirements"]
            if isinstance(requirement, dict)
            and not _is_boilerplate(_evidence_text(requirement))
            and not _is_non_qualification_context(requirement, source_content)
            and not _is_context_mismatch(requirement)
        ]
        if path["requirements"]:
            retained_paths.append(path)
    group["paths"] = retained_paths


def _is_non_qualification_context(
    requirement: dict[str, Any], source_content: str
) -> bool:
    """Reject role/reward copy even when a model quotes it exactly."""

    statement = " ".join(_evidence_text(requirement).casefold().split())
    if not statement:
        return False

    # These are descriptions of the employer, opportunity, or employee reward,
    # not facts an applicant must bring or satisfy.
    if any(
        phrase in statement
        for phrase in (
            "fastest-growing used automotive retailer",
            "fastest growing used automotive retailer",
            "build an exciting career",
            "leading the charge in reintroducing happiness",
            "ready to join the 'hauler-life'",
            "ready to join the ‘hauler-life’",
            "significant growth opportunities based on performance",
            "merit opportunities annually",
            "invest in our team members",
        )
    ):
        return True

    # Company/industry narrative can follow a real qualification list without
    # a heading. Small models sometimes relabel these factual declarations as
    # education or experience, so reject prose whose subject is the employer,
    # its products, or the field rather than the applicant.
    if re.match(
        r"(?i)^(?:at\s+[^,]{1,80},\s+we\s+(?:are|build|develop|use)|"
        r"we\s+(?:are|build|develop|use)\s+(?:our\s+)?(?:technolog|product)|"
        r"our\s+(?:company|mission|products?|technologies|teams?)\b|"
        r"(?:[a-z][a-z0-9&./+-]{1,12}\s+)?includes\s+the\s+"
        r"(?:commercial\s+)?(?:arms?|teams?|groups?|organizations?)\b|"
        r"(?:artificial intelligence|machine learning|the company|the industry)\s+"
        r"(?:is|are|will|has|have)\b)",
        statement,
    ):
        return True

    # Imperative bullets describe work to perform, even when a posting omits a
    # responsibilities heading or places duties next to qualifications.
    has_requirement_language = bool(
        re.search(
            r"(?i)\b(?:candidates? must|must be|must have|required|requires?|"
            r"at least \d+\s+years?|ability to|proficiency|familiarity|"
            r"knowledge of|experience (?:in|with)|license|certification)\b",
            statement,
        )
    )
    duty_opening = re.match(
        r"(?i)^(?:act as|align|analy[sz]e|build|complete|consistently drive|"
        r"coordinate|create|cultivate|define|deliver|design|develop|drive|"
        r"establish|execute|frequently load|implement|improve|influence|inspect|"
        r"lead|load|manage|monitor|operate|own|partner with|perform|provide|"
        r"secure|serve as|support|synthesize|transport|unload|work with)\b",
        statement,
    )
    if duty_opening and not has_requirement_language:
        return True
    return False


def _source_section_at(
    requirement: dict[str, Any], source_content: str
) -> str | None:
    if not source_content:
        return None
    evidence = requirement.get("evidence")
    starts = [
        item.get("start")
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("start"), int)
    ] if isinstance(evidence, list) else []
    if not starts:
        return None
    headings: list[tuple[int, str]] = []
    patterns = (
        ("duties", r"(?:about the role|responsibilities|what you(?:'|’)ll do)"),
        (
            "rewards",
            r"(?:benefits?(?:\s*[+&]\s*perks)?|"
            r"unlock your earning potential|compensation)",
        ),
        (
            "qualifications",
            r"(?:general qualifications? and requirements?|"
            r"minimum|required|preferred qualifications?)",
        ),
        ("legal", r"(?:legal stuff|equal employment opportunity)"),
    )
    for match in re.finditer(r"(?m)^\s*([^\r\n]{1,100})\s*$", source_content):
        line = match.group(1).strip(" :")
        for section, pattern in patterns:
            if re.fullmatch(pattern, line, re.IGNORECASE):
                headings.append((match.start(), section))
                break
    preceding = [section for position, section in headings if position <= min(starts)]
    return preceding[-1] if preceding else None


def _is_context_mismatch(requirement: dict[str, Any]) -> bool:
    """Reject category claims whose quoted text does not express that meaning."""

    statement = " ".join(_evidence_text(requirement).casefold().split())
    category = requirement.get("category")
    if category == "work_authorization":
        return not any(
            term in statement
            for term in (
                "citizen",
                "visa",
                "sponsor",
                "authorized to work",
                "authorization",
                "permanent resident",
                "green card",
            )
        )
    if category == "schedule":
        return not any(
            term in statement
            for term in (
                "shift",
                "schedule",
                "hours",
                "weekend",
                "available to work",
                "days a week",
                "days off",
                "full time",
                "full-time",
                "part time",
                "part-time",
            )
        )
    return False


def _remove_overlapping_and_duplicate_evidence(groups: list[Any]) -> None:
    """Keep the most specific item when model evidence overlaps or repeats."""

    requirements = [
        requirement
        for group in groups
        for requirement in _requirements(group)
    ]
    evidence_use: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for requirement in requirements:
        evidence = requirement.get("evidence")
        if not isinstance(evidence, list):
            continue
        for reference in evidence:
            if isinstance(reference, dict):
                key = (reference.get("start"), reference.get("end"))
                evidence_use.setdefault(key, []).append(requirement)
    for requirement in requirements:
        evidence = requirement.get("evidence")
        if not isinstance(evidence, list) or len(evidence) < 2:
            continue
        unique_evidence = [
            reference
            for reference in evidence
            if len(
                evidence_use.get(
                    (reference.get("start"), reference.get("end")),
                    [],
                )
            )
            == 1
        ]
        requirement["evidence"] = unique_evidence or [evidence[0]]

    seen_statements: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        for path in group.get("paths", []):
            if not isinstance(path, dict) or not isinstance(
                path.get("requirements"), list
            ):
                continue
            retained = []
            for requirement in path["requirements"]:
                if not isinstance(requirement, dict) or not requirement.get("evidence"):
                    continue
                evidence_text = _evidence_text(requirement)
                # A rejected marketing/benefit sentence must not consume the
                # deduplication key of a later, cleanly quoted requirement.
                if _is_boilerplate(evidence_text):
                    retained.append(requirement)
                    continue
                statement_key = _statement_dedup_key(evidence_text)
                if statement_key and statement_key in seen_statements:
                    continue
                seen_statements.add(statement_key)
                retained.append(requirement)
            path["requirements"] = retained


def _split_multi_evidence_requirements(groups: list[Any]) -> None:
    """Make each requirement atomic by assigning it one exact source passage."""

    for group in groups:
        if not isinstance(group, dict):
            continue
        for path in group.get("paths", []):
            if not isinstance(path, dict) or not isinstance(
                path.get("requirements"), list
            ):
                continue
            atomic = []
            for requirement in path["requirements"]:
                if not isinstance(requirement, dict):
                    continue
                evidence = requirement.get("evidence")
                if not isinstance(evidence, list):
                    continue
                if len(evidence) <= 1:
                    atomic.append(requirement)
                    continue
                for index, reference in enumerate(evidence, start=1):
                    item = deepcopy(requirement)
                    item["item_id"] = f"{requirement.get('item_id', 'item')}_{index}"
                    item["evidence"] = [reference]
                    if isinstance(reference, dict) and isinstance(
                        reference.get("quote"), str
                    ):
                        item["statement"] = reference["quote"]
                    atomic.append(item)
            path["requirements"] = atomic


def _statement_dedup_key(statement: str) -> str:
    lowered = " ".join(statement.casefold().split())
    age_and_license = re.search(
        r"\b(?:at least\s+)?(\d+)\s+years? of age\b.*"
        r"\b(?:valid )?driver[’']s license\b",
        lowered,
    )
    if age_and_license:
        return f"age-and-license:{age_and_license.group(1)}"
    if "english" in lowered and all(
        term in lowered for term in ("read", "write", "speak", "understand")
    ):
        return "language:english:read-write-speak-understand"
    experience = re.search(
        r"\b(\d+)\s+years?\s+of\s+([a-z-]+(?:\s+[a-z-]+){0,3})\s+experience\b",
        lowered,
    )
    if experience:
        return f"experience:{experience.group(1)}:{experience.group(2)}"
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _merge_simple_groups_by_priority(groups: list[Any]) -> list[Any]:
    """Present ordinary AND requirements together instead of as separate groups."""

    combined: dict[str, dict[str, Any]] = {}
    result: list[Any] = []
    for group in groups:
        if (
            not isinstance(group, dict)
            or not isinstance(group.get("paths"), list)
            or len(group["paths"]) != 1
            or not isinstance(group.get("priority"), str)
        ):
            result.append(group)
            continue
        priority = group["priority"]
        target = combined.get(priority)
        if target is None:
            target = {
                "group_id": f"combined_{priority}_requirements",
                "priority": priority,
                "paths": [
                    {
                        "path_id": f"combined_{priority}_path",
                        "requirements": [],
                    }
                ],
            }
            combined[priority] = target
            result.append(target)
        target["paths"][0]["requirements"].extend(
            group["paths"][0]["requirements"]
        )
    return result


def _separate_location_conditional_requirements(
    groups: list[Any],
) -> list[Any]:
    """Keep location-dependent rules out of the universal required list."""

    conditional: list[dict[str, Any]] = []
    retained_groups: list[Any] = []
    for group in groups:
        if (
            not isinstance(group, dict)
            or not isinstance(group.get("paths"), list)
            or len(group["paths"]) != 1
        ):
            retained_groups.append(group)
            continue
        path = group["paths"][0]
        requirements = path.get("requirements")
        if not isinstance(requirements, list):
            retained_groups.append(group)
            continue
        retained = []
        for requirement in requirements:
            if isinstance(requirement, dict) and _is_location_conditional(
                _evidence_text(requirement)
            ):
                conditional.append(requirement)
            else:
                retained.append(requirement)
        path["requirements"] = retained
        if retained:
            retained_groups.append(group)
    if conditional:
        retained_groups.append(
            {
                "group_id": "conditional_location_requirements",
                "priority": "required",
                "paths": [
                    {
                        "path_id": "location_applicability_path",
                        "requirements": conditional,
                    }
                ],
            }
        )
    return retained_groups


def _is_location_conditional(statement: str) -> bool:
    lowered = " ".join(statement.casefold().split())
    if "state-specific requirements related to access dmv/title" in lowered:
        return True
    states = (
        "alabama",
        "alaska",
        "arizona",
        "arkansas",
        "california",
        "colorado",
        "connecticut",
        "delaware",
        "florida",
        "georgia",
        "hawaii",
        "idaho",
        "illinois",
        "indiana",
        "iowa",
        "kansas",
        "kentucky",
        "louisiana",
        "maine",
        "maryland",
        "massachusetts",
        "michigan",
        "minnesota",
        "mississippi",
        "missouri",
        "montana",
        "nebraska",
        "nevada",
        "new hampshire",
        "new jersey",
        "new mexico",
        "new york",
        "north carolina",
        "north dakota",
        "ohio",
        "oklahoma",
        "oregon",
        "pennsylvania",
        "rhode island",
        "south carolina",
        "south dakota",
        "tennessee",
        "texas",
        "utah",
        "vermont",
        "virginia",
        "washington",
        "west virginia",
        "wisconsin",
        "wyoming",
    )
    return "employees must" in lowered and any(
        state in lowered for state in states
    )


def _is_boilerplate(statement: str) -> bool:
    lowered = " ".join(statement.casefold().split()).strip(" :.-")
    if lowered in {
        "legal",
        "legal stuff",
        "company information",
        "general qualifications and requirements",
        "qualifications",
        "required qualifications",
        "preferred qualifications",
        "minimum qualifications",
        "work location",
        "additional work locations",
        "employment type",
        "skills",
        "experience",
        "education",
        "certifications",
    }:
        return True
    if "$" in statement and any(
        term in lowered
        for term in ("pay", "earn", "increase", "compensation", "progress", "/hr")
    ):
        return True
    return any(
        phrase in lowered
        for phrase in (
            "not designed to contain a comprehensive listing",
            "duties, responsibilities, and activities may change",
            "equal employment opportunity employer",
            "all applicants receive consideration for employment",
            "prohibits harassment of applicants or employees",
            "reasonable accommodations may be granted",
            "for further details, candidates can review",
            "unlock your earning potential",
            "build an exciting career",
            "fastest-growing used automotive retailer",
            "fastest growing used automotive retailer",
            "significant growth opportunities based on performance",
            "benefits + perks",
            "health & wellness",
            "education support:",
            "professional development:",
            "we continually invest in our team members",
            "performance-based careers not jobs",
            "higher pay rates sooner",
            "performance won't go unnoticed",
            "performance won’t go unnoticed",
            "wellness program",
            "health insurance",
            "dental",
            "vision",
            "401(k)",
            "paid time off",
            "tuition reimbursement",
            "employee stock purchase",
            "student loan repayment",
            "advancement opportunities:",
            "studies have shown that",
            "think you’ve got what it takes",
            "think you've got what it takes",
            "please check with your recruiter",
            "stock options for all regular employees",
            "this posting is for an existing vacancy",
            "uses ai tools in its recruiting process",
            "bonus amounts and eligibility",
            "your base salary will be determined",
            "eligible for equity and benefits",
            "eligible for benefits and equity",
            "comprehensive benefits package",
            "medical, dental, vision",
            "paid healthcare premiums",
            "retirement savings",
            "employee benefits",
            "committed to attracting, retaining, and developing",
            "hires and promotes people on the basis",
            "workplace that fosters trust, equality, and teamwork",
            "delivers technology solutions and mission services",
            "experts extract the power of technology",
            "we operate across ",
        )
    ) or lowered.startswith(
        (
            "pay range:",
            "starting pay:",
            "compensation:",
            "work location:",
            "additional work locations:",
            "employment type:",
            "required for certain job profiles:",
        )
    )


def _collapse_unproven_alternative_paths(group: Any) -> None:
    if not isinstance(group, dict) or not isinstance(group.get("paths"), list):
        return
    paths = group["paths"]
    if len(paths) < 2 or _has_explicit_alternative_language(paths):
        return
    requirements = [
        requirement
        for path in paths
        if isinstance(path, dict) and isinstance(path.get("requirements"), list)
        for requirement in path["requirements"]
    ]
    if requirements:
        group["paths"] = [
            {"path_id": "combined_required_path", "requirements": requirements}
        ]


def _has_explicit_alternative_language(paths: list[Any]) -> bool:
    path_texts = [
        " ".join(
            _evidence_text(requirement)
            for requirement in path.get("requirements", [])
            if isinstance(requirement, dict)
        ).strip()
        for path in paths
        if isinstance(path, dict) and isinstance(path.get("requirements"), list)
    ]
    if len(path_texts) != len(paths) or len(path_texts) < 2:
        return False
    # Incidental "or" wording inside ordinary requirements does not prove that
    # the model's separate paths are interchangeable qualification routes.
    return all(
        re.match(r"(?i)^(?:or\b|either\b|option\s+\d+\b|in lieu of\b)", text)
        for text in path_texts[1:]
    ) and bool(
        re.search(
            r"(?i)\b(?:or|either|one of the following|in lieu of)\b",
            path_texts[0],
        )
    )


_REQUIRED_SECTION = re.compile(
    r"(?i)\b(?:minimum|required|basic|key|general) qualifications?\b|"
    r"\bwhat (?:we need to see|you(?:'|’)ll need|you(?:'|’)ll bring)\b|"
    r"\bexperience,? education,? skills,? abilities\b"
)
_PREFERRED_SECTION = re.compile(
    r"(?i)\b(?:preferred qualifications?|ways to stand out|bonus points?|"
    r"nice to have|desired qualifications?)\b"
)
_PREFERRED_WORDING = re.compile(
    r"(?i)\b(?:preferred|desirable|desired|a plus|bonus|nice to have)\b"
)
_REQUIRED_WORDING = re.compile(
    r"(?i)\b(?:required|requires?|must|minimum of|at least)\b"
)


def _apply_source_priorities(groups: list[Any], source_content: str) -> list[Any]:
    """Use the nearest source heading to preserve required versus preferred."""

    headings: list[tuple[int, str]] = []
    for match in re.finditer(r"(?m)^\s*([^\r\n]{1,100})\s*$", source_content):
        line = match.group(1).strip(" :")
        if _PREFERRED_SECTION.search(line):
            headings.append((match.start(), "preferred"))
        elif _REQUIRED_SECTION.search(line):
            headings.append((match.start(), "required"))

    rebuilt: list[Any] = []
    for group_index, group in enumerate(groups, start=1):
        if not isinstance(group, dict):
            rebuilt.append(group)
            continue
        by_priority: dict[str, list[dict[str, Any]]] = {
            "required": [],
            "preferred": [],
        }
        for requirement in _requirements(group):
            statement = _evidence_text(requirement)
            priority = _source_priority(requirement, statement, headings)
            by_priority[priority].append(requirement)
        nonempty = [(key, value) for key, value in by_priority.items() if value]
        if len(nonempty) == 1:
            group["priority"] = nonempty[0][0]
            rebuilt.append(group)
            continue
        for priority, requirements in nonempty:
            rebuilt.append(
                {
                    "group_id": f"source_{priority}_{group_index}",
                    "priority": priority,
                    "paths": [
                        {
                            "path_id": f"source_{priority}_{group_index}_path",
                            "requirements": requirements,
                        }
                    ],
                }
            )
    return rebuilt


def _source_priority(
    requirement: dict[str, Any],
    statement: str,
    headings: list[tuple[int, str]],
) -> str:
    if _REQUIRED_WORDING.search(statement):
        return "required"
    if _PREFERRED_WORDING.search(statement):
        return "preferred"
    evidence = requirement.get("evidence")
    starts = (
        [
            item.get("start")
            for item in evidence
            if isinstance(item, dict) and isinstance(item.get("start"), int)
        ]
        if isinstance(evidence, list)
        else []
    )
    if starts:
        preceding = [priority for offset, priority in headings if offset <= min(starts)]
        if preceding:
            return preceding[-1]
    return "required"
