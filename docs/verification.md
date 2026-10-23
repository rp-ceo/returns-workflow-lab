# Test results and integration records

## Current offline checks

Run both development sets without an API key:

```sh
python3 evaluate.py --mode demo --suite all
```

| Set | Expected routes matched | Labelled intents matched | Review required but drafted | Unnecessary escalations |
| --- | --- | --- | --- | --- |
| Original 40 cases | 35/40 | Not labelled | 0 | 5 |
| Additional 32 cases | 32/32 | 31/31 | 0 | 0 |

The additional set includes negated returns and problems, broken zips, duplicate billing, mixed requests and English/Spanish wording. One override attempt is blocked before extraction and has no intent label. When payment and damage both occur, the expected primary intent is payment; both require review.

These are authored regression cases used while changing the rules. They are not an independent test set. The five remaining route misses in the original set are paraphrases the offline rules do not recognise, such as “send it back” or “has it arrived yet.” They go to review rather than receiving a draft. The CLI prints every mismatch, and the JSON includes separate intent and route confusion counts. A wrong intent still counts as wrong even if it reaches the expected review queue.

Reports are written to the ignored `runtime/reports/` folder. [CI](https://github.com/rp-ceo/returns-workflow-lab/actions/workflows/checks.yml) runs the offline evaluation and uploads its report as `offline-evaluation`. Another case file can be run with `--cases PATH`; use unique `ticket_id`, `sender_email`, `message`, `expected_route` and, where applicable, `expected_category` fields. Omit the category label for cases deliberately blocked before extraction.

## Recorded model run: 22 October 2026

The [saved report](https://github.com/rp-ceo/returns-workflow-lab/blob/ad173b6b8fe0456fe93cb553c1a51704fa87642e/artifacts/evaluation-live.json) records 40/40 expected routes on the original synthetic set. There were 38 OpenAI Responses API calls using `gpt-6-luna`; all 38 extractions passed schema validation. Two requests stopped at the override check before calling the provider. No review-required case received a draft in that run. Reported usage was 7,573 input and 1,579 output tokens.

This result belongs to the linked historical revision. The extraction prompt and offline rules have since changed. It has not been rerun for the current revision. The report has no expected intent labels, so 40/40 describes routing, not classification accuracy. The set includes the original 14 fixtures. An earlier smoke request failed validation and went to review; it is outside the 40-case report.

## Recorded integration runs

- **n8n 2.44.6:** a EUR 79 order reached draft approval; a EUR 299 order exceeded the EUR 150 review threshold. Repeating the first execution reused the saved case and queue receipt. See the [summary](https://github.com/rp-ceo/returns-workflow-lab/blob/ad173b6b8fe0456fe93cb553c1a51704fa87642e/artifacts/n8n-verification.json), [normal route](https://github.com/rp-ceo/returns-workflow-lab/blob/ad173b6b8fe0456fe93cb553c1a51704fa87642e/artifacts/n8n-return-run.json), [exception route](https://github.com/rp-ceo/returns-workflow-lab/blob/ad173b6b8fe0456fe93cb553c1a51704fa87642e/artifacts/n8n-review-run.json) and [replay](https://github.com/rp-ceo/returns-workflow-lab/blob/ad173b6b8fe0456fe93cb553c1a51704fa87642e/artifacts/n8n-replay-run.json). These records predate attempt-aware retries. The trigger and queues are local fictional examples.
- **GitHub Issues:** the separate workflow created and reused [issue #1](https://github.com/rp-ceo/returns-workflow-lab/issues/1) using offline extraction. The model call and external GitHub write were tested separately, not as a combined live flow.
- **Order lookup:** a separate loopback HTTP service serves fictional orders. Both services are part of this repository. This is not a third-party shop sandbox.

## Failure recovery

A model or order-service failure is saved for review. Repeating the original request returns that saved outcome. After resolving the service problem, an operator can add a reason and choose **Retry processing**. The new attempt uses the original saved message. Previous results and operator actions remain visible, and an earlier approval or queue receipt does not apply to the new attempt.

Recovery tests cover failure followed by success, repeated failures, lost-response replay, old database records, stale operator views and a review saved by another process while a provider call is in progress. HTTP tests exercise the retry endpoint; browser tests exercise the note requirement, attempt history and reuse of a retry ID after a lost response. Provider calls in these tests are mocked.

The per-ticket lock coordinates one server process. Across processes, a database check prevents conflicting attempts or reviews from being overwritten, but two processes may still make duplicate outbound calls before one loses that check. Customer conversation threads and later replies still require a separate design.

## Still missing

There is no real shop or helpdesk connection, operator authentication or customer sending. Third-party authentication, pagination, rate limits, schema changes and webhook redelivery have not been exercised against a shop or helpdesk. Fresh independently labelled requests, including mixed intentions, are still needed before making accuracy claims beyond these development cases.
