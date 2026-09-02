import sqlite3

from junior.infrastructure.application_database import (
    initialize_database,
    list_report_exports,
)
from junior.reporting.scan_report import render_html_report, render_markdown_report


def test_reports_render_persisted_evaluations(tmp_path) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO job_postings (
                   company_key, source_type, source_url, title,
                   canonical_key, content_hash
               ) VALUES ('acme', 'test', 'https://job', 'Platform Engineer',
                         'acme:1', 'hash')"""
        )
        posting_id = connection.execute("SELECT id FROM job_postings").fetchone()[0]
        connection.execute("""INSERT INTO scan_runs (status) VALUES ('completed')""")
        run_id = connection.execute("SELECT id FROM scan_runs").fetchone()[0]
        connection.execute(
            """INSERT INTO job_evaluations (
                   job_posting_id, scan_run_id, score, recommendation,
                   compensation_label, compensation_range,
                   resume_match_label, reasons_json
               ) VALUES (?, ?, 90, 'top_match', 'Meets floor', '$150,000',
                         'Very Strong', '["Strong evidence"]')""",
            (posting_id, run_id),
        )

    markdown = render_markdown_report(database)
    assert "Top matches: 1" in markdown
    assert "## Summary" in markdown
    assert "## Top matches" in markdown
    assert "Applications tracked: 0" in markdown
    assert "Acme" not in markdown
    assert "acme — Platform Engineer" in markdown
    assert "Strong evidence" in markdown
    assert "Legacy policy score: 0" in markdown
    assert "Location: unknown" in markdown
    html = render_html_report(database)
    assert "<!doctype html>" in html
    assert "Platform Engineer" in html

    destination = tmp_path / "saved-report.html"
    from junior.reporting.scan_report import save_report

    save_report(database, destination)
    assert list_report_exports(database)[0]["path"] == str(destination.resolve())
