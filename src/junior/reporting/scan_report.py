"""Portable Markdown and HTML reports backed by durable scan evaluations."""

from __future__ import annotations

import json
import sqlite3
from html import escape
from pathlib import Path

from junior.infrastructure.application_database import list_job_evaluations


def render_markdown_report(database_path: str | Path) -> str:
    rows = list_job_evaluations(database_path)
    counts = _counts(rows)
    context = _report_context(database_path)
    lines = [
        "# Junior scan report",
        "",
        "## Summary",
        "",
        f"- Top matches: {counts.get('top_match', 0)}",
        f"- Review needed: {counts.get('review_needed', 0)}",
        f"- Omitted: {counts.get('omit', 0)}",
        f"- Already tracked: {counts.get('track_status', 0)}",
        f"- Applications tracked: {context['applications']}",
        f"- Follow-ups due: {context['follow_ups_due']}",
        f"- History records used: {context['history_included']}",
        f"- Collector errors: {len(context['errors'])}",
        "",
    ]
    if context["errors"]:
        lines.extend(("## Collector errors", ""))
        lines.extend(
            f"- {error['company_key'] or 'Unknown source'}: "
            f"{error['error_type']} — {error['error_message']}"
            for error in context["errors"]
        )
        lines.append("")
    sections = (
        ("Top matches", "top_match"),
        ("Review needed", "review_needed"),
        ("Tracked applications", "track_status"),
        ("Omitted audit", "omit"),
    )
    for title, recommendation in sections:
        section_rows = tuple(
            row for row in rows if row["recommendation"] == recommendation
        )
        if not section_rows:
            continue
        lines.extend((f"## {title}", ""))
        for row in section_rows:
            lines.extend(
                (
                    f"### {row['company_key']} — {row['title']}",
                    "",
                    f"- Recommendation: {row['recommendation']}",
                    f"- Action: {row['recommended_action']}",
                    f"- Hiring probability: {row['hiring_probability']}",
                    f"- Score: {row['score']}",
                    f"- Legacy policy score: {row['policy_score']}",
                    f"- Location: {row['location_status']}",
                    f"- Compensation: {row['compensation_label']}",
                    f"- Résumé match: {row['resume_match_label']}",
                )
            )
            reasons = json.loads(str(row["reasons_json"]) or "[]")
            if reasons:
                lines.append("- Reasons:")
                lines.extend(f"  - {reason}" for reason in reasons)
            lines.append("")
    return "\n".join(lines)


def render_html_report(database_path: str | Path) -> str:
    markdown = render_markdown_report(database_path)
    body = "\n".join(_html_line(line) for line in markdown.splitlines())
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Junior scan report</title>"
        "<style>body{font:15px system-ui;margin:32px;max-width:1100px}"
        "h2{border-bottom:1px solid #ccd;padding-bottom:6px}"
        "li{margin:4px 0}</style></head><body>"
        f"{body}</body></html>"
    )


def save_report(database_path: str | Path, destination: str | Path) -> Path:
    path = Path(destination)
    content = (
        render_html_report(database_path)
        if path.suffix.casefold() in {".html", ".htm"}
        else render_markdown_report(database_path)
    )
    path.write_text(content, encoding="utf-8")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO report_exports(path, format) VALUES (?, ?)",
            (str(path.resolve()), path.suffix.casefold().lstrip(".") or "markdown"),
        )
    return path


def _counts(rows: tuple[dict[str, object], ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row["recommendation"])
        counts[key] = counts.get(key, 0) + 1
    return counts


def _report_context(database_path: str | Path) -> dict[str, object]:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        applications = connection.execute(
            "SELECT follow_up_on FROM application_tracker"
        ).fetchall()
        history_included = connection.execute(
            "SELECT COUNT(*) FROM job_history WHERE include_in_job_radar = 1"
        ).fetchone()[0]
        errors = connection.execute(
            """SELECT company_key, error_type, error_message FROM scan_errors
               ORDER BY id DESC LIMIT 100"""
        ).fetchall()
    from datetime import date

    today = date.today().isoformat()
    return {
        "applications": len(applications),
        "follow_ups_due": sum(
            bool(row["follow_up_on"] and str(row["follow_up_on"]) <= today)
            for row in applications
        ),
        "history_included": int(history_included),
        "errors": tuple(dict(row) for row in errors),
    }


def _html_line(line: str) -> str:
    text = escape(line)
    if line.startswith("### "):
        return f"<h3>{escape(line[4:])}</h3>"
    if line.startswith("## "):
        return f"<h2>{escape(line[3:])}</h2>"
    if line.startswith("# "):
        return f"<h1>{escape(line[2:])}</h1>"
    if line.startswith("  - "):
        return f"<li style='margin-left:2em'>{escape(line[4:])}</li>"
    if line.startswith("- "):
        return f"<li>{escape(line[2:])}</li>"
    return f"<p>{text}</p>" if line else ""
