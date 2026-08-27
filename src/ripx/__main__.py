"""Command-line entry point for RIP-X baseline experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ripx.analytics.experiment import run_scenario, save_result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a reproducible RIP-X scenario.")
    parser.add_argument("scenario", type=Path, help="path to a JSON scenario file")
    parser.add_argument("--output", type=Path, help="optional path for the JSON report")
    arguments = parser.parse_args()
    result = run_scenario(arguments.scenario)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        save_result(result, arguments.output)
        print(f"Saved report to {arguments.output}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
