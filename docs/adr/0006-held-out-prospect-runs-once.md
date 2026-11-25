# 0006: The held-out prospect runs once, behind a lock

**Status:** accepted

**Context.** A kit tuned while looking at the prospects it is reported on looks better than it is.

**Decision.** Three development prospects (a German CASP, a UK EMI, a Swiss private bank) are used while building. A
fourth prospect (a Lithuanian payment institution with more mules and scam victims) and 600 webhook scenarios run once
with `ocp heldout`, which writes `reports/heldout.lock` with the config hash first.

**Consequences.** Whatever the held-out run shows stays in the report.
