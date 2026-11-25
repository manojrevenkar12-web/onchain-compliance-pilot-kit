# 0001: Simulated prospects with hidden truth, and the same luck for every design

**Status:** accepted

**Context.** A pilot has to show a compliance team that the setup catches what matters without drowning them. On
real data you never know which customers you missed. A simulated prospect knows: which customers are mules, scam
victims, structurers or sanctions evaders, which counterparties the intelligence attributes and when.

**Decision.** `ocp.world` generates each prospect's customers and transfers from its discovery notes (size,
segments) and `world.yml` (customer types, counterparty categories, attribution coverage and lag). The kit sees the
book, screening results as of an hour, and the customer's existing case file (80% of past reportable customers).
Randomness is keyed so every design sees the same world.

**Consequences.** Differences between designs come from the designs. The numbers are as good as the generator; the
README lists what it leaves out.
