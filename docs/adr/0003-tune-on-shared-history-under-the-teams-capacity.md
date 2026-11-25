# 0003: Tune on the shared history, under the team's capacity

**Status:** accepted

**Context.** The right thresholds depend on the customer's mix and on how many alerts their analysts can work.

**Decision.** Thresholds are searched on the 45 days of history the customer shares, scored by how many customers
already on their case file the rules reach, subject to expected review time staying under 80% of the team's minutes.
Rules are independent, so each threshold's alerts are computed once and combinations are scored as unions (960
combinations in about a second).

**Consequences.** Tuning never sees the pilot window. Because the case file is incomplete, tuning can trade a little
recall for load; the "Not tuned" ablation shows how much.
