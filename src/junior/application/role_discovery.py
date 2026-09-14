"""Evidence-bounded adjacent-role discovery for one candidate profile."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from junior.infrastructure.application_database import get_candidate_profile

FEEDBACK_STATES = {"relevant", "not_relevant", "different_discipline"}
_STOP_WORDS = {
    "and", "are", "for", "from", "have", "into", "job", "role", "that",
    "the", "their", "this", "through", "using", "with", "work",
}
_GENERIC_TERMS = {
    "administrator", "analyst", "associate", "computer", "engineer", "manager",
    "operator", "specialist", "system", "systems", "technician",
}
_DISCIPLINE_GATES = {
    "rtl": {"rtl", "verilog", "systemverilog", "uvm"},
    "asic": {"asic", "soc", "silicon", "verilog", "systemverilog"},
    "fpga": {"fpga", "vhdl", "verilog", "systemverilog"},
    "software": {"software", "programming", "developer", "python", "java", "c++"},
    "manager": {"managed", "management", "supervised", "leadership", "led"},
}


@dataclass(frozen=True, slots=True)
class RoleSuggestion:
    suggestion_id: int
    profile_id: str
    suggested_title: str
    employer_context: str | None
    explanation: str
    evidence: tuple[str, ...]
    feedback_state: str


def refresh_role_suggestions(
    database_path: str | Path, profile_id: str
) -> tuple[RoleSuggestion, ...]:
    profile = get_candidate_profile(database_path, profile_id)
    if profile is None:
        raise ValueError("The selected profile is no longer available.")
    if not profile.resume_normalized_text_path:
        raise ValueError("Add a résumé before generating role suggestions.")
    try:
        resume = Path(profile.resume_normalized_text_path).read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError("Junior could not read the active résumé.") from error
    resume_terms = _tokens(resume)
    if len(resume_terms) < 3:
        raise ValueError("The résumé does not contain enough readable work evidence.")
    target_titles = {_normalize(title) for title in profile.target_roles}
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT DISTINCT jobs.title, jobs.description, jobs.company_key,
                      companies.name AS employer_name
               FROM job_postings AS jobs
               LEFT JOIN companies ON companies.company_key = jobs.company_key
               WHERE jobs.description IS NOT NULL AND jobs.description != ''
               ORDER BY jobs.last_seen_at DESC LIMIT 500"""
        ).fetchall()
        for suggestion in _catalog_suggestions(
            profile.target_roles, resume, resume_terms
        ):
            connection.execute(
                """INSERT INTO role_discovery_suggestions (
                       profile_id, suggested_title, normalized_title,
                       employer_context, context_key, explanation, evidence_json
                   ) VALUES (?, ?, ?, NULL, 'occupation_catalog', ?, ?)
                   ON CONFLICT(profile_id, normalized_title, context_key) DO UPDATE SET
                       explanation=excluded.explanation,
                       evidence_json=excluded.evidence_json,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    profile_id,
                    suggestion["title"],
                    _normalize(suggestion["title"]),
                    suggestion["explanation"],
                    json.dumps(suggestion["evidence"]),
                ),
            )
        ranked: list[tuple[int, sqlite3.Row, tuple[str, ...]]] = []
        for row in rows:
            title = str(row["title"] or "").strip()
            if not title or _normalize(title) in target_titles:
                continue
            evidence = tuple(sorted(resume_terms & _tokens(row["description"])))[:8]
            if len(evidence) >= 4:
                ranked.append((-len(evidence), row, evidence))
        ranked.sort(key=lambda item: (item[0], str(item[1]["title"]).casefold()))
        for _, row, evidence in ranked[:12]:
            employer = str(row["employer_name"] or row["company_key"])
            title = str(row["title"]).strip()
            connection.execute(
                """INSERT INTO role_discovery_suggestions (
                       profile_id, suggested_title, normalized_title,
                       employer_context, context_key, explanation, evidence_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(profile_id, normalized_title, context_key) DO UPDATE SET
                       explanation=excluded.explanation,
                       evidence_json=excluded.evidence_json,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    profile_id,
                    title,
                    _normalize(title),
                    employer,
                    f"employer:{str(row['company_key']).casefold()}",
                    f"Observed at {employer}; résumé evidence overlaps with the "
                    "posting. Review before approving this role.",
                    json.dumps(evidence),
                ),
            )
    return list_role_suggestions(database_path, profile_id)


def list_role_suggestions(
    database_path: str | Path, profile_id: str
) -> tuple[RoleSuggestion, ...]:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT * FROM role_discovery_suggestions WHERE profile_id = ?
               ORDER BY CASE feedback_state WHEN 'pending' THEN 0 ELSE 1 END,
                        suggested_title COLLATE NOCASE""",
            (profile_id,),
        ).fetchall()
    return tuple(_suggestion(row) for row in rows)


def record_role_feedback(
    database_path: str | Path,
    profile_id: str,
    suggestion_id: int,
    feedback_state: str,
) -> RoleSuggestion:
    if feedback_state not in FEEDBACK_STATES:
        raise ValueError("Choose a supported role-discovery decision.")
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            """UPDATE role_discovery_suggestions SET feedback_state = ?,
                      reviewed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
               WHERE id = ? AND profile_id = ?""",
            (feedback_state, suggestion_id, profile_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("The selected role suggestion is no longer available.")
        row = connection.execute(
            "SELECT * FROM role_discovery_suggestions WHERE id = ?", (suggestion_id,)
        ).fetchone()
    return _suggestion(row)


def approved_role_mappings(
    database_path: str | Path, profile_id: str, employer_key: str | None = None
) -> tuple[str, ...]:
    context = f"employer:{employer_key.casefold()}" if employer_key else "%"
    operator = "=" if employer_key else "LIKE"
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            f"""SELECT suggested_title FROM role_discovery_suggestions
                WHERE profile_id = ? AND feedback_state = 'relevant'
                  AND context_key {operator} ?
                ORDER BY suggested_title COLLATE NOCASE""",
            (profile_id, context),
        ).fetchall()
    return tuple(dict.fromkeys(str(row[0]) for row in rows))


def _tokens(value: object) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9+#.]+", str(value).casefold())
        if len(token) >= 3 and token not in _STOP_WORDS
    }


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _catalog_suggestions(
    target_roles: tuple[str, ...], resume: str, resume_terms: set[str]
) -> tuple[dict[str, object], ...]:
    occupations, titles_by_code, title_codes = _occupation_reference()
    selected_titles = {_normalize(title) for title in target_roles}
    selected_codes: set[str] = set()
    for title in selected_titles:
        selected_codes.update(title_codes.get(title, ()))
    candidates: list[tuple[int, str, str, tuple[str, ...]]] = []
    for code in selected_codes:
        occupation = occupations[code]
        description_evidence = (
            resume_terms & _tokens(occupation["description"]) - _GENERIC_TERMS
        )
        if len(description_evidence) < 2:
            continue
        for title in titles_by_code.get(code, ()):
            normalized = _normalize(title)
            title_evidence = _tokens(title) - _GENERIC_TERMS & resume_terms
            if (
                normalized in selected_titles
                or not title_evidence
                or not _title_is_safe(title, resume)
            ):
                continue
            evidence = tuple(sorted(title_evidence | description_evidence)[:6])
            candidates.append((-len(title_evidence), title, code, evidence))
    candidates.sort(key=lambda item: (item[0], len(item[1]), item[1].casefold()))
    results: list[dict[str, object]] = []
    seen: set[str] = set()
    for _, title, code, evidence in candidates:
        if (normalized := _normalize(title)) in seen:
            continue
        seen.add(normalized)
        results.append(
            {
                "title": title,
                "evidence": evidence,
                "explanation": (
                    f"O*NET groups this title with {occupations[code]['title']}. "
                    f"The résumé contains related evidence: {', '.join(evidence)}. "
                    "Review the discipline before approving it."
                ),
            }
        )
        if len(results) == 8:
            break
    return tuple(results)


def _title_is_safe(title: str, resume: str) -> bool:
    normalized_title = _normalize(title)
    normalized_resume = _normalize(resume)
    return all(
        marker not in normalized_title
        or any(evidence in normalized_resume for evidence in required)
        for marker, required in _DISCIPLINE_GATES.items()
    )


@lru_cache(maxsize=1)
def _occupation_reference() -> tuple[
    dict[str, dict[str, str]], dict[str, list[str]], dict[str, set[str]]
]:
    occupations_payload = json.loads(
        files("junior.reference_data")
        .joinpath("occupations.json")
        .read_text(encoding="utf-8")
    )
    titles_payload = json.loads(
        files("junior.reference_data")
        .joinpath("job_titles.json")
        .read_text(encoding="utf-8")
    )
    occupations = {
        item["code"]: item for item in occupations_payload["occupations"]
    }
    titles_by_code: dict[str, list[str]] = {}
    title_codes: dict[str, set[str]] = {}
    for item in titles_payload["job_titles"]:
        titles_by_code.setdefault(item["code"], []).append(item["job_title"])
        title_codes.setdefault(_normalize(item["job_title"]), set()).add(item["code"])
    for occupation in occupations.values():
        title_codes.setdefault(_normalize(occupation["title"]), set()).add(
            occupation["code"]
        )
    return occupations, titles_by_code, title_codes


def _suggestion(row: sqlite3.Row) -> RoleSuggestion:
    return RoleSuggestion(
        int(row["id"]), str(row["profile_id"]), str(row["suggested_title"]),
        row["employer_context"], str(row["explanation"]),
        tuple(json.loads(row["evidence_json"])), str(row["feedback_state"]),
    )
