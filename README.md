# ReturnOps

I built ReturnOps to organise return requests and order-status questions in one workspace. It reads the customer's message, checks the order and store policy, and prepares a reply or sends the case for review. An operator can edit the draft, record a decision and see the history.

All customer records and store rules are fictional. The app does not send messages, issue labels or move money.

![Returns inbox](docs/operations-workspace.jpg)

## How it works

1. A request arrives through the desk or an n8n workflow.
2. Python validates it. The offline mode uses keyword rules; live mode asks OpenAI for structured intent, order reference and supporting text.
3. A separate local HTTP service supplies the order. Python checks the sender, delivery date, return window, order value and country.
4. The case reaches draft approval or exception review. SQLite stores the outcome and subsequent operator decisions.

I kept policy decisions in Python and replies in [templates](drafts.py). The model cannot change the policy or execute merchant actions. n8n handles the HTTP calls, routing and queue hand-off. The browser interface uses plain HTML, CSS and JavaScript.

## Run locally

Python 3.9 or later. The app itself has no third-party Python dependencies.

```sh
python3 launch_demo.py
```

Open http://127.0.0.1:8765 and click **Load sample queue**. This runs without an API key. The launcher starts both the desk and the fictional order service on loopback. `python3 app.py` starts the desk alone, using local order fixtures.

For live extraction, copy `.env.example` to `.env.local` and add an OpenAI API key. The file is ignored by git and loaded at startup; existing environment variables take precedence. The default model is `gpt-6-luna`, with a 400-token output limit. Live mode makes paid API calls. Only the message text is sent to OpenAI.

To run the two n8n scenarios, follow the [local setup guide](automation/n8n/README.md).

## Retries and reviews

The same ticket ID and content reuse a saved outcome. Changing the content requires a new ID. Different tickets process concurrently; simultaneous retries of one ticket share a lock in the server process. No global or database lock is held during a model call. Separate server processes may still make duplicate model calls, although only one outcome can be saved.

Review actions also have stable IDs and revision numbers. A stale browser cannot overwrite a newer decision. Exceptions require a note, and approving a draft only records approval.

## Checks

```sh
python3 -m unittest discover -s tests -v
python3 run_demo.py
python3 evaluate.py --mode demo
python3 run_case.py --ticket DEMO-005 --mode demo
```

Reports go to the ignored `runtime/reports/` directory. Each script accepts `--output PATH`. To save a model evaluation for the desk's **Verification** page, run `python3 evaluate.py --mode live`; this makes up to 40 paid calls. The 40 authored cases are examples, not a measure of production accuracy. The offline classifier does not match every expected route.

Frontend tests run the interface in jsdom:

```sh
npm ci --ignore-scripts
npm test
npm run format:check
```

Python formatting uses `python3 -m pip install -r requirements-dev.txt`, then `python3 -m black --check .`. CI checks Python 3.9, 3.11 and 3.14, plus the frontend on Node 24. Pull requests run the checks; older runs are cancelled when a newer commit arrives.

## Scope

I use a fixed reference date of 22 October 2026 for repeatable return-window checks. Sender-email matching is a fixture check, not customer authentication. The override-phrase filter catches some suspicious messages; it is not comprehensive prompt-injection protection. Schema validation, order checks, fixed templates and operator approval remain in place even when a phrase is missed.

This is a local prototype without operator accounts or a production shop connection. I would add authentication, monitoring and real merchant policies before connecting it to customer systems.

A separate, manually triggered GitHub Actions scenario can create or reuse an issue for a fictional review case. It needs `issues: write` and never sends customer messages. Live mode in Actions needs an `OPENAI_API_KEY` repository secret; local keys stay local.

[MIT licence](LICENSE) · [n8n workflows](automation/n8n)
