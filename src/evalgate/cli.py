import argparse
from html import escape
from importlib.resources import files
import json
from pathlib import Path
import sys

import yaml

from .core import Recording, Report, compare, evaluate, load_suite, read_text


def save(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(text + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="evalgate")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init").add_argument("directory", type=Path, nargs="?", default=Path("."))
    run = commands.add_parser("run")
    run.add_argument("suite", type=Path)
    run.add_argument("--mode", choices=["replay"], default="replay")
    run.add_argument("--trace", required=True, type=Path)
    run.add_argument("--out", required=True, type=Path)
    diff = commands.add_parser("compare")
    for name in ("baseline", "candidate"):
        diff.add_argument("--" + name, required=True, type=Path)
    commands.add_parser("gate").add_argument("--run", required=True, type=Path)
    report = commands.add_parser("report")
    report.add_argument("--run", required=True, type=Path)
    report.add_argument("--format", choices=["html", "json"], default="html")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            examples = files("evalgate").joinpath("examples")
            resources = sorted(examples.iterdir(), key=lambda p: p.name)
            targets = [args.directory / ("suites" if p.name.endswith(".yaml") else "traces") / p.name for p in resources]
            if any(target.exists() for target in targets):
                raise ValueError("Example files already exist")
            for resource, target in zip(resources, targets, strict=True):
                save(target, resource.read_text(encoding="utf-8").rstrip())
        elif args.command == "run":
            result = evaluate(load_suite(args.suite), Recording.model_validate_json(read_text(args.trace)))
            save(args.out, result.model_dump_json(indent=2))
            print(f"{len(result.cases)} cases, {result.pass_rate:.1%} passed")
        elif args.command == "compare":
            changes = compare(*(Report.model_validate_json(read_text(p)) for p in (args.baseline, args.candidate)))
            print(json.dumps(changes, indent=2))
            return int(bool(changes))
        else:
            result = Report.model_validate_json(read_text(args.run))
            if args.command == "gate":
                print("PASS" if result.passed else "FAIL")
                return int(not result.passed)
            if args.format == "json":
                print(result.model_dump_json(indent=2))
            else:
                rows = "".join(f"<tr><td>{escape(row.id)}</td><td>{escape(', '.join(row.failures) or 'Pass')}</td>"
                               f"<td>{row.latency_ms}</td><td>{row.cost_usd:.5f}</td></tr>" for row in result.cases)
                print(f'<!doctype html><meta charset="utf-8"><title>{escape(result.suite)}</title>'
                      f'<h1>{escape(result.suite)}</h1><p>{escape(result.source)} · {result.pass_rate:.1%} passed</p>'
                      f'<table><tr><th>Case</th><th>Failed checks</th><th>Latency (ms)</th><th>Cost (USD)</th></tr>{rows}</table>')
    except (ValueError, OSError, yaml.YAMLError, RecursionError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
