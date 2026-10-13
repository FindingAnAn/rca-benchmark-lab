"""Check message extraction without interpreting INFO or identifiers as labels."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.application import run_internal
from src.data.ingestion.log_csv import CsvLogAdapter
from src.domain.contracts import timestamp_seconds
from src.features.log_parser import message_features, parse_messages
from src.settings import AnalysisSettings, RuntimeSettings

ROOT = Path(__file__).resolve().parents[1]
PARSER = json.loads((ROOT / "config/log_parser.json").read_text(encoding="utf-8"))


def sample_message(service="7000001", suffix=""):
    fields = [
        "215141799999999999" + suffix,
        "contract",
        "sub",
        "account",
        "6010",
        "20260801000000",
        "20260801000000",
        "20260825000000",
        "PLAN",
        "100.25",
        "0",
        "account",
        "1",
        "0",
        "sub",
        "contract",
        "5",
        "20260824235959",
        "charging",
        "20260824000000",
        "account",
        "16",
    ]
    return (
        "CdrUtils.toRawCdr: "
        + ";".join(fields)
        + f"\n. Write cdr service id: {service} to file : /internal/example.dat\n"
        "2026-08-24 01:00:00.146 c.v.CdrImportThread [INFO] [kafka-producer-network-thread | producer-1]: "
        "msisdn=[] sessionId=[] Topic: CustHis_Rollback, CdrEvent to cdrImport, "
        "MSISDN_CHECK: account, TELECOMSERVICE_ID: 3000000, FILE_NAME_ID: 000123, "
        "createDate: 2026-08-24 01:00:00.137"
    )


def canonical(message):
    return pd.DataFrame(
        [
            dict(
                timestamp=60.0,
                text=message,
                system_id="fixture",
                entity_id="system",
                source_file="example.csv",
                source_record=1,
                source_timezone="Asia/Ho_Chi_Minh",
                expected_cdr_service_id="7000001",
            )
        ]
    )


def test_kibana_timestamp_and_multiline_csv(tmp_path):
    pd.DataFrame(
        {"@timestamp": ["Aug 24, 2026 @ 01:00:00.146"], "message": [sample_message()]}
    ).to_csv(tmp_path / "example.csv", index=False)
    records = CsvLogAdapter().read(
        tmp_path,
        [
            dict(
                file="example.csv",
                system_id="a",
                timestamp_column="@timestamp",
                text_column="message",
                time_unit="kibana_display",
                timezone="Asia/Ho_Chi_Minh",
                cdr_service_id="7000001",
            )
        ],
        tmp_path / "raw",
        5,
    )
    assert len(records) == 1
    assert records.timestamp.iloc[0] == timestamp_seconds(
        "2026-08-24T01:00:00.146+07:00", "iso", "UTC"
    )
    assert records.source_record.iloc[0] == 1
    events = parse_messages(records, PARSER)
    assert len(events) == 3
    assert events.source_record.nunique() == 1


def test_cdr_schema_and_info_rollback_are_not_failure_labels():
    events = parse_messages(canonical(sample_message()), PARSER)
    assert events.family.tolist() == ["cdr_raw", "cdr_write", "custhis_rollback"]
    assert events.cdr_field_call_id.iloc[0] == "215141799999999999"
    assert events.resource_charge1.iloc[0] == 100.25
    assert events.file_name_id.iloc[2] == "000123"
    assert np.isclose(events.logger_create_delay_ms.iloc[2], 9, atol=0.001)
    features = message_features(events, 60).set_index("feature_name").value
    assert features.log_event_count == 3
    assert features.log_record_count == 1
    assert features.log_level_error_ratio == 0
    assert features.log_template_custhis_rollback_count == 1
    assert features.cdr_resource_charge1_sum == 100.25


def test_schema_mismatch_and_service_conflict_preserve_raw_fields():
    for message, status in [
        (sample_message().replace(";16\n", ";16;extra\n"), "cdr_field_count_mismatch"),
        (sample_message("7000005"), "cdr_service_mismatch"),
    ]:
        events = parse_messages(canonical(message), PARSER)
        assert events.parse_status.iloc[0] == status
        assert np.isnan(events.resource_charge1.iloc[0])
        assert isinstance(json.loads(events.cdr_fields_json.iloc[0]), list)


def test_missing_and_negative_delay_are_not_latency():
    events = parse_messages(
        canonical(sample_message().replace("00.137", "00.150")), PARSER
    )
    values = message_features(events, 60).set_index("feature_name").value
    assert values.log_negative_delay_count == 1
    assert np.isnan(values.log_logger_create_delay_p95_ms)
    assert "process_time_ms" not in values


def test_unknown_lines_and_budgets():
    events = parse_messages(canonical("unrecognized message\ncontinuation"), PARSER)
    values = message_features(events, 60).set_index("feature_name").value
    assert values.log_parse_unknown_ratio == 1
    assert np.isnan(values.log_level_error_ratio)
    assert np.isnan(values.cdr_resource_charge1_sum)
    with pytest.raises(ValueError, match="event budget"):
        parse_messages(canonical(sample_message()), {**PARSER, "max_events": 1})


def test_all_five_files_internal_flow_and_empty_windows(tmp_path):
    config = json.loads((ROOT / "config/internal.json").read_text())
    config["metric"]["enabled"] = False
    config["log"]["enabled"] = True
    config["relationships"]["enabled"] = False
    for source in config["log"]["sources"]:
        # Six observed windows then a gap. No synthetic zeros in silent windows.
        pd.DataFrame(
            {
                "@timestamp": [
                    f"Aug 24, 2026 @ 01:{minute:02d}:00.146"
                    for minute in [0, 1, 2, 3, 4, 5, 8]
                ],
                "message": [sample_message(source["cdr_service_id"])] * 7,
            }
        ).to_csv(tmp_path / source["file"], index=False)
    reference = timestamp_seconds("2026-08-24T01:05:00+07:00", "iso", "UTC")
    output = tmp_path / "run"
    run_internal(
        config,
        AnalysisSettings(window_seconds=60, min_reference_points=5),
        RuntimeSettings(ROOT, tmp_path, tmp_path, "", ""),
        output,
        reference,
        None,
        None,
        None,
        eda_only=True,
    )
    parsed = pd.read_parquet(output / "parsed_log_events.parquet")
    assert parsed.system_id.nunique() == 5
    assert parsed.parse_status.eq("parsed").all()
    features = pd.read_parquet(output / "features.parquet")
    assert not features.window_end.eq(reference + 120).any()
    assert (output / "cdr_fields.csv").exists()
    assert (output / "manifest.json").exists()
