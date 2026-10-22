# Live verification

The report was produced by an actual run of `python3 evaluate.py --mode live` using OpenAI Responses API and `gpt-6-luna`, with reasoning disabled. No offline classifier was substituted for provider responses.

- Run timestamp: 2026-10-22T22:38:32.630554+00:00 (UTC).
- Authored synthetic cases: 40.
- Expected routes matched: 40/40.
- Model calls attempted: 38. All 38 produced validated extractions.
- Two messages were stopped by the instruction-override check before calling the model.
- Cases expected to require human review but given a draft: 0 in this set.
- Reported input tokens: 7,573; output tokens: 1,579.

[Inspect every saved result](../artifacts/evaluation-live.json). The report includes messages, extracted categories and evidence, routes, latency and provider token counts. All messages are fictional.

An earlier smoke request failed output validation and went to human review. That attempt is outside this 40-case run. Model outputs can vary; the evaluation is evidence for this run, not a guarantee of future behaviour.

## Interfaces checked

The browser workflow was also tested with a real AI call and a separate loopback order service. The model extracted the return request; the application checked the fictional order and prepared a draft. The screenshot in the main README shows that run.

The separate GitHub Issues integration was verified in offline mode: [task #1](https://github.com/rp-ceo/returns-workflow-lab/issues/1) was created and reused on rerun. The live model and the GitHub write were checked separately; this is not a claim that a live cloud workflow has already combined both.

## Interpretation

This is a small authored scenario set, including the original 14 fixtures. It is not held-out customer data. It does not measure production accuracy, actual customer satisfaction, time saved or autonomous ticket resolution. Response drafts have not been sent to customers.

At the [published Standard short-context rates](https://developers.openai.com/api/docs/models/gpt-6-luna) of $0.10 per million input tokens and $0.50 per million output tokens, the reported tokens in this one evaluation correspond to approximately $0.00155 before any taxes. This estimate excludes separate smoke/UI calls and is not an account invoice.
