from junior.collectors.activate import ActivateCollector
from junior.collectors.contracts import CollectorSource


def test_activate_paginates_and_extracts_tracking_fields(monkeypatch) -> None:
    calls = []

    def fake_json(url, parameters, headers):
        calls.append(parameters["jtStartIndex"])
        identifier = str(len(calls))
        return {
            "Records": [
                {
                    "ID": identifier,
                    "TrackingObject": {
                        "TitleJson": "Platform Engineer",
                        "ReferenceNumberJson": f"REQ-{identifier}",
                        "LocationNamesJson": ["Boston, MA"],
                        "DepartmentNameJson": "Engineering",
                    },
                }
            ],
            "TotalRecordCount": 2,
        }

    monkeypatch.setattr("junior.collectors.activate._get_json", fake_json)
    jobs = ActivateCollector().collect(
        CollectorSource(
            "lab",
            "Lab",
            "activate",
            {
                "source_url": "https://lab.example/api",
                "source_base_url": "https://lab.example",
                "page_size": 1,
            },
        )
    )
    assert calls == [0, 1]
    assert len(jobs) == 2
    assert jobs[0].location == "Boston, MA"
    assert jobs[0].posting_url.endswith("/platform-engineer/1")
    assert jobs[0].description == "REQ-1 | Engineering"
