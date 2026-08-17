from dataclasses import dataclass

import pytest

from junior.collectors.contracts import CollectedJob, CollectorSource
from junior.collectors.registry import CollectorRegistry


@dataclass
class StubCollector:
    source_type: str

    def collect(self, source: CollectorSource) -> tuple[CollectedJob, ...]:
        return ()


def test_registry_returns_migrated_collector_by_source_type() -> None:
    greenhouse = StubCollector("greenhouse")
    registry = CollectorRegistry({"greenhouse": greenhouse})

    assert registry.collector_for("greenhouse") is greenhouse


def test_registry_rejects_mismatched_source_type() -> None:
    with pytest.raises(ValueError, match="does not match"):
        CollectorRegistry({"lever": StubCollector("greenhouse")})


def test_registry_explains_when_collector_has_not_been_migrated() -> None:
    registry = CollectorRegistry({})

    with pytest.raises(LookupError, match="no collector registered for workday"):
        registry.collector_for("workday")
