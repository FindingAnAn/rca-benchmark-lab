"""Read bounded VMUI-compatible API windows and preserve original labels"""

import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from src.settings import RuntimeSettings
from src.storage import write_json


def get_json(url: str, authorization: str = "", timeout_seconds: int = 60) -> dict:
    """Read an HTTP JSON response without logging endpoint credentials"""
    headers = {"Authorization": authorization} if authorization else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.load(response)


class VictoriaMetricsAdapter:
    """Export raw counters/gauges; derived rates belong to feature processing"""

    def __init__(
        self, runtime: RuntimeSettings, transport: Callable = get_json
    ) -> None:
        self.runtime = runtime
        self.transport = transport

    def export(
        self, config: dict, start: float, end: float, output: Path
    ) -> pd.DataFrame:
        """Fetch each system/query in bounded chunks with stable series identities

        Args:
            config: Explicit systems, metric contracts and query limits.
            start: First UTC sample timestamp.
            end: Last UTC sample timestamp.
            output: New directory for original API responses.
        Returns:
            Long-form metric records with no inferred fault labels.
        Raises:
            ValueError: Partial responses, missing identities or budget violations.
        """
        if not self.runtime.vm_api_url:
            raise ValueError("Set RCA_VM_API_URL to .../prometheus/api/v1")
        if end <= start or end - start > config.get("max_export_seconds", 3600):
            raise ValueError("Export window exceeds configured budget")
        output.mkdir(parents=True, exist_ok=False)
        records = []
        step = int(config.get("step_seconds", 60))
        chunk = int(config.get("chunk_seconds", 900))
        if step <= 0 or chunk < step:
            raise ValueError("Require 0 < step_seconds <= chunk_seconds")
        for system in config["systems"]:
            if not re.fullmatch(r"[a-zA-Z0-9_-]+", system["system_id"]):
                raise ValueError("Invalid system_id")
            if not system["match_labels"]:
                raise ValueError("Explicit system scope labels required")
            for metric in config["metrics"]:
                records.extend(
                    self._export_query(
                        system, metric, config, start, end, step, chunk, output
                    )
                )
                if len(records) > config.get("max_rows", 500000):
                    raise ValueError(
                        "Row budget exceeded; narrow system, query or time window"
                    )
        if not records:
            raise ValueError("No metric samples returned; inspect VMUI scope and dates")
        return pd.DataFrame(records)

    def _export_query(
        self,
        system: dict,
        metric: dict,
        config: dict,
        start: float,
        end: float,
        step: int,
        chunk: int,
        output: Path,
    ) -> list[dict]:
        extra = metric.get("match_labels", {})
        if any(
            key in system["match_labels"] and system["match_labels"][key] != value
            for key, value in extra.items()
        ):
            raise ValueError("Metric scope cannot override system scope")
        labels = {**system["match_labels"], **extra}
        if any(not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name) for name in labels):
            raise ValueError("Invalid Prometheus label name")
        if not re.fullmatch(r"[a-zA-Z_:][a-zA-Z0-9_:]*", metric["name"]):
            raise ValueError("Invalid metric name")
        selector = ",".join(
            f"{name}={json.dumps(value)}" for name, value in sorted(labels.items())
        )
        query = metric["name"] + "{" + selector + "}"
        records = []
        cursor = start
        chunk_index = 0
        while cursor <= end:
            stop = min(end, cursor + (chunk // step - 1) * step)
            params = urllib.parse.urlencode(
                dict(
                    query=query,
                    start=cursor,
                    end=stop,
                    step=step,
                    deny_partial_response=1,
                )
            )
            response = self.transport(
                self.runtime.vm_api_url + "/query_range?" + params,
                self.runtime.vm_authorization,
            )
            file_name = f"{system['system_id']}_{metric['name']}_{chunk_index}.json"
            write_json(output / file_name, response)
            records.extend(self.parse_response(response, system, metric, config))
            if len(records) > config.get("max_rows", 500000):
                raise ValueError("One query exceeded row budget")
            cursor = stop + step
            chunk_index += 1
        return records

    @staticmethod
    def parse_response(
        response: dict, system: dict, metric: dict, config: dict
    ) -> list[dict]:
        """Validate a VM matrix and preserve all label dimensions in series identity"""
        if (
            response.get("status") != "success"
            or response.get("isPartial")
            or response.get("warnings")
        ):
            raise ValueError("VM returned an error, partial result or warning")
        if response.get("data", {}).get("resultType") != "matrix":
            raise ValueError("Expected query_range matrix")
        records = []
        for series in response["data"]["result"]:
            labels = series["metric"]
            entity_label = metric.get(
                "entity_label", config.get("entity_label", "pod_id")
            )
            entity = labels.get(entity_label)
            if not entity:
                raise ValueError(
                    f"Metric missing configured entity label: {entity_label}"
                )
            # Matching dimensions are explicit; omitted dimensions are still preserved in labels.
            dimensions = json.dumps(
                {
                    name: labels.get(name, "")
                    for name in metric.get("comparison_dimensions", [])
                },
                sort_keys=True,
            )
            identity = json.dumps(
                [system["system_id"], metric["name"], labels], sort_keys=True
            )
            for timestamp, value in series["values"]:
                records.append(
                    dict(
                        timestamp=float(timestamp),
                        value=float(value),
                        system_id=system["system_id"],
                        entity_id=str(entity),
                        metric=metric["name"],
                        kind=metric["kind"],
                        unit=metric["unit"],
                        cadence_seconds=metric.get(
                            "cadence_seconds", config.get("step_seconds", 60)
                        ),
                        series_id=hashlib.sha256(identity.encode()).hexdigest()[:24],
                        dimensions=dimensions,
                        labels=json.dumps(labels, sort_keys=True),
                    )
                )
        return records
