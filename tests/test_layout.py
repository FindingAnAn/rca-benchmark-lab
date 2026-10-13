"""Check the flat src package and local data defaults."""

import json
import sys
from pathlib import Path

from src import cli
from src.settings import RuntimeSettings


def test_runtime_defaults_and_home_expansion(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("RCA_DATA_ROOT", raising=False)
    monkeypatch.delenv("RCA_LOG_ROOT", raising=False)
    runtime = RuntimeSettings.from_env(tmp_path / "project")
    assert runtime.data_root == tmp_path / "Downloads" / "rca_eval"
    assert runtime.log_root == tmp_path / "Downloads" / "anomaly"
    monkeypatch.setenv("RCA_LOG_ROOT", "~/Downloads/anomaly")
    assert (
        RuntimeSettings.from_env(tmp_path).log_root
        == Path("~/Downloads/anomaly").expanduser()
    )


def test_cli_uses_project_root_and_default_corpus(monkeypatch, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({}))
    monkeypatch.setenv("RCA_DATA_ROOT", str(tmp_path / "rca_eval"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rca-lab",
            "rcaeval",
            "--config",
            str(config),
            "--output",
            str(tmp_path / "out"),
        ],
    )
    captured = []
    monkeypatch.setattr(cli, "run_rcaeval", lambda *args: captured.extend(args))
    cli.main()
    assert captured[2].project_root == Path(cli.__file__).resolve().parents[1]
    assert captured[3] == tmp_path / "rca_eval"
