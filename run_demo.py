"""Generate a reproducible report of the offline workflow and its scenario checks."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from workflow import ROOT, load_tickets, process_ticket


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "runtime/reports/demo-results.json"
    )
    args = parser.parse_args()
    results = []
    for ticket in load_tickets():
        result = process_ticket(ticket, "demo")
        result["expected_route"] = ticket["expected_route"]
        result["scenario_passed"] = result["route"] == ticket["expected_route"]
        results.append(result)
    passed = sum(r["scenario_passed"] for r in results)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "offline rules, no AI model calls",
        "scope": "Synthetic scenarios, not a production benchmark.",
        "scenario_checks_passed": passed,
        "scenario_count": len(results),
        "results": results,
    }
    destination = args.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(str(passed) + "/" + str(len(results)) + " offline scenario checks passed.")
    print("Report: " + str(destination))
    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
