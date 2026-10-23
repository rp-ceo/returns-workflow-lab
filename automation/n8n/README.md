# n8n workflows

I use n8n to pass a request to the Python service and route its saved decision to the right queue. The two workflows use a manual trigger and fictional orders. I tested them locally with n8n 2.44.6 and Node 24.19.0.

## Run

Start the Python service from the repository:

```sh
python3 launch_demo.py
```

Install n8n locally using the [npm setup instructions](https://docs.n8n.io/hosting/installation/npm/), then import and execute:

```sh
n8n import:workflow --input=automation/n8n/returns-triage.json
n8n import:workflow --input=automation/n8n/high-value-review.json
n8n execute --id=ReturnOpsLive001 --rawOutput
n8n execute --id=ReturnOpsLive002 --rawOutput
```

The workflows default to `mode: live`. Set the Python service's key in the ignored `.env.local`, or change the Set node to `mode: demo` to run without a model account. Credentials do not belong in workflow JSON.

Both workflows call http://127.0.0.1:8765. If n8n runs in a container, change that address to reach the host. Keep the desk private. If you set `N8N_USER_FOLDER`, keep that directory out of git; it holds n8n's private configuration.

## Steps

1. **Manual Trigger** starts the sample.
2. **Set** supplies the ticket, sender, message and classifier mode.
3. **HTTP Request** calls `/api/process` for extraction, order lookup and policy checks.
4. **If** branches on `route === human_review`.
5. **HTTP Request** calls `/api/dispatch` to save an `exceptions` or `draft_approval` receipt. The desk's Workflow page shows saved hand-offs.

`ReturnOpsLive001` uses a EUR 79 order and reaches draft approval. `ReturnOpsLive002` uses a EUR 299 order, above the EUR 150 threshold, and reaches exception review.

## Replays

Repeat an execution to reuse the saved ticket and dispatch receipt. Reusing an ID with changed content is rejected. Use a new ticket ID after changing the message or policy. A queue receipt is a local record, not an email, refund or helpdesk integration.
