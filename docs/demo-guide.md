# Five-minute walkthrough

1. Run `python3 launch_demo.py` and open http://127.0.0.1:8765. The header should say **Sandbox HTTP API**.
2. Process a fresh ticket based on `DEMO-001`. Explain how the order service, identity consistency check and fictional return rules lead to a draft. Nothing is sent.
3. Process a fresh ticket based on `DEMO-005`. Explain why the high value requires a person.
4. Open the **Run an operations scenario** workflow in GitHub Actions. Run `DEMO-005` in `demo` mode. Inspect its summary and the resulting review issue. This is a real GitHub action using a rules-based classifier.
5. Rerun the same scenario. The integration should reuse the issue. Explain why an unreliable network must not cause repeated tasks.
6. Open `artifacts/evaluation-demo.json`. Show one failure on negation or paraphrasing. Explain why a live model comparison is still needed.

## Before presenting it as your project

Personally run the workflow, inspect a failure, make a small change and verify its effect. Be able to identify the code that performs the lookup, the checks and the API action. The code was built with AI coding assistance; do not claim independent authorship of unfamiliar parts.

## Explain the design

- Why separate understanding from policy? A plausible model answer is not authority to approve a refund.
- Why a review queue? Missing data and exceptions still need an owner and a next action.
- Why separate order service? To demonstrate a real HTTP integration boundary and failure handling without needing a retailer's private systems.
- Why GitHub? To make the external task creation visible and reproducible with repository-scoped credentials.
- What is not verified? The evidence table in the README separates offline checks, actual API actions and live model status.

## A useful personal change

In `data/policy.json`, change `manual_review_above_eur` from 150 to 50. Submit a new ticket ID for the €79 order. It should now need review. Restore 150 afterwards. Results with an old ID deliberately remain unchanged.
