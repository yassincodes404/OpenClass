import json
import sys

import httpx
import pytest
from openclass_cli.main import main
from openclass_sdk import OpenClass


def test_cli_classifies_through_sdk(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["openclass", "classify", "charged twice"])

    def classify(self, *, classifier, observation, metadata=None):
        assert classifier == "support-intent" and observation == "charged twice"
        return {"selected_class": "billing"}

    monkeypatch.setattr(OpenClass, "classify", classify)
    main()
    assert json.loads(capsys.readouterr().out)["selected_class"] == "billing"


def test_cli_requests_advisory_review_through_sdk(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(
        sys, "argv", ["openclass", "review", "run-1", "--classifier", "support-intent"]
    )

    def review_run(self, *, classifier, run_id):
        assert classifier == "support-intent" and run_id == "run-1"
        return {"trigger": "manual", "result": {"finding": "no_issue"}}

    monkeypatch.setattr(OpenClass, "review_run", review_run)
    main()
    output = json.loads(capsys.readouterr().out)
    assert output["result"]["finding"] == "no_issue"


def test_cli_connection_failure_is_actionable(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["openclass", "doctor"])

    def health(self):
        raise httpx.ConnectError("private network detail")

    monkeypatch.setattr(OpenClass, "health", health)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert "openclass serve" in capsys.readouterr().err
