import logging
import re
import time
from threading import Lock

import requests
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from api import get_json
from mappings import TRANSPORT_METRIC_DEFS


LOG = logging.getLogger("collector")
SUPPORTED_MODELS = {"EF50", "EF80"}


def release_version(payload):
    """Read the SANtricity release, not the separate RAID firmware version."""
    if not isinstance(payload, dict):
        return None
    versions = payload.get("codeVersions")
    if not isinstance(versions, list):
        return None
    for module in ("management", "bundleDisplay"):
        for entry in versions:
            if not isinstance(entry, dict) or entry.get("codeModule") != module:
                continue
            version = entry.get("versionString")
            if isinstance(version, str):
                match = re.match(r"^(\d+)\.(\d+)(?:\.|R|$)", version.strip())
                if match:
                    return tuple(int(part) for part in match.groups())
    return None


class TransportMetrics:
    """Publish absolute transport snapshots without changing legacy metrics."""

    metric_definitions = TRANSPORT_METRIC_DEFS
    log_name = "Transport metrics"

    def __init__(self, clock=time.monotonic, discovery_interval=900, retry_interval=60):
        self.clock = clock
        self.discovery_interval = discovery_interval
        self.retry_interval = retry_interval
        self._capabilities = {}
        self._retry_after = {}
        self._snapshots = {}
        self._lock = Lock()

    def _families(self):
        families = {}
        for definition in self.metric_definitions.values():
            for path, suffix, kind, extra_labels in definition["fields"]:
                name = f"{definition['prefix']}_{suffix}"
                labels = definition.get("labels", ["sys_id", "sys_name", "controller_id", "interface_id"]) + sorted(extra_labels)
                family_type = CounterMetricFamily if kind == "counter" else GaugeMetricFamily
                description = f"{definition['prefix']} {suffix.removesuffix('_total').replace('_', ' ')}"
                families.setdefault(name, family_type(name, description, labels=labels))
        return families

    def describe(self):
        return self._families().values()

    def collect(self):
        with self._lock:
            snapshots = tuple(self._snapshots.values())
        families = self._families()
        for snapshot in snapshots:
            for name, labels, value in snapshot:
                families[name].add_metric(labels, value)
        return (family for family in families.values() if family.samples)

    def clear(self, system_id):
        with self._lock:
            for key in list(self._snapshots):
                if key[0] == system_id:
                    del self._snapshots[key]

    def update(self, session, system_info, system_root, firmware_root, include=None):
        system_id = system_info.get("wwn") or system_info.get("id")
        selected = {
            measurement for measurement in self.metric_definitions
            if not include or measurement in include
        }
        if not selected or not self.eligible(session, system_info, firmware_root):
            self.clear(system_id)
            return
        now = self.clock()
        for measurement, definition in self.metric_definitions.items():
            key = (system_id, measurement)
            if measurement not in selected:
                with self._lock:
                    self._snapshots.pop(key, None)
                continue
            if now < self._retry_after.get(key, 0):
                continue
            try:
                payload = self._fetch(session, f"{system_root}/{system_id}{definition['endpoint']}", definition)
                snapshot = self._parse(payload, system_info, definition)
                if not snapshot:
                    self._retry_after[key] = now + self.discovery_interval
                    LOG.info("No usable %s statistics for %s; backing off", measurement, system_id)
                else:
                    self._retry_after.pop(key, None)
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                unsupported = status in (404, 405, 501)
                self._retry_after[key] = now + (self.discovery_interval if unsupported else self.retry_interval)
                LOG.warning("%s statistics %s for %s (HTTP %s)", measurement,
                            "unsupported" if unsupported else "unavailable", system_id, status)
                snapshot = ()
            except (requests.exceptions.RequestException, ValueError) as exc:
                self._retry_after[key] = now + self.retry_interval
                LOG.warning("%s statistics unavailable for %s: %s", measurement, system_id, exc)
                snapshot = ()
            with self._lock:
                self._snapshots[key] = snapshot

    def _fetch(self, session, url, definition):
        return get_json(session, url)

    @staticmethod
    def _parse(payload, system_info, definition):
        if not isinstance(payload, list):
            raise ValueError("Expected a controller statistics list")
        samples = {}
        for controller in payload:
            if not isinstance(controller, dict) or not isinstance(controller.get("interfaceStatistics"), list):
                raise ValueError("Expected per-controller interfaceStatistics lists")
            controller_id = controller.get("controllerId")
            if not isinstance(controller_id, str) or not controller_id:
                continue
            controller_id = {
                "070000000000000000000001": "A",
                "070000000000000000000002": "B",
            }.get(controller_id, controller_id)
            for interface in controller["interfaceStatistics"]:
                if not isinstance(interface, dict):
                    continue
                interface_id = interface.get("interfaceId")
                if not isinstance(interface_id, str) or not interface_id:
                    continue
                for path, suffix, kind, extra_labels in definition["fields"]:
                    value = interface.get("raw")
                    qualifiers = interface.get("qualifiers")
                    qualifier = qualifiers.get("raw") if isinstance(qualifiers, dict) else None
                    for part in path:
                        value = value.get(part) if isinstance(value, dict) else None
                        qualifier = qualifier.get(part) if isinstance(qualifier, dict) else qualifier
                    if isinstance(qualifier, str) and qualifier.strip().lower() == "unknown":
                        continue
                    if isinstance(value, bool) or not isinstance(value, (str, int)):
                        continue
                    try:
                        value = int(value)
                    except ValueError:
                        continue
                    if value < 0:
                        continue
                    name = f"{definition['prefix']}_{suffix}"
                    labels = (
                        str(system_info.get("wwn") or system_info.get("id")),
                        str(system_info.get("name") or "unknown"),
                        controller_id, interface_id,
                    ) + tuple(extra_labels[key] for key in sorted(extra_labels))
                    samples[name, labels] = value
        return tuple((name, labels, value) for (name, labels), value in samples.items())

    def eligible(self, session, system_info, firmware_root):
        system_id = system_info.get("wwn") or system_info.get("id")
        if not system_id:
            return False
        model = str(system_info.get("model") or "").strip().upper()
        fingerprint = (model, system_info.get("fwVersion"), system_info.get("appVersion"))
        now = self.clock()
        cached = self._capabilities.get(system_id)
        if cached and cached["fingerprint"] == fingerprint and now < cached["next_check"]:
            return cached["eligible"]

        supported = False
        version = None
        interval = self.discovery_interval
        reason = f"unconfirmed or unsupported model {model or 'unknown'}"
        if model in SUPPORTED_MODELS:
            try:
                version = release_version(get_json(session, f"{firmware_root}/1/versions"))
                supported = version is not None and version >= (12, 1)
                reason = f"SANtricity release {version or 'unknown'} on {model}"
                if version is None:
                    interval = self.retry_interval
            except (requests.exceptions.RequestException, ValueError) as exc:
                reason = f"release discovery unavailable: {exc}"
                interval = self.retry_interval
                LOG.warning("%s discovery failed for %s: %s", self.log_name, system_id, exc)

        if cached and (cached["fingerprint"] != fingerprint or cached["eligible"] != supported
                   or cached["version"] != version):
            self.clear(system_id)
            for key in list(self._retry_after):
                if key[0] == system_id:
                    del self._retry_after[key]
        self._capabilities[system_id] = {
            "fingerprint": fingerprint,
            "next_check": now + interval,
            "eligible": supported,
            "version": version,
        }
        LOG.info("%s for %s: %s (%s)", self.log_name, system_id,
                 "eligible" if supported else "skipped", reason)
        return supported