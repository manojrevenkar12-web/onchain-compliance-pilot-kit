# 0002: Compile rules from discovery notes, refuse what cannot be compiled safely

**Status:** accepted

**Context.** Vendor default rules alert on any exposure to any risky category at any share. Teams then either drown
or switch rules off by hand, without a record of why.

**Decision.** The customer's risk appetite (prohibited, high risk, restricted, maximum hops) compiles into a short,
readable rule list: prohibited exposure at any amount, indirect exposure above a share, high-risk direct exposure
above an amount per segment, and behavioural rules (24-hour totals to restricted categories, structuring under the
travel-rule threshold, rising payments to a new payee, pass-through of risky deposits). Unknown or contradictory
categories are refused; a severe category missing from the risk appetite is added as prohibited with a note for the
customer to confirm.

**Consequences.** The pilot plan shows the rules in the customer's own terms. A typo in discovery notes fails loudly.
