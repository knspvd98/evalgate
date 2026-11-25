import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")]


class Call(Model):
    name: Identifier
    arguments: dict[str, JsonValue]


class Case(Model):
    id: Identifier
    input: str = Field(min_length=1)
    expected: dict[str, JsonValue] = Field(min_length=1)
    tools: list[Call]
    evidence: list[str] = Field(default_factory=list)
    abstain: bool
    max_latency_ms: int = Field(ge=0)
    max_cost_usd: float = Field(ge=0)


class Suite(Model):
    suite: Identifier
    version: int = Field(ge=1)
    min_pass_rate: float = Field(ge=0, le=1)
    forbidden_tools: list[Identifier]
    cases: list[Case] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def check_cases(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate case IDs")
        if any(call.name in self.forbidden_tools for case in self.cases for call in case.tools):
            raise ValueError("A forbidden tool appears in expected calls")
        return self


class Trace(Model):
    id: Identifier
    output: dict[str, JsonValue]
    calls: list[Call]
    evidence: list[str]
    abstained: bool
    latency_ms: int = Field(ge=0)
    cost_usd: float = Field(ge=0)


class Recording(Model):
    source: str = Field(min_length=1)
    traces: list[Trace] = Field(max_length=10000)


class CaseResult(Model):
    id: Identifier
    failures: list[Literal["output", "tool_sequence", "tool_arguments", "forbidden_action",
                           "evidence", "abstention", "latency", "cost"]]
    latency_ms: int
    cost_usd: float


class Report(Model):
    suite: Identifier
    version: int
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: str
    min_pass_rate: float = Field(ge=0, le=1)
    cases: list[CaseResult] = Field(min_length=1)

    @property
    def pass_rate(self):
        return sum(not row.failures for row in self.cases) / len(self.cases)

    @property
    def passed(self):
        return self.pass_rate >= self.min_pass_rate and all("forbidden_action" not in row.failures for row in self.cases)


def read_text(path: Path):
    with path.open("rb") as stream:
        data = stream.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError(f"Input exceeds 2 MB: {path.name}")
    return data.decode("utf-8")


def load_suite(path: Path):
    text = read_text(path)
    if any(isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)) for token in yaml.scan(text)):
        raise ValueError("Suite aliases and anchors are unsupported")
    return Suite.model_validate(yaml.safe_load(text))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def evaluate(suite, recording):
    traces = {trace.id: trace for trace in recording.traces}
    if len(traces) != len(recording.traces) or traces.keys() != {case.id for case in suite.cases}:
        raise ValueError("Recording must contain each suite case exactly once")
    results = []
    for case in suite.cases:
        trace = traces[case.id]
        names = [call.name for call in trace.calls]
        checks = {
            "output": canonical(trace.output) == canonical(case.expected),
            "tool_sequence": names == [call.name for call in case.tools],
            "tool_arguments": canonical([c.arguments for c in trace.calls]) == canonical([c.arguments for c in case.tools]),
            "forbidden_action": not set(names).intersection(suite.forbidden_tools),
            "evidence": set(trace.evidence) == set(case.evidence),
            "abstention": trace.abstained == case.abstain,
            "latency": trace.latency_ms <= case.max_latency_ms,
            "cost": trace.cost_usd <= case.max_cost_usd,
        }
        results.append(CaseResult(id=case.id, failures=[name for name, ok in checks.items() if not ok],
                                  cost_usd=trace.cost_usd, latency_ms=trace.latency_ms))
    return Report(suite=suite.suite, version=suite.version, source=recording.source,
                  fingerprint=hashlib.sha256(canonical(suite.model_dump()).encode()).hexdigest(),
                  min_pass_rate=suite.min_pass_rate, cases=results)


def compare(baseline, candidate):
    if baseline.fingerprint != candidate.fingerprint:
        raise ValueError("Reports must come from the same reviewed suite")
    before = {row.id: set(row.failures) for row in baseline.cases}
    after = {row.id: set(row.failures) for row in candidate.cases}
    if before.keys() != after.keys() or len(before) != len(baseline.cases) or len(after) != len(candidate.cases):
        raise ValueError("Report case IDs do not match")
    return {key: sorted(after[key] - before[key]) for key in before if after[key] - before[key]}
