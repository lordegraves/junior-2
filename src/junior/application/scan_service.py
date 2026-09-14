"""One native scan transaction independent of the desktop UI."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from junior.application.review_workspace import (
    QualificationGroupReview,
    QualificationPathReview,
    RequirementReview,
    ReviewValidationState,
    ReviewWorkspaceResult,
)
from junior.application.role_discovery import approved_role_mappings
from junior.collectors.contracts import CollectedJob, CollectorSource
from junior.collectors.registry import CollectorRegistry
from junior.domain.documents import DocumentKind, EvidenceReference, SourceDocument
from junior.domain.lifecycle import JobPosting
from junior.domain.qualifications import RequirementPriority
from junior.infrastructure.application_database import (
    get_candidate_profile,
    list_history_records,
)
from junior.scoring.job_evaluator import Recommendation, evaluate_job
from junior.scoring.qualification_shadow_matcher import match_review_results

QualificationRunner = Callable[..., object]
ResumeRunner = Callable[..., object]


@dataclass(frozen=True, slots=True)
class ScanSummary:
    run_id: int
    companies_scanned: int
    jobs_collected: int
    jobs_new: int
    jobs_changed: int
    errors: int
    top_matches: int = 0
    review_needed: int = 0
    omitted: int = 0


class ScanService:
    def __init__(
        self,
        database_path: str | Path,
        registry: CollectorRegistry,
        qualification_runner: QualificationRunner | None = None,
        resume_runner: ResumeRunner | None = None,
        company_keys: tuple[str, ...] | None = None,
    ) -> None:
        self._database_path = Path(database_path)
        self._registry = registry
        self._qualification_runner = qualification_runner
        self._resume_runner = resume_runner
        self._company_keys = company_keys

    def run(self) -> ScanSummary:
        sources = self._sources()
        profile = get_candidate_profile(self._database_path)
        resume_path = profile.resume_normalized_text_path if profile else None
        resume_text = _resume_text(resume_path)
        resume_review = None
        if profile is not None and resume_text and self._resume_runner is not None:
            resume_review = self._interpret_resume(
                profile.profile_id, resume_path, resume_text
            )
        history_records = list_history_records(self._database_path)
        run_id = self._begin_run(len(sources), profile.profile_id if profile else None)
        scanned = collected = new = changed = errors = top = review = omitted = 0
        for source in sources:
            try:
                collector = self._registry.collector_for(source.source_type)
                jobs = collector.collect(source)
                scanned += 1
                collected += len(jobs)
                for job in jobs:
                    state, posting_id = self._store_job(source, job, run_id)
                    new += state == "new"
                    changed += state == "changed"
                    recommendation = self._evaluate_job(
                        source,
                        job,
                        posting_id,
                        run_id,
                        profile,
                        resume_text,
                        history_records,
                    )
                    if self._qualification_runner is not None and state in {
                        "new",
                        "changed",
                    }:
                        self._interpret_job(
                            source, job, posting_id, run_id, resume_review
                        )
                    top += recommendation is Recommendation.TOP_MATCH
                    review += recommendation is Recommendation.REVIEW_NEEDED
                    omitted += recommendation is Recommendation.OMIT
            except Exception as error:  # one source must not abort the whole scan
                errors += 1
                self._record_error(run_id, source, error)
        self._finish_run(
            run_id, scanned, collected, new, changed, errors, top, review, omitted
        )
        return ScanSummary(
            run_id, scanned, collected, new, changed, errors, top, review, omitted
        )

    def _sources(self) -> tuple[CollectorSource, ...]:
        with sqlite3.connect(self._database_path) as connection:
            connection.row_factory = sqlite3.Row
            query = """SELECT company_key, name, source_type, source_slug, source_url,
                              source_settings_json
                       FROM companies WHERE enabled = 1"""
            parameters: tuple[str, ...] = ()
            if self._company_keys:
                placeholders = ",".join("?" for _ in self._company_keys)
                query += f" AND company_key IN ({placeholders})"
                parameters = self._company_keys
            rows = connection.execute(query + " ORDER BY name", parameters).fetchall()
        return tuple(
            CollectorSource(
                company_id=row["company_key"],
                company_name=row["name"],
                source_type=row["source_type"],
                source_settings=_source_settings(row),
            )
            for row in rows
        )

    def _begin_run(self, requested: int, profile_id: str | None) -> int:
        with sqlite3.connect(self._database_path) as connection:
            cursor = connection.execute(
                """INSERT INTO scan_runs (
                       generated_at, started_at, profile_id, status,
                       companies_requested,
                       companies_enabled
                   ) VALUES (?, ?, ?, 'running', ?, ?)""",
                (_now(), _now(), profile_id, requested, requested),
            )
            return int(cursor.lastrowid)

    def _store_job(
        self, source: CollectorSource, job: CollectedJob, run_id: int
    ) -> tuple[str, int]:
        content = "\n".join(
            filter(
                None,
                (
                    job.title,
                    job.location,
                    job.description,
                    job.posting_url,
                    job.remote_status,
                    job.salary_text,
                ),
            )
        )
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        canonical_key = f"{source.company_id}:{job.source_job_id}"
        now = _now()
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                """SELECT id, content_hash FROM job_postings
                   WHERE canonical_key = ?""",
                (canonical_key,),
            ).fetchone()
            if row is None:
                cursor = connection.execute(
                    """INSERT INTO job_postings (
                           company_key, source_type, source_job_id, source_url,
                           title, location, description, remote_status, salary_text,
                           canonical_key, content_hash,
                           first_seen_at, last_seen_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        source.company_id,
                        source.source_type,
                        job.source_job_id,
                        job.posting_url,
                        job.title,
                        job.location,
                        job.description,
                        job.remote_status,
                        job.salary_text,
                        canonical_key,
                        content_hash,
                        now,
                        now,
                    ),
                )
                posting_id = int(cursor.lastrowid)
                state = "new"
            else:
                posting_id = int(row[0])
                state = "seen" if row[1] == content_hash else "changed"
                connection.execute(
                    """UPDATE job_postings SET source_url = ?, title = ?, location = ?,
                              description = ?, remote_status = ?, salary_text = ?,
                              content_hash = ?, last_seen_at = ?,
                              last_changed_at = CASE WHEN content_hash <> ? THEN ?
                                                    ELSE last_changed_at END,
                              is_active = 1, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (
                        job.posting_url,
                        job.title,
                        job.location,
                        job.description,
                        job.remote_status,
                        job.salary_text,
                        content_hash,
                        now,
                        content_hash,
                        now,
                        posting_id,
                    ),
                )
            connection.execute(
                """INSERT INTO job_seen_events (
                       job_posting_id, scan_run_id, event_type
                   ) VALUES (?, ?, ?)""",
                (posting_id, run_id, state),
            )
        return state, posting_id

    def _evaluate_job(
        self,
        source: CollectorSource,
        job: CollectedJob,
        posting_id: int,
        run_id: int,
        profile,
        resume_text: str | None,
        history_records,
    ) -> Recommendation:
        effective_profile = profile
        if profile is not None:
            approved = approved_role_mappings(
                self._database_path, profile.profile_id, source.company_id
            )
            if approved:
                effective_profile = replace(
                    profile,
                    target_roles=tuple(
                        dict.fromkeys((*profile.target_roles, *approved))
                    ),
                )
        evaluation = evaluate_job(
            JobPosting(
                source.company_id,
                source.company_name,
                source.source_type,
                job.posting_url,
                job.title,
                job.location,
                job.description,
                job.source_job_id,
                job.remote_status,
                job.salary_text,
            ),
            effective_profile,
            resume_text,
            history_records,
        )
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """INSERT OR REPLACE INTO job_evaluations (
                       job_posting_id, scan_run_id, score, policy_score,
                       location_status, recommendation, recommended_action,
                       hiring_probability, risk_flags_json,
                       compensation_label, compensation_range, resume_match_label,
                       evidence_json, gaps_json, reasons_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    posting_id,
                    run_id,
                    evaluation.score,
                    evaluation.policy_score,
                    evaluation.location_status,
                    evaluation.recommendation.value,
                    evaluation.recommended_action,
                    evaluation.hiring_probability,
                    json.dumps(evaluation.risk_flags),
                    evaluation.compensation_label,
                    evaluation.compensation_range,
                    evaluation.resume_match_label,
                    json.dumps(evaluation.evidence),
                    json.dumps(evaluation.gaps),
                    json.dumps(evaluation.reasons),
                ),
            )
        return evaluation.recommendation

    def _interpret_job(
        self,
        source: CollectorSource,
        job: CollectedJob,
        posting_id: int,
        run_id: int,
        resume_review: ReviewWorkspaceResult | None,
    ) -> None:
        try:
            result = self._qualification_runner(
                title=job.title,
                company=source.company_name,
                content=job.description or job.title,
                source_uri=job.posting_url,
            )
            payload = _serialize_review(result)
            status = "validated"
            section_state = str(getattr(result, "section_state", "unknown"))
            model_id = _review_model_id(result)
            shadow_payload = (
                _serialize_shadow_match(match_review_results(result, resume_review))
                if resume_review is not None
                else None
            )
            error_message = None
        except Exception as error:
            payload = None
            status = "failed"
            section_state = None
            model_id = None
            shadow_payload = None
            error_message = str(error)
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """INSERT OR REPLACE INTO job_interpretations (
                       job_posting_id, scan_run_id, model_id, status,
                       section_state, interpretation_json, shadow_match_json,
                       error_message
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    posting_id,
                    run_id,
                    model_id,
                    status,
                    section_state,
                    json.dumps(payload) if payload is not None else None,
                    json.dumps(shadow_payload) if shadow_payload is not None else None,
                    error_message,
                ),
            )

    def _interpret_resume(
        self, profile_id: str, resume_path: str | None, resume_text: str
    ) -> ReviewWorkspaceResult | None:
        content_hash = hashlib.sha256(resume_text.encode()).hexdigest()
        with sqlite3.connect(self._database_path) as connection:
            existing = connection.execute(
                """SELECT status, interpretation_json FROM resume_interpretations
                   WHERE profile_id = ? AND content_hash = ?""",
                (profile_id, content_hash),
            ).fetchone()
        if existing is not None and existing[0] == "validated" and existing[1]:
            return _deserialize_review(json.loads(existing[1]), document_kind="resume")
        try:
            result = self._resume_runner(
                filename=Path(resume_path or "resume.txt").name,
                content=resume_text,
            )
            payload = _serialize_review(result)
            status = "validated"
            model_id = _review_model_id(result)
            error_message = None
        except Exception as error:
            payload = None
            status = "failed"
            model_id = None
            error_message = str(error)
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """INSERT OR REPLACE INTO resume_interpretations (
                       profile_id, content_hash, model_id, status,
                       interpretation_json, error_message
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    profile_id,
                    content_hash,
                    model_id,
                    status,
                    json.dumps(payload) if payload is not None else None,
                    error_message,
                ),
            )
        return result if status == "validated" else None

    def _record_error(
        self, run_id: int, source: CollectorSource, error: Exception
    ) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """INSERT INTO scan_errors (
                       scan_run_id, company_key, source_type, error_type, error_message
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    run_id,
                    source.company_id,
                    source.source_type,
                    type(error).__name__,
                    str(error),
                ),
            )

    def _finish_run(
        self,
        run_id: int,
        scanned: int,
        collected: int,
        new: int,
        changed: int,
        errors: int,
        top: int,
        review: int,
        omitted: int,
    ) -> None:
        status = "completed" if errors == 0 else "completed_with_errors"
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """UPDATE scan_runs SET finished_at = ?, status = ?,
                          companies_scanned = ?, jobs_found = ?, jobs_collected = ?,
                          actionable_jobs_stored = ?, jobs_new = ?, jobs_changed = ?,
                          collector_errors = ?, errors_count = ?
                          , top_matches_count = ?, review_needed_count = ?,
                          jobs_not_actionable = ?
                   WHERE id = ?""",
                (
                    _now(),
                    status,
                    scanned,
                    collected,
                    collected,
                    collected,
                    new,
                    changed,
                    errors,
                    errors,
                    top,
                    review,
                    omitted,
                    run_id,
                ),
            )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _source_settings(row: sqlite3.Row) -> dict[str, object]:
    settings = json.loads(row["source_settings_json"] or "{}")
    settings["source_slug"] = row["source_slug"]
    settings["source_url"] = row["source_url"]
    return settings


def _resume_text(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def _serialize_review(result: object) -> dict[str, object]:
    groups = []
    for group in getattr(result, "groups", ()):
        groups.append(
            {
                "label": group.label,
                "priority": str(group.priority),
                "paths": [
                    {
                        "label": path.label,
                        "requirements": [
                            {
                                "label": requirement.label,
                                "category": requirement.category,
                                "state": requirement.state,
                                "confidence": requirement.confidence,
                                "normalized_value": requirement.normalized_value,
                                "evidence": [
                                    {
                                        "quote": evidence.quote,
                                        "start": evidence.start,
                                        "end": evidence.end,
                                    }
                                    for evidence in requirement.evidence
                                ],
                            }
                            for requirement in path.requirements
                        ],
                    }
                    for path in group.paths
                ],
            }
        )
    return {
        "section_state": getattr(result, "section_state", "unknown"),
        "validation_state": str(getattr(result, "validation_state", "unknown")),
        "groups": groups,
    }


def _review_model_id(result: object) -> str | None:
    for key, value in getattr(result, "technical_details", ()):
        if key == "Mode":
            return str(value).rsplit("—", 1)[-1].strip()
    return None


def _deserialize_review(
    payload: dict[str, object], *, document_kind: str
) -> ReviewWorkspaceResult:
    source = SourceDocument(
        "cached-review", DocumentKind.RESUME, "Cached validated interpretation"
    )
    groups = []
    for group in payload.get("groups", []):
        paths = []
        for path in group["paths"]:
            requirements = []
            for requirement in path["requirements"]:
                evidence = tuple(
                    EvidenceReference(
                        source.document_id,
                        item["quote"],
                        int(item["start"]),
                        int(item["end"]),
                    )
                    for item in requirement["evidence"]
                )
                requirements.append(
                    RequirementReview(
                        requirement["label"],
                        requirement["category"],
                        requirement["state"],
                        float(requirement["confidence"]),
                        evidence,
                        requirement.get("normalized_value"),
                    )
                )
            paths.append(QualificationPathReview(path["label"], tuple(requirements)))
        priority = str(group["priority"]).rsplit(".", 1)[-1].casefold()
        groups.append(
            QualificationGroupReview(
                group["label"], RequirementPriority(priority), tuple(paths)
            )
        )
    return ReviewWorkspaceResult(
        fixture_id="cached-review",
        title="Cached resume",
        company="Resume",
        source_document=source,
        section_state=str(payload.get("section_state", "unknown")),
        groups=tuple(groups),
        validation_state=ReviewValidationState.VALIDATED,
        validation_message="Loaded from validated local cache.",
        engine_message="",
        rejected_claims=(),
        technical_details=(),
        document_kind=document_kind,
    )


def _serialize_shadow_match(result) -> dict[str, object]:
    return {
        "required_state": result.required_state().value,
        "counts": {
            state.value: result.count(state) for state in type(result.required_state())
        },
        "requirements": [
            {
                "job_requirement": match.requirement.label,
                "group": match.group_label,
                "path": match.path_label,
                "priority": match.priority,
                "state": match.state.value,
                "resume_evidence": [item.label for item in match.resume_evidence],
                "reason": match.reason,
            }
            for match in result.matches
        ],
    }
