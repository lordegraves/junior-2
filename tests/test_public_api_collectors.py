from unittest.mock import patch

from junior.collectors.contracts import CollectorSource
from junior.collectors.public_api import SmartRecruitersCollector, USAJobsCollector


def test_smartrecruiters_maps_location_remote_and_public_url() -> None:
    source = CollectorSource(
        "canonical",
        "Canonical",
        "smartrecruiters",
        {
            "source_url": "https://api.example/jobs",
            "company_identifier": "Canonical",
        },
    )
    payload = {
        "totalFound": 1,
        "content": [
            {
                "id": "123",
                "name": "Linux Platform Engineer",
                "location": {"fullLocation": "Remote, US", "remote": True},
                "experienceLevel": {"label": "Senior"},
            }
        ],
    }

    with patch("junior.collectors.public_api._get_json", return_value=payload):
        jobs = SmartRecruitersCollector().collect(source)

    assert jobs[0].posting_url.endswith("/123-linux-platform-engineer")
    assert jobs[0].remote_status == "Remote"
    assert jobs[0].description == "Senior"


def test_usajobs_maps_qualification_evidence_and_paginates() -> None:
    source = CollectorSource(
        "federal", "Federal", "usajobs", {"query_params": {"Keyword": "Linux"}}
    )
    payload = {
        "SearchResult": {
            "UserArea": {"NumberOfPages": "1"},
            "SearchResultItems": [
                {
                    "MatchedObjectDescriptor": {
                        "PositionID": "FED-1",
                        "PositionTitle": "Systems Engineer",
                        "PositionURI": "https://usajobs.example/FED-1",
                        "PositionLocation": [{"LocationName": "Remote"}],
                        "QualificationSummary": "Five years of experience.",
                        "UserArea": {
                            "Details": {"SecurityClearance": "Secret"}
                        },
                    }
                }
            ],
        }
    }

    with (
        patch.dict(
            "os.environ",
            {
                "USAJOBS_USER_AGENT": "candidate@example.com",
                "USAJOBS_AUTHORIZATION_KEY": "secret",
            },
        ),
        patch("junior.collectors.public_api._get_json", return_value=payload),
    ):
        jobs = USAJobsCollector().collect(source)

    assert jobs[0].location == "Remote"
    assert "SecurityClearance: Secret" in (jobs[0].description or "")


def test_usajobs_requires_credentials() -> None:
    source = CollectorSource("federal", "Federal", "usajobs", {})
    with patch.dict("os.environ", {}, clear=True):
        try:
            USAJobsCollector().collect(source)
        except ValueError as error:
            assert "USAJOBS_USER_AGENT" in str(error)
        else:
            raise AssertionError("missing credentials must fail safely")
