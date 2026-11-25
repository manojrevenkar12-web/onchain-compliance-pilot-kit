# 0005: Signed webhooks applied once and in order

**Status:** accepted

**Context.** Polling for alerts adds delay; webhooks arrive duplicated, out of order and sometimes forged, and a
receiver can die after committing and before answering.

**Decision.** HMAC-SHA256 over timestamp and body with a five-minute window; the event id recorded in the same
SQLite transaction as its effect; an older version never overwrites a newer one; the first event for an alert opens
its case and ticket; the sender retries with backoff until it gets an answer.

**Consequences.** The webhook lab breaks nothing with the full receiver, and removing any one safeguard breaks
scenarios: forged cases, events logged twice, cases left at an older version, alerts lost.
