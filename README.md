# ReturnOps — AI Returns Assistant

A small operations-automation project by Roman Petrov, built with AI coding assistance.

The project follows one support request from intake to a checked response draft or a human-review task. It separates understanding a message from applying store rules, fetching order data and taking an action.

It is an independent learning project inspired by returns operations. All customers, orders and store rules are fictional.

![The local decision desk](docs/demo-screenshot.jpg)

## The process

    Customer request
          ↓
    Validate input and extract intent
          ↓
    Fetch the order through a separate sandbox HTTP service
          ↓
    Check customer, dates, value and country
          ↓
    Prepare a response draft OR create a human-review outcome
          ↓
    In the GitHub demo: create/reuse a real GitHub review issue

The model extracts information. Code enforces policy. The GitHub issue is a real API action on fictional data; order lookup uses a local sandbox API, not Shopify. No emails, shipping labels or refunds are sent.

## Run locally

Python 3.9+; standard library only. No packages to install.

```sh
python3 -m unittest discover -s tests -v
python3 launch_demo.py
```

Open http://127.0.0.1:8765. The launcher starts both the decision desk and the separate fictional order service. The original `python3 app.py` command also works, using local order fixtures unless `ORDER_API_URL` is set.

The web desk stores results in SQLite. Replaying an existing ID returns its saved outcome; reusing that ID with different content is rejected. After changing code or policy, use a new ticket ID to inspect a new outcome. The fictional reference date is fixed at 22 October 2026 for reproducibility.

## Two classifier modes

| Mode | What runs | External model calls |
| --- | --- | --- |
| Offline demo | Small keyword-based baseline | None |
| Live AI | OpenAI Responses API with Structured Outputs | One per new live ticket |

Live mode requires `OPENAI_API_KEY` in the server environment. `OPENAI_MODEL` defaults to `gpt-4o-mini`. `.env.example` is a template; it is not loaded automatically. The API follows the [official Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

Only message text goes to the model. Extracted references and supporting excerpts are validated against that text. Errors and invalid responses go to human review; the app does not substitute offline results for a failed live call. Model confidence is a routing heuristic, not a calibrated probability.

## Run the GitHub integration

Open **Actions → Run an operations scenario → Run workflow**. Choose `DEMO-005` and mode `demo` to test the integration without an LLM key.

The manually triggered workflow:

1. Runs a supplied fictional request through the separate order HTTP service and policy checks.
2. Creates a GitHub issue when a person needs to review it, including the reason, checks and trace.
3. Reuses the existing issue on a repeated scenario instead of opening another one.
4. Saves a JSON report as a downloadable Actions artifact.

The workflow uses GitHub's short-lived repository token with `contents: read` and `issues: write`. It runs only when manually started by the repository owner. It accepts only the supplied scenario IDs and publishes only fictional `example.com` tickets.

For mode `live`, the owner must first configure the `OPENAI_API_KEY` repository secret. A live run fails visibly when a validated model result is unavailable.

The equivalent command is `python3 run_case.py --ticket DEMO-005 --mode demo --publish`, with `GITHUB_REPOSITORY` and `GITHUB_TOKEN` provided by GitHub Actions. The same command without `--publish` exercises the HTTP workflow locally without writing to GitHub.

Deduplication searches for a stable ticket marker and payload hash. Demo runs are serialized. This is a bounded demonstration, not a transactional guarantee across independent workers or an unlimited issue history. Unknown POST outcomes are not blindly retried.

## Evidence and evaluation

| Check | Current evidence |
| --- | --- |
| Automated tests | 27 passed locally, including real loopback HTTP tests |
| Original business scenarios | 14/14 expected routes matched offline |
| Broader challenge set | 34/40 expected routes matched offline; 0 review-required cases drafted in this set |
| Live AI | API integration implemented; a real provider call has not yet been verified |
| GitHub review-task API | Code and tests implemented; see the integration report for the verified run status |

```sh
python3 run_demo.py
python3 evaluate.py --mode demo
python3 run_case.py --ticket DEMO-005 --mode demo
```

The 40-case set includes English/Spanish requests, paraphrases, negation, missing references, mismatched customers and policy exceptions. Six route mismatches remain in the offline baseline; inspect `artifacts/evaluation-demo.json`. These authored synthetic examples are not held-out customer data, production accuracy, autonomous-resolution rate or measured time savings.

With a configured API key, `python3 evaluate.py --mode live --limit 5` runs a small live comparison. This makes paid provider calls. A full 40-case comparison should be run deliberately after checking model access and budget.

## Read the business case

[Problem, scope, measurements and rollout](docs/business-case.md) explains which work the automation could remove and how to judge whether it actually helps. [Demo guide](docs/demo-guide.md) provides a short walkthrough.

## Main files

- `workflow.py`: extraction, policy checks, routing and local persistence.
- `shop_api.py`: separate fictional order HTTP service and validated client.
- `github_queue.py`: real GitHub review-task integration.
- `run_case.py`: complete scenario and integration report.
- `evaluate.py`: expected-versus-actual routing comparison.
- `web/`: local browser interface.
- `.github/workflows/`: checks and manually triggered integration demo.

## Boundaries

This project does not include a production merchant integration, authenticated shopper identity, automated refunds, a calibrated model-confidence score or a comprehensive prompt-injection defence. Draft preparation is not autonomous resolution. A production rollout would require real policies/data, reviewed permissions, operational monitoring and a measured pilot. The local servers are intended for loopback use only.
