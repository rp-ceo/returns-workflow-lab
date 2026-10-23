"""Compare routing on an authored challenge set. Never presents fixtures as real customers."""

import argparse
import json
from pathlib import Path
import os
from datetime import datetime, timezone

from workflow import ROOT, DEFAULT_MODEL, process_ticket


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("demo", "live"), default="demo")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.limit <= 40:
        parser.error("Choose 1–40 cases.")
    if args.mode == "live" and not os.environ.get("OPENAI_API_KEY"):
        parser.error(
            "Live evaluation requires OPENAI_API_KEY; no offline substitution."
        )
    cases = json.loads((ROOT / "data/evaluation-cases.json").read_text())[: args.limit]
    rows = []
    for case in cases:
        result = process_ticket(case, args.mode)
        rows.append(
            {
                "id": case["ticket_id"],
                "message": case["message"],
                "expected_route": case["expected_route"],
                "actual_route": result["route"],
                "matched": result["route"] == case["expected_route"],
                "validated_live_extraction": args.mode == "live"
                and result["extraction"] is not None,
                "classification_attempted": result["classification_attempted"],
                "model": result["model"],
                "extraction": result["extraction"],
                "provider_usage": result["provider_usage"],
                "duration_ms": result["duration_ms"],
                "reason": result["reason"],
            }
        )
        print(
            case["ticket_id"]
            + ": "
            + result["route"]
            + (" [match]" if rows[-1]["matched"] else " [mismatch]"),
            flush=True,
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "scope": "Authored synthetic cases, not held-out customer data or production accuracy.",
        "case_count": len(rows),
        "route_matches": sum(row["matched"] for row in rows),
        "validated_live_extractions": sum(
            row["validated_live_extraction"] for row in rows
        ),
        "provider_calls_attempted": (
            sum(row["classification_attempted"] for row in rows)
            if args.mode == "live"
            else 0
        ),
        "model": (
            os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
            if args.mode == "live"
            else None
        ),
        "reported_token_usage": {
            name: sum((row["provider_usage"] or {}).get(name, 0) for row in rows)
            for name in ("input_tokens", "output_tokens", "total_tokens")
        },
        "review_required_but_drafted": sum(
            row["expected_route"] == "human_review"
            and row["actual_route"] != "human_review"
            for row in rows
        ),
        "cases": rows,
    }
    target = args.output or ROOT / "runtime/reports" / f"evaluation-{args.mode}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(
        str(report["route_matches"])
        + "/"
        + str(len(rows))
        + " expected routes matched; mode="
        + args.mode
    )
    print(
        "Cases requiring review but given a draft: "
        + str(report["review_required_but_drafted"])
    )
    print("Validated live extractions: " + str(report["validated_live_extractions"]))
    print("Report: " + str(target))


if __name__ == "__main__":
    main()
