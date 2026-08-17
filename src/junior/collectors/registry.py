"""Register migrated collectors without coupling callers to source-specific code."""

from collections.abc import Mapping

from junior.collectors.contracts import JobCollector


class CollectorRegistry:
    def __init__(self, collectors: Mapping[str, JobCollector]) -> None:
        self._collectors = dict(collectors)
        for source_type, collector in self._collectors.items():
            if not source_type.strip():
                raise ValueError("collector source type is required")
            if source_type != collector.source_type:
                raise ValueError("registered source type does not match collector")

    def collector_for(self, source_type: str) -> JobCollector:
        try:
            return self._collectors[source_type]
        except KeyError as exc:
            raise LookupError(f"no collector registered for {source_type}") from exc
