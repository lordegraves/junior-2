import zipfile
from pathlib import Path

import pytest

from junior.infrastructure.rc6_raw_scan_importer import (
    RawScanImportError,
    import_rc6_evaluation_sample,
)


def _posting(index: int, description: str) -> str:
    return "\n".join(
        [
            "=" * 80,
            f"Posting {index}",
            f"Company: Company {index}",
            f"Title: Role {index}",
            "Location: Remote",
            "Remote status: Remote",
            "Compensation: Not stated",
            "Source type: synthetic",
            f"Source URL: https://example.invalid/jobs/{index}",
            f"Source job ID: {index}",
            f"Junior job ID: jr-example-{index}",
            "",
            "Job description:",
            description,
            "",
        ]
    )


def _write_export(path: Path, descriptions: list[str]) -> None:
    header = "\n".join(
        [
            "Junior raw scan export",
            "Junior build: RC6 Build 1.25",
            "Generated: 2026-08-17T12:00:00+00:00",
            f"Companies enabled: {len(descriptions)}",
            f"Jobs collected: {len(descriptions)}",
            "",
            "Public posting export.",
            "",
        ]
    )
    content = header + "\n" + "\n".join(
        _posting(index, description)
        for index, description in enumerate(descriptions, start=1)
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("target-scan-raw.txt", content)


def _description(marker: str) -> str:
    return (
        f"{marker}\n"
        "Build reliable infrastructure and support production systems. "
        "Collaborate with engineering teams and document operational practices."
    )


def test_import_selects_diverse_public_postings_without_profile_data(
    tmp_path: Path,
) -> None:
    descriptions = []
    markers = [
        "Public Trust clearance required.",
        "Bachelor's degree or equivalent experience.",
        "Bonus Points: Kubernetes.",
        "Minimum Qualifications: Linux.",
        "General engineering role.",
    ]
    for marker in markers:
        descriptions.extend(_description(marker) for _ in range(5))
    archive = tmp_path / "junior-raw-scan.zip"
    _write_export(archive, descriptions)

    sample = import_rc6_evaluation_sample(archive)

    assert sample.source_build == "RC6 Build 1.25"
    assert sample.jobs_in_export == 25
    assert sample.eligible_jobs == 25
    assert len(sample.postings) == 20
    assert {posting.sample_category for posting in sample.postings} == {
        "clearance or work authorization",
        "alternative qualification path",
        "preferred or bonus qualifications",
        "qualification heading",
        "general posting",
    }


def test_import_excludes_missing_and_tiny_descriptions(tmp_path: Path) -> None:
    archive = tmp_path / "junior-raw-scan.zip"
    _write_export(archive, ["Not provided", "Too short"])

    sample = import_rc6_evaluation_sample(archive)

    assert sample.eligible_jobs == 0
    assert sample.postings == ()


def test_import_rejects_unrecognized_zip_contents(tmp_path: Path) -> None:
    archive = tmp_path / "not-an-export.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("other.txt", "not a raw scan")

    with pytest.raises(RawScanImportError, match="Reports page"):
        import_rc6_evaluation_sample(archive)
