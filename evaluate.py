"""Report intent and route errors separately on labelled, synthetic requests."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from workflow import CATEGORIES, ROOT, DEFAULT_MODEL, process_ticket


ROUTES = {
    "human_review",
    "return_instructions_draft",
    "tracking_update_draft",
    "order_reference_request_draft",
}


def load_cases(path):
    cases = json.loads(path.read_text())
    if not isinstance(cases, list) or not cases:
        raise ValueError("The case file must contain a non-empty JSON list.")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or case.get("expected_route") not in ROUTES:
            raise ValueError("Each case needs a supported expected_route.")
        category = case.get("expected_category")
        if category is not None and category not in CATEGORIES:
            raise ValueError("Unsupported expected_category.")
        ticket_id = case.get("ticket_id")
        if not isinstance(ticket_id, str) or ticket_id in seen:
            raise ValueError("Each case needs a unique ticket_id.")
        seen.add(ticket_id)
    return cases


def confusion(rows, expected, actual):
    counts = Counter((row[expected], row[actual]) for row in rows)
    return [
        {"expected": wanted, "actual": found, "count": count}
        for (wanted, found), count in sorted(counts.items())
    ]


def evaluate_cases(cases, mode="demo", *, processor=process_ticket):
    rows = []
    for case in cases:
        result = processor(case, mode)
        extraction = result["extraction"]
        category = extraction["category"] if extraction else "no_extraction"
        expected_category = case.get("expected_category")
        rows.append(
            {
                "id": case["ticket_id"],
                "message": case["message"],
                "expected_route": case["expected_route"],
                "actual_route": result["route"],
                "matched": result["route"] == case["expected_route"],
                "expected_category": expected_category,
                "actual_category": category,
                "category_matched": (
                    category == expected_category
                    if expected_category is not None
                    else None
                ),
                "validated_live_extraction": mode == "live" and extraction is not None,
                "classification_attempted": result["classification_attempted"],
                "model": result["model"],
                "extraction": extraction,
                "provider_usage": result["provider_usage"],
                "duration_ms": result["duration_ms"],
                "reason": result["reason"],
            }
        )
    labelled = [row for row in rows if row["expected_category"] is not None]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "scope": "Synthetic cases; built-in sets are authored development regressions, not held-out customer data or production accuracy.",
        "case_count": len(rows),
        "route_matches": sum(row["matched"] for row in rows),
        "category_case_count": len(labelled),
        "category_matches": sum(row["category_matched"] for row in labelled),
        "route_confusion": confusion(rows, "expected_route", "actual_route"),
        "category_confusion": confusion(
            labelled, "expected_category", "actual_category"
        ),
        "validated_live_extractions": sum(
            row["validated_live_extraction"] for row in rows
        ),
        "provider_calls_attempted": (
            sum(row["classification_attempted"] for row in rows)
            if mode == "live"
            else 0
        ),
        "model": (
            os.environ.get("OPENAI_MODEL", DEFAULT_MODEL) if mode == "live" else None
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
        "unnecessary_escalations": sum(
            row["expected_route"] != "human_review"
            and row["actual_route"] == "human_review"
            for row in rows
        ),
        "cases": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("demo", "live"), default="demo")
    parser.add_argument(
        "--suite", choices=("original", "challenge", "all"), default="original"
    )
    parser.add_argument(
        "--cases", type=Path, help="Use another labelled JSON case file."
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "live" and not os.environ.get("OPENAI_API_KEY"):
        parser.error(
            "Live evaluation requires OPENAI_API_KEY; no offline substitution."
        )
    try:
        if args.cases:
            cases = load_cases(args.cases)
        else:
            cases = []
            if args.suite in ("original", "all"):
                cases += load_cases(ROOT / "data/evaluation-cases.json")
            if args.suite in ("challenge", "all"):
                cases += load_cases(ROOT / "data/challenge-cases.json")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if args.limit is not None:
        if not 1 <= args.limit <= len(cases):
            parser.error(f"Choose 1–{len(cases)} cases.")
        cases = cases[: args.limit]
    report = evaluate_cases(cases, args.mode)
    suite = "custom" if args.cases else args.suite
    report["suite"] = suite
    suffix = "" if suite == "original" else "-" + suite
    target = (
        args.output or ROOT / "runtime/reports" / f"evaluation-{args.mode}{suffix}.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    for row in report["cases"]:
        if not row["matched"] or row["category_matched"] is False:
            print(
                f"{row['id']}: intent {row['expected_category']} → {row['actual_category']}; "
                f"route {row['expected_route']} → {row['actual_route']}"
            )
    print(f"Routes: {report['route_matches']}/{report['case_count']}")
    print(
        f"Categories: {report['category_matches']}/{report['category_case_count']} labelled cases"
    )
    print(f"Review required but drafted: {report['review_required_but_drafted']}")
    print(f"Unnecessary escalations: {report['unnecessary_escalations']}")
    print(f"Report: {target}")


if __name__ == "__main__":
    main()
