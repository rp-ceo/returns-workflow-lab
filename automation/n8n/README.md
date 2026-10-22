# Local n8n orchestration

Tested with **n8n 2.44.6 / Node.js 24.19.0**. The Python desk must run on the same host at http://127.0.0.1:8765. No n8n Cloud account is required for this local demonstration.

## Import and execute

Install the pinned n8n package in a local tools directory, following the [official npm installation instructions](https://docs.n8n.io/hosting/installation/npm/). The commands below assume `n8n` is available on your PATH.

In terminal one, from the repository:

```sh
python3 launch_demo.py
```

For real extraction, configure the backend's ignored `.env.local` with your own `OPENAI_API_KEY`. Do not put it into workflow JSON. The key stays in the Python service.

In terminal two:

```sh
n8n import:workflow --input=automation/n8n/returns-triage.json
n8n import:workflow --input=automation/n8n/high-value-review.json
n8n execute --id=ReturnOpsLive001 --rawOutput
n8n execute --id=ReturnOpsLive002 --rawOutput
n8n execute --id=ReturnOpsLive001 --rawOutput
```

Use one consistent local `N8N_USER_FOLDER` if you change the default. That folder contains n8n configuration and must stay private. If using a container, loopback inside the container is not the host: adapt the service address deliberately rather than exposing the desk publicly.

## Nodes and outcomes

1. **Manual Trigger** starts a reproducible sample.
2. **Set** supplies the fictional ticket and `mode: live`.
3. **HTTP Request** calls `/api/process`. Python performs extraction, order lookup and policy checks.
4. **If** branches on `route === human_review`.
5. The matching **HTTP Request** calls `/api/dispatch`, saving an `exceptions` or `draft_approval` receipt.

Only one branch runs in each execution. Saved receipts show the branch actually taken. This is a local queue hand-off, not a connected email, payment or production helpdesk action.

- `N8N-RETURN-001`: alex@example.com, ORD-1001, EUR 79 → draft approval.
- `N8N-REVIEW-001`: leo@example.com, ORD-1004, EUR 299 → exception review above the EUR 150 threshold.

To test the rules without a funded model account, change the Set node's mode to `demo` before executing. That uses the baseline, not AI.

## Retries and changes

The fixed ticket IDs make repeats free of additional processing. Dispatch IDs include queue, mode and ticket ID. Reusing an ID with different content is rejected. To test new content or a changed policy, give the sample a new ticket ID. Case history is in the Python application's SQLite store, not the workflow file.

The [verification summary](../../artifacts/n8n-verification.json) links three whitelisted execution records: normal route, exception route and replay. These contain only fictional payloads and node results. They exclude n8n's private configuration and credentials.
