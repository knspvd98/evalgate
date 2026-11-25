"""Expose operator-installed suites and recordings over local stdio."""
from collections import OrderedDict
import hashlib
import os
from pathlib import Path
import re

from .core import Recording, canonical, compare, evaluate, load_suite, read_text


def build_server(root: Path):
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("EvalGate")
    reports = OrderedDict()

    def resolve(directory, identifier, extension):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
            raise ValueError("Invalid identifier")
        base = root.resolve()
        path = base / directory / (identifier + extension)
        if path.resolve() != path or not path.is_file():
            raise ValueError("Unknown suite or recording")
        return path

    @server.tool()
    def list_suites() -> list[str]:
        """List available suite IDs."""
        return sorted(p.stem for p in (root / "suites").glob("*.yaml")
                      if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", p.stem) and not p.is_symlink())

    @server.tool()
    def run_suite(suite: str, recording: str) -> dict:
        """Grade a named recording. No model or tool calls are executed."""
        spec = load_suite(resolve("suites", suite, ".yaml"))
        traces = Recording.model_validate_json(read_text(resolve("traces", recording, ".json")))
        report = evaluate(spec, traces)
        identifier = hashlib.sha256(canonical(report.model_dump()).encode()).hexdigest()
        reports[identifier] = report
        reports.move_to_end(identifier)
        if len(reports) > 64:
            reports.popitem(last=False)
        return {"run_id": identifier, "passed": report.passed, "pass_rate": report.pass_rate}

    @server.tool()
    def get_run_results(run_id: str) -> dict:
        """Return one of the latest 64 in-memory reports."""
        return reports[run_id].model_dump()

    @server.tool()
    def compare_runs(baseline: str, candidate: str) -> dict:
        """Return newly failed checks per case."""
        return compare(reports[baseline], reports[candidate])

    return server


def main():
    build_server(Path(os.environ.get("EVALGATE_WORKSPACE", ".")).resolve()).run(transport="stdio")
