from pathlib import Path
import json

import pytest

from evalgate.cli import main
from evalgate.core import Recording, compare, evaluate, load_suite, read_text

EXAMPLES = Path(__file__).parents[1] / "src/evalgate/examples"


def fixture():
    suite = load_suite(EXAMPLES / "water-utility-intake.yaml")
    traces = Recording.model_validate_json(read_text(EXAMPLES / "baseline.json"))
    return suite, traces


def test_cli_replay_and_gate(tmp_path, capsys):
    assert main(["init", str(tmp_path)]) == 0
    suite = str(tmp_path / "suites/water-utility-intake.yaml")
    paths = {}
    for name, expected in [("baseline", 0), ("regression", 1)]:
        out = tmp_path / (name + ".json")
        assert main(["run", suite, "--trace", str(tmp_path / f"traces/{name}.json"), "--out", str(out)]) == 0
        assert main(["gate", "--run", str(out)]) == expected
        paths[name] = str(out)
    assert main(["compare", "--baseline", paths["baseline"], "--candidate", paths["regression"]]) == 1
    assert "forbidden_action" in capsys.readouterr().out
    assert main(["report", "--run", paths["regression"], "--format", "html"]) == 0
    assert "<table>" in capsys.readouterr().out


def test_missing_case_and_duplicate_case_are_invalid():
    suite, traces = fixture()
    traces.traces.pop()
    with pytest.raises(ValueError, match="exactly once"):
        evaluate(suite, traces)
    traces.traces.append(traces.traces[0])
    with pytest.raises(ValueError, match="exactly once"):
        evaluate(suite, traces)


def test_each_check_detects_an_independent_change():
    suite, traces = fixture()
    reference = evaluate(suite, traces)
    trace = traces.traces[0]
    trace.calls[0].arguments = {"address": "other"}
    trace.evidence = []
    trace.output["review"] = 0  # JSON number is distinct from false.
    trace.abstained = True
    trace.cost_usd, trace.latency_ms = 0.5, 2000
    changes = compare(reference, evaluate(suite, traces))
    assert changes[trace.id] == sorted(["output", "tool_arguments", "evidence", "abstention", "cost", "latency"])
    suite.version += 1
    with pytest.raises(ValueError, match="same reviewed suite"):
        compare(reference, evaluate(suite, traces))


def test_forbidden_action_always_blocks():
    suite, _ = fixture()
    traces = Recording.model_validate(json.loads(read_text(EXAMPLES / "regression.json")))
    suite.min_pass_rate = 0.1
    assert not evaluate(suite, traces).passed
