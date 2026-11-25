# SKILLS.md

Repeatable tasks, with the command and the check that tells you it worked.

## Onboard a new prospect after discovery
1. Write `config/prospects/<name>.yml` from the discovery call: risk appetite (prohibited, high risk, restricted,
   hops), travel-rule threshold, review team and office hours, escalation deadline, success criteria.
2. `python -m ocp.cli plan config/prospects/<name>.yml` prints the compiled rules and any notes to confirm with the
   customer (for example a severe category missing from the risk appetite).
3. `python -m ocp.cli dev` replays and scores it; `reports/pilots/<name>.md` is the pilot plan to send.

## Change a threshold, route or minute estimate
Edit `config/kit.yml`, run `python -m ocp.cli dev && python -m ocp.cli gate dev`, and commit the regenerated reports.

## Add a rule
1. Add it to `Policy` and `Policy.rules()` in `ocp/kit/policy.py` with its setting in `kit.yml`.
2. Implement it in `ocp/kit/engine.py` (screening rules vectorised, behavioural rules per customer).
3. Add a unit test in `tests/test_engine.py` with a hand-built book that fires it and one that does not.

## Plug in an LLM drafter
Write a function with the `Drafter` signature in `ocp/kit/triage.py` and pass it to `draft_checked`. It must pass
`check_draft`: every sentence cites evidence ids that exist, every number appears in the cited evidence. Add a test
with a drafter that invents a number and check the template draft replaces it.

## Add a receiver safeguard to the webhook lab
Add a field to `Safeguards` in `ocp/kit/webhooks.py`, a variant to `VARIANTS` in `ocp/lab/webhook_lab.py` and a
label in `report.py`. `pytest tests/test_webhooks.py`: the kit still breaks nothing, the new variant breaks something.

## Run the held-out prospect (once)
Gates final and committed, then `python -m ocp.cli heldout`; commit `reports/heldout.lock` with the reports in one commit.

## Refresh the console screenshots
`cd web && npm run build`, serve `web/dist`, capture `docs/screenshots/console.png` (light, full page) and `console-dark.png`.
