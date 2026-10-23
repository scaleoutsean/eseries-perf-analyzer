import math

from api import get_analyzed_statistics
from mappings import HOST_PERFORMANCE_METRIC_DEFS
from transport_metrics import TransportMetrics


class HostPerformanceMetrics(TransportMetrics):
    """Publish gated, analyzed host averages as gauges, never counters."""

    metric_definitions = HOST_PERFORMANCE_METRIC_DEFS
    log_name = "Host performance metrics"

    def __init__(self, statistics_fetch_time=300, **kwargs):
        super().__init__(**kwargs)
        self.statistics_fetch_time = statistics_fetch_time

    def _fetch(self, session, url, definition):
        return get_analyzed_statistics(
            session, url, definition["identity_keys"], self.statistics_fetch_time,
        )

    @staticmethod
    def _parse(payload, system_info, definition):
        samples = []
        for row in payload:
            identities = [row[key] for key in definition["identity_keys"]]
            if "controllerId" in definition["identity_keys"]:
                index = definition["identity_keys"].index("controllerId")
                identities[index] = {
                    "070000000000000000000001": "A",
                    "070000000000000000000002": "B",
                }.get(identities[index], identities[index])
            base_labels = [str(system_info.get("wwn") or system_info.get("id")),
                           str(system_info.get("name") or "unknown"), *identities]
            for path, suffix, kind, extra_labels in definition["fields"]:
                value = row.get(path[0])
                if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                    continue
                try:
                    value = float(value)
                except (ValueError, OverflowError):
                    continue
                if not math.isfinite(value) or value < 0:
                    continue
                if suffix == "throughput_bytes_per_second":
                    value *= 1024 ** 2
                elif suffix in ("response_time_seconds", "response_time_stddev_seconds", "observed_timestamp_seconds"):
                    value /= 1000
                elif suffix == "response_time_max_seconds":
                    value /= 1_000_000
                if not math.isfinite(value):
                    continue
                labels = tuple(base_labels + [extra_labels[key] for key in sorted(extra_labels)])
                samples.append((f"{definition['prefix']}_{suffix}", labels, value))
        return tuple(samples)