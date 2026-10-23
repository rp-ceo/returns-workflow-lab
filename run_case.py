"""Run one fixed synthetic scenario; optionally create a real GitHub review task."""

import argparse
import json
from pathlib import Path
import os

from github_queue import GitHubQueue
from shop_api import sandbox_shop
from workflow import ROOT, load_tickets, process_ticket


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ticket", default="DEMO-005", choices=[t["ticket_id"] for t in load_tickets()]
    )
    parser.add_argument("--mode", choices=("demo", "live"), default="demo")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Create/reuse a review issue in GITHUB_REPOSITORY using GITHUB_TOKEN.",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "runtime/reports/integration-result.json"
    )
    args = parser.parse_args()
    if args.mode == "live" and not os.environ.get("OPENAI_API_KEY"):
        parser.error(
            "Live mode requires an API key. Offline results are not substituted."
        )
    ticket = next(t for t in load_tickets() if t["ticket_id"] == args.ticket)
    with sandbox_shop() as shop:
        result = process_ticket(ticket, args.mode, order_lookup=shop.get_order)
    result["order_source"] = (
        "Separate local sandbox HTTP service, fictional data; not Shopify."
    )
    if args.mode == "live" and result["extraction"] is None:
        result["live_model_verified"] = False
    else:
        result["live_model_verified"] = args.mode == "live"
    result["integration"] = {"status": "not_requested"}
    integration_error = None
    if args.publish:
        try:
            queue = GitHubQueue(
                os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
            )
            result["integration"] = queue.publish_review(result)
            if result["integration"]["status"] in ("created", "reused"):
                result["actions_executed"].append(
                    {"type": "github_review_task", **result["integration"]}
                )
        except (RuntimeError, ValueError) as error:
            integration_error = str(error)
            result["integration"] = {
                "status": "failed_or_unknown",
                "reason": integration_error,
            }
    destination = args.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print("Classifier: " + result["classifier"])
    print("Route: " + result["route"])
    print("GitHub integration: " + result["integration"]["status"])
    if result["integration"].get("url"):
        print("Review task: " + result["integration"]["url"])
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
            summary.write(
                "## ReturnOps scenario\n\n"
                "- Ticket: " + args.ticket + "\n"
                "- Classifier: " + result["classifier"] + "\n"
                "- Outcome: " + result["route"] + "\n"
                "- Review task: "
                + result["integration"].get("url", result["integration"]["status"])
                + "\n\n"
                "Synthetic data. No customer email or refund sent.\n"
            )
    if integration_error:
        raise SystemExit(integration_error)
    if args.mode == "live" and not result["live_model_verified"]:
        raise SystemExit(
            "The live model call did not produce a validated extraction. See the report."
        )


if __name__ == "__main__":
    main()
