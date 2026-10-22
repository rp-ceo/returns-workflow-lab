# Returns Workflow Lab

A small operations-automation prototype by Roman Petrov, built with AI coding assistance.

It takes a return or delivery request, extracts its intent, looks up a synthetic order, applies a fictional store policy, and prepares either a response draft or a human-review task. It is an independent learning project, not a REVER product or a production customer deployment.

![The local workflow interface after processing synthetic requests](docs/demo-screenshot.jpg)

## What works

- A local web interface for individual tickets and a batch of 14 synthetic scenarios.
- Order lookup, customer-email consistency checks, return-window checks, value thresholds and country routing.
- Response drafts and a review queue with an execution trace.
- SQLite persistence and duplicate-request handling. A repeated ticket does not run the classifier again; reusing its ID with different content returns a conflict.
- An optional OpenAI Responses API extraction step using Structured Outputs and application-side validation.
- A clearly labelled offline classifier so the workflow can be tried without API access.
- 15 automated tests covering 14 business scenarios plus boundary conditions, identity mismatch, model failures, invented references, invalid confidence scores and duplicate requests.

## Try it in two commands

Requires Python 3.9 or later. The project uses the standard library; there are no packages to install.

    python3 -m unittest discover -s tests -v
    python3 app.py

Open http://127.0.0.1:8765 and click **Run 14 demo scenarios**. Select requests in the decision desk to inspect the checks and routing.

To generate the offline scenario report:

    python3 run_demo.py

The report is saved to artifacts/demo-results.json. Passing these fixtures is a workflow check, not a claim about model accuracy, time saved, customer satisfaction or production performance.

## Two distinct modes

| Mode | Intent extraction | External calls |
| --- | --- | --- |
| Offline demo | A small keyword-based baseline | None |
| Live AI | OpenAI Responses API with a strict JSON schema | One model request for each new live ticket |

Offline results are never presented as model results. Live mode appears in the interface only when the server has an API key.

To enable live AI locally, set OPENAI_API_KEY in your terminal environment and restart the server. OPENAI_MODEL is optional and defaults to gpt-4o-mini. The .env.example file is only a template: the app does not automatically load it. Never commit an actual API key.

Only the customer message goes to the model. Use the supplied fictional messages. A successful model response must still pass schema, reference and evidence validation. Provider failures become review tasks instead of fabricated answers. To retry a failed live classification, submit a new ticket ID; an existing ID deliberately replays its stored outcome.

The integration follows the [official Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

## The workflow

    Ticket intake
         ↓
    Validate input and detect a simple instruction-override pattern
         ↓
    Extract category, order reference, language, confidence and evidence
         ↓
    Validate the extraction and look up the synthetic order
         ↓
    Apply deterministic customer / date / value / country checks
         ↓
    Prepare a response draft OR create a human-review outcome
         ↓
    Save the result and execution trace in SQLite

The model is used for understanding text. It does not decide store policy, issue labels, send emails or move money. Passing initial checks produces a draft, not approval of a real refund.

## Example cases

| Request | Expected outcome |
| --- | --- |
| Normal return within the fictional 30-day window | Return instructions draft |
| Delivery-status question for a matching customer | Tracking update draft |
| No order reference | Request the reference |
| Return outside the window | Human review |
| High-value order, damaged item or duplicate charge | Human review |
| Different customer email, unknown order or conflicting references | Human review |
| Instruction to bypass policy | Human review |

The store, customers, orders, thresholds and reference date of 22 October 2026 are fictional. The prompt-injection pattern is a small demonstration, not a comprehensive defence. A model's confidence score is a routing heuristic, not a calibrated probability.

## Main files

- app.py — local HTTP interface and endpoints.
- workflow.py — extraction, policy checks, routing and SQLite storage.
- data/ — fictional orders, policy and example tickets.
- web/ — browser interface.
- tests/test_workflow.py — repeatable workflow checks.
- docs/demo-screenshot.jpg — the local interface after processing synthetic scenarios.

## Honest scope

This project was assembled with AI coding assistance as a new personal learning exercise. It is not evidence of previous professional automation work, independent software-engineering expertise, access to REVER systems, or production results. The repository separates implemented behaviour from external integrations and future work.

### Verification status

- Offline business scenarios: 14/14 passed locally.
- Automated tests: 15/15 passed locally.
- Browser workflow: batch execution, decision details and repeat-ticket behaviour checked locally.
- Live AI: integration implemented; a real provider call has not yet been verified in this version.
- Real email, CRM, shipping and refund integrations: not implemented.

## What a production version would need

Authenticated customer identity; real, versioned merchant policies; reliable order and carrier APIs; a reviewed dataset for evaluating model behaviour; access controls; personal-data handling rules; a durable queue and retry strategy; operational monitoring; and explicit approval gates for customer-facing or financial actions. The local server is not intended to be exposed publicly.
