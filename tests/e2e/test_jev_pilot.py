"""Exercise the pilot runner offline; all inference in this test is simulated."""

import json
import runpy
import sys
from pathlib import Path

from openclass_provider_mock import MockDecisionProvider
from openclass_server.main import create_app


def test_smoke_report_and_restart_without_labels(tmp_path, monkeypatch) -> None:
    runner = runpy.run_path("scripts/jev_pilot.py")
    main = runner["main"]
    monkeypatch.setenv("OPENCLASS_RUN_LIVE_TESTS", "1")
    monkeypatch.setenv("OPENCLASS_JEV_API_KEY", "synthetic-pilot-key")
    monkeypatch.setitem(
        main.__globals__,
        "create_app",
        lambda settings: create_app(settings, provider=MockDecisionProvider()),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["jev_pilot", "--smoke", "--labels", "missing.json", "--output", str(tmp_path)],
    )
    assert main() == 0
    reports = list(Path(tmp_path).glob("*/report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert report["call_limit"] == report["summary"]["completed"] == 1
    assert report["label_provenance"] is None
    assert "known_accuracy" not in report["summary"]
    assert report["rows"][0]["result"]["decision"]["provider_metadata"]["simulated"]
    assert "synthetic-pilot-key" not in reports[0].read_text()
