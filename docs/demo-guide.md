# Five-minute walkthrough

## 1. Explain the operating problem

A support request needs more than a plausible reply. The operator needs the right order, the merchant's rules, a clear next step and a record of what happened. This prototype prepares that decision using fictional data.

## 2. Open the inbox

Run `python3 launch_demo.py`, open http://127.0.0.1:8765 and click **Load 14 baseline cases**. Select the EUR 79 return and inspect the customer message, order and eight checks. This mode uses keyword rules, not AI.

Click **New request**, choose the same scenario, use a fresh ticket ID and select **Live AI** if a funded backend key is configured. Only this explicit submission calls the provider.

## 3. Make an operator decision

Edit the response draft, leave a review note and click **Approve draft**. Reload the page: the text, status and activity remain. No message is sent.

Select the EUR 299 order. It exceeds the fictional EUR 150 threshold. There is no automatic draft to approve. Add the next step in the note and click **Mark reviewed**. Reviewing the case records a decision; it does not issue a refund.

## 4. Show actual orchestration

Open **Automation** for the workflow map and saved receipts. The diagram is the application's explanation of the imported workflow, not a screenshot of the n8n editor.

Follow [the n8n instructions](../automation/n8n/README.md) to execute the two workflows. n8n calls Python, branches on the saved outcome and records the queue hand-off. Repeat the first workflow: it should reuse both the processed case and dispatch event without another model call.

## 5. Discuss a result and a limit

Open **Checks & evidence** or `artifacts/evaluation-live.json`. The actual live run matched 40/40 expected routes on authored synthetic examples. The baseline matched 34/40, with failures on language it did not understand. These results do not establish production accuracy or time saved.

The separate GitHub Actions demo creates or reuses a real review issue in offline mode. That external write and the live AI+n8n paths were tested separately.

## Make one personal change before presenting

Understand and run the project yourself. One useful experiment: change `manual_review_above_eur` from 150 to 50 in `data/policy.json`. Submit a **new** ticket ID for the EUR 79 order: it should now need review. Restore 150 afterwards. Old IDs intentionally retain their saved result.

Explain which part you changed and observed. The code was built with AI coding assistance. Be precise about your own contribution and do not claim production deployments or independent authorship of code you cannot explain.
