"""Parse internal log messages and calculate windowed log/CDR features."""

import json
import re

import numpy as np
import pandas as pd

from src.domain.contracts import timestamp_seconds

LOGGER = re.compile(
    r"^(?P<event_time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[.,]\d+)\s+"
    r"(?P<logger>\S+)\s+\[(?P<level>TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\]"
    r"(?:\s+\[(?P<thread>[^\]]*)\])?"
)
WRITE = re.compile(r"Write cdr service id:\s*(\d+)\s+to file\s*:\s*(\S+)", re.I)
CDR = re.compile(r"CdrUtils[.]toRawCdr:\s*(.*)$")
KEYS = {
    "msisdn_check": r"MSISDN_CHECK:\s*([^,\s]+)",
    "telecom_service_id": r"TELECOMSERVICE_ID:\s*(\d+)",
    "file_name_id": r"FILE_NAME_ID:\s*(\d+)",
    "session_id": r"sessionId=\[([^\]]*)\]",
    "msisdn": r"msisdn=\[([^\]]*)\]",
    "topic": r"Topic:\s*([^,]+)",
    "create_date": r"createDate:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[.,]\d+)",
}
FAMILIES = ("cdr_raw", "cdr_write", "custhis_rollback", "application_log", "unparsed")


def parse_messages(records: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Keep one event per nonempty physical line, with source-row provenance.

    Event timestamps stay separate from the CSV timestamp used for features.
    Positional CDR names are candidates from the supplied template, not labels.
    Unrecognized lines are retained; budgets fail rather than truncate messages.
    """
    if config.get("version") != 1:
        raise ValueError("Expected log parser config version 1")
    rows = []
    for source in records.to_dict("records"):
        text = str(source["text"])
        if len(text) > config.get("max_message_characters", 200000):
            raise ValueError("Message character budget exceeded; inspect source record")
        writes = WRITE.findall(text)
        unique_services = {item[0] for item in writes}
        for line_number, line in enumerate(text.splitlines() or [""], 1):
            if not line.strip() and text.strip():
                continue
            row = {
                key: source.get(key, "")
                for key in ("system_id", "entity_id", "source_file", "source_record")
            }
            row.update(
                timestamp=source["timestamp"],
                line_number=line_number,
                message=line,
                family="unparsed",
                parse_status="unparsed",
                level="",
                event_timestamp=np.nan,
                create_timestamp=np.nan,
                logger_create_delay_ms=np.nan,
                cdr_field_count=np.nan,
                resource_charge1=np.nan,
                call_id="",
                cdr_service_id="",
                cdr_fields_json="{}",
                template_status="not_applicable",
            )
            match = LOGGER.match(line.strip())
            if match:
                row.update(match.groupdict())
                row.update(family="application_log", parse_status="parsed")
                try:
                    row["event_timestamp"] = timestamp_seconds(
                        match["event_time"].replace(",", "."),
                        "iso",
                        source.get("source_timezone", "Asia/Ho_Chi_Minh"),
                    )
                except ValueError:
                    row["parse_status"] = "invalid_event_time"
            for key, pattern in KEYS.items():
                found = re.search(pattern, line)
                row[key] = found[1].strip() if found else ""
            if "CustHis_Rollback" in line:
                row["family"] = "custhis_rollback"
                # A recognized body does not establish an ERROR level.
                if row["parse_status"] == "unparsed":
                    row["parse_status"] = "parsed"
            if row["create_date"]:
                try:
                    row["create_timestamp"] = timestamp_seconds(
                        row["create_date"].replace(",", "."),
                        "iso",
                        source.get("source_timezone", "Asia/Ho_Chi_Minh"),
                    )
                    row["logger_create_delay_ms"] = (
                        row["event_timestamp"] - row["create_timestamp"]
                    ) * 1000
                except ValueError:
                    row["parse_status"] = "invalid_create_time"
            write = WRITE.search(line)
            if write:
                row.update(
                    family="cdr_write",
                    parse_status="parsed",
                    cdr_service_id=write[1],
                    output_path=write[2],
                )
            cdr = CDR.search(line)
            if cdr:
                fields = cdr[1].strip().split(";")
                # A trailing delimiter is a field, not silently removed.
                row.update(
                    family="cdr_raw",
                    cdr_field_count=len(fields),
                    cdr_fields_json=json.dumps(fields, ensure_ascii=False),
                    parse_status="cdr_schema_unknown",
                    template_status="unconfirmed",
                )
                expected = str(source.get("expected_cdr_service_id", ""))
                service = (
                    next(iter(unique_services)) if len(unique_services) == 1 else ""
                )
                schema = config.get("cdr_schemas", {}).get(service)
                if expected and service != expected:
                    row["parse_status"] = "cdr_service_mismatch"
                elif schema and len(fields) == len(schema["fields"]):
                    named = dict(zip(schema["fields"], fields))
                    row.update(
                        cdr_service_id=service,
                        parse_status="parsed",
                        template_status="matched_template_candidate",
                        cdr_fields_json=json.dumps(named, ensure_ascii=False),
                        call_id=named.get("CALL_ID", ""),
                    )
                    for name, value in named.items():
                        row["cdr_field_" + name.lower()] = value
                    row["resource_charge1"] = pd.to_numeric(
                        named.get("RESOURCE_CHARGE1"), errors="coerce"
                    )
                elif schema:
                    row["parse_status"] = "cdr_field_count_mismatch"
            row["template_id"] = row["family"]
            rows.append(row)
            if len(rows) > config.get("max_events", 1000000):
                raise ValueError("Expanded log event budget exceeded; partition files")
    return pd.DataFrame(rows)


def message_features(events: pd.DataFrame, window_seconds: int) -> pd.DataFrame:
    """Count observed events by fixed template family; do not fill silent windows."""
    if events.empty:
        return pd.DataFrame()
    events = events.copy()
    events["window_end"] = (
        np.floor(events.timestamp / window_seconds) + 1
    ) * window_seconds
    rows = []
    for (system, entity, window), group in events.groupby(
        ["system_id", "entity_id", "window_end"]
    ):
        valid_cdr = group[(group.family == "cdr_raw") & group.parse_status.eq("parsed")]
        cdr_count = int(group.family.eq("cdr_raw").sum())
        charge = valid_cdr.resource_charge1.replace([np.inf, -np.inf], np.nan).dropna()
        delay = group.logger_create_delay_ms
        nonnegative = delay[delay >= 0]
        known_levels = int(group.level.ne("").sum())
        values = {
            "log_event_count": len(group),
            "log_record_count": len(
                group[["source_file", "source_record"]].drop_duplicates()
            ),
            "log_parse_unknown_ratio": float(group.parse_status.ne("parsed").mean()),
            "log_level_error_ratio": (
                float(group.level.isin(["ERROR", "FATAL"]).sum() / known_levels)
                if known_levels
                else np.nan
            ),
            "log_level_missing_ratio": float(group.level.eq("").mean()),
            "log_warning_count": int(group.level.isin(["WARN", "WARNING"]).sum()),
            "cdr_schema_mismatch_count": int(
                group.parse_status.str.startswith("cdr_").sum()
            ),
            "cdr_valid_count": len(valid_cdr),
            "cdr_duplicate_call_id_ratio": (
                float(
                    valid_cdr.loc[valid_cdr.call_id.ne(""), "call_id"]
                    .duplicated()
                    .mean()
                )
                if valid_cdr.call_id.ne("").any()
                else np.nan
            ),
            "cdr_charge_observed_count": len(charge),
            "cdr_charge_coverage_ratio": (
                len(charge) / cdr_count if cdr_count else np.nan
            ),
            "cdr_resource_charge1_sum": (
                charge.sum() if len(charge) == cdr_count and len(charge) else np.nan
            ),
            "cdr_resource_charge1_mean": charge.mean(),
            "log_logger_create_delay_p95_ms": nonnegative.quantile(0.95),
            "log_negative_delay_count": int((delay < 0).sum()),
            "log_delay_observed_count": int(delay.notna().sum()),
        }
        for family in FAMILIES:
            values[f"log_template_{family}_count"] = int(group.family.eq(family).sum())
        for name, value in values.items():
            rows.append(
                dict(
                    system_id=system,
                    entity_id=entity,
                    dimensions="{}",
                    series_id=name,
                    feature_name=name,
                    window_end=window,
                    value=value,
                )
            )
    return pd.DataFrame(rows)
