# Business case: reduce repeated work in returns support

## The problem

A support agent receiving a return question often repeats the same sequence: identify the request, find the order, check status and policy, then write a reply or ask another team to investigate. The opportunity is to remove predictable lookup and preparation work while retaining human judgment where the data or decision is uncertain.

## First useful scope

Start with order-status questions and straightforward return-instruction requests. Keep damage, payment disputes, mismatched identities, high-value orders and ambiguous cases in a review queue.

| Request | Data needed | Outcome demonstrated here |
| --- | --- | --- |
| Where is my order? | Matching order and shipment status | Tracking response draft |
| I want to return this item | Matching order, delivery date, fictional policy | Return-instructions draft |
| I cannot find my order number | Customer message | Draft asking for the reference |
| Damaged item, duplicate charge or failed check | Message and available context | Human-review task |

The language model handles varied wording. Deterministic code applies the rules. A separate order service supplies order facts. A review task includes the reason and context so the next person does not repeat the initial investigation.

## What to measure in a real pilot

- **Correct routing:** compare outcomes against a human-reviewed set of historical requests.
- **True autonomous resolution:** resolved requests without staff intervention divided by all relevant inbound requests, using an agreed definition of resolution and a reopening window.
- **Incorrect automation:** cases routed or answered incorrectly, especially cases that should have gone to a person.
- **Manual effort:** handling minutes before versus after, including review and maintenance work.
- **Customer outcome:** satisfaction, repeat contacts and escalations, alongside speed.

Drafts are not resolutions. A fast answer that causes a second contact can increase work.

## Illustrative economics, not measured impact

Suppose a team receives 1,000 requests in a week, including 300 repetitive status questions. Resolving half of those status questions would cover 150 requests, or 15% of total inbound. At five manual minutes per request, gross time avoided would be 12.5 hours. Review, monitoring and maintenance time must be subtracted. These are example assumptions, not REVER volumes or project results.

## A sensible first week

1. Review a sample of requests with an operator; identify common types and exceptions.
2. Map where the required facts live and who owns each decision.
3. Pick one frequent, low-risk type and define its allowed actions.
4. Build and test against examples, keeping failures visible.
5. Run in draft mode, have an operator compare decisions, and revise the rules.
6. Introduce limited automation only after agreeing quality thresholds and a way to stop or reverse it.

## Evidence from this project

The local offline classifier matched 34 of 40 expected routes on the authored synthetic challenge set. It misses some paraphrases and negation. The same 40 authored cases were subsequently run in live mode: 40 expected routes matched, with 38 validated model extractions and two pre-model safety stops. Actual local n8n runs also verified the draft route, the high-value exception and replay without repeated processing. See [the verification notes](live-verification.md). These are small synthetic demonstrations, not production accuracy or measured customer outcomes.

The GitHub integration is a demonstration of handing off a real task through an external API. GitHub is used as an accessible test queue; this does not imply that REVER uses GitHub for customer support.

Role context: [REVER Global Operations & AI Intern](https://www.ycombinator.com/companies/rever/jobs/bClINAp-global-operations-ai-intern).
