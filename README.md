# EvalGate

I use EvalGate to check whether a change to an intake assistant introduces a bad tool call, drops evidence or answers a question it should defer to a dispatcher. The first suite is based on water-utility intake in AquaOps. Its eight cases and two recordings are fictional and hand-authored.

**Status:** Preserved replay prototype. The CLI and MCP examples can be run locally.

## Replay an evaluation

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test,mcp]'
evalgate init workspace
cd workspace
evalgate run suites/water-utility-intake.yaml --mode replay --trace traces/baseline.json --out runs/baseline.json
evalgate run suites/water-utility-intake.yaml --trace traces/regression.json --out runs/candidate.json
evalgate compare --baseline runs/baseline.json --candidate runs/candidate.json
evalgate gate --run runs/candidate.json
evalgate report --run runs/candidate.json --format html > report.html
```

The baseline passes all eight cases. The candidate proposes closing an incident without dispatcher confirmation. Compare and gate exit with code 1. Invalid input exits with code 2. Use a new output path for each run.

## Evaluator contract

A suite defines expected structured output, ordered tool calls and arguments, evidence identifiers, abstention, latency and cost limits. Each trace must appear exactly once. A forbidden action blocks release at any pass-rate threshold. Changing the suite or thresholds changes its fingerprint and invalidates comparisons against the old suite.

Replace a fixture with a recording exported by your application, preserving its source, case IDs, outputs and measured costs. Evidence checks compare recorded identifiers. Model quality, provider latency and real spend require live observations. No external model, municipal system or tool is invoked by replay.

## Local MCP tools

From the initialized workspace, run `evalgate-mcp` as a stdio server. Set `EVALGATE_WORKSPACE` to use a different directory. Clients can list suites, run a named recording, read a report by ID, and compare two reports. The server keeps the latest 64 reports in memory. The CLI writes durable JSON reports to a user-selected path.

Run `pytest` from the repository root for regression tests. This release covers deterministic replay.
