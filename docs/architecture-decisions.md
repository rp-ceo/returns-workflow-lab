# Design decisions

## Start with one workflow

Returns support is a useful operations problem because the message, order record and merchant policy can disagree. The first useful output is a checked next step with a clear owner. This project covers returns and delivery questions; it does not attempt to replace a whole support team.

## Keep business authority outside the model

The model extracts intent, order reference, evidence and a confidence heuristic. Code validates that output and checks a fictional 30-day window, customer-email consistency, delivery state, supported countries and a EUR 150 review threshold. A model cannot change those rules through a customer message.

Matching a supplied email to an order is a consistency check, not proof of identity. Production would use an authenticated customer context. The injection prefilter covers examples in this set; it is not comprehensive protection.

## Use n8n for the hand-off

The imported workflow makes the trigger, service call and routing branch inspectable. Python keeps the policy and state in one place, so the browser and n8n cannot drift into different policy implementations. n8n is genuinely executed, but its destination is a saved local queue receipt. Connecting a real helpdesk would be a separate integration step.

A direct Python workflow would also work. n8n adds an explicit integration layer that an operations team could modify. Adding both Zapier and n8n would duplicate that responsibility without helping this narrow case.

## Do not add a second support platform just for its name

GuruSup could be appropriate for an existing team's agent configuration and support tooling. This independent prototype has no access to REVER's account, customer knowledge base or helpdesk. Claiming that integration would be misleading. The transferable work here is process analysis, tool calls, policy handling, escalation, evaluation and an operator's next action.

## Save decisions, not just outputs

A retry should not call the model or create the same task again. Stable request/event IDs, payload hashes and saved outcomes handle that locally. Review revisions reject stale browser decisions. These are practical safeguards for a small single-store demonstration, not a claim of distributed exactly-once execution.

## Measure usefulness in a real pilot

The next step would be a permissioned sample of real, anonymised cases, reviewed by an operator. First run in shadow mode and compare the suggested route and draft to the operator's decision. Measure handling time, edit rate, missed exceptions and reopen rate. Agree on acceptable errors before expanding scope. No such customer pilot or time-saving claim has been made here.
