# 0004: Governed AI triage: evidence packs, cited drafts, hard rules before the score

**Status:** accepted

**Context.** Most review time goes into gathering evidence across tools. An agent can do that and draft a
disposition, but a confident wrong draft pulls analysts with it, and an agent closing alerts on its own loses
reportable customers.

**Decision.** For each alert the kit builds an evidence pack (alert, exposure, customer profile, last 7 days, earlier
alerts, score), a gradient-boosted model trained on the shared history scores it, and a drafter writes a disposition
in which every sentence cites evidence. Code routes: prohibited categories, behavioural alerts and amounts of EUR
10,000 or more always get a full review; low scores otherwise go to a fast lane with 10% sampled for a full review;
the analyst decides everything else. Any drafter, including an LLM, must pass the citation and number check or is
replaced by the template.

**Consequences.** The simulation models anchoring: analysts are right 96% of the time with a right draft and 80% with
a wrong one. The ungoverned ablation shows what letting the score close alerts costs.
