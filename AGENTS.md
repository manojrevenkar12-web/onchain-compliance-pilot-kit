# AGENTS.md

How to work in this repository, for people and coding agents alike.

## Fast feedback

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy src tests && pytest -q    # about 10 seconds
python -m ocp.cli dev && python -m ocp.cli gate dev                     # every design on every development prospect, about a minute
cd web && npm ci && npm run typecheck && npm run lint && npm test        # the console
```

## Layout

| Package | Owns | May import |
|---|---|---|
| `ocp.world` | the simulated onchain world and each prospect's customers, with the truth (`config/world.yml`) | `ocp.config`, `ocp.domain`, `ocp.rng` |
| `ocp.kit` | the pilot kit: policy compiler, rules engine, tuner, triage, queue, webhook receiver | `ocp.config`, `ocp.domain` |
| `ocp.service` | the HTTP API: webhooks into cases, decisions, policy compile, draft check | `ocp.kit` |
| `ocp.sim` | runs a design on a prospect and scores it against the truth | everything above |
| `ocp.lab` | the study, the webhook lab, the gates, the reports and pilot plans | everything above |
| `config/prospects/` | discovery notes per prospect, as the customer would give them | read by the kit and the world |
| `web/` | the console; reads only `web/public/data/report.json` | – |

## Invariants

1. **The truth stays in the world.** Which customer is a mule, which transfer is part of a scheme, which counterparty
   the intelligence will attribute and when: only `ocp.world` knows. The kit sees the customer's book, screening
   results as of a given hour, and the cases the customer already had on file. `tests/test_boundaries.py` fails if the
   kit or the service imports the world, the simulation or the lab.
2. **The world does not read the kit's settings.** It reads `world.yml` and the prospect's size and segments, never
   `kit.yml` or `designs.yml`.
3. **Same luck for every design.** All randomness is keyed (`ocp.rng.keyed`) by seed, prospect and subject: every
   design sees the same customers, the same attributions and the same analyst mistakes on the same alert.
4. **The model scores and code decides.** The triage model only scores; the route comes from hard rules first
   (prohibited categories, behavioural alerts and large amounts are never fast-laned) and the score second. A person
   decides every case that is not in the sampled fast lane. Every draft must cite evidence that exists and quote
   only numbers from it, or it is replaced by the template draft.
5. **Tune only on what the customer shared.** Thresholds and the triage model learn from the history window and the
   customer's existing case file, never from the pilot window or the truth.
6. **An event is applied once and in order.** The receiver checks the signature and time window, records the event
   id in the same transaction as its effect, and never lets an older version overwrite a newer one.
7. **Settings in config.** Thresholds, grids, routes, minutes and gates live in `config/*.yml`.
8. **Generated reports.** `REPORT.md`, `reports/pilots/*.md`, the README results block and
   `web/public/data/report.json` are written by `python -m ocp.cli report`. CI regenerates them and fails on a diff.

## The held-out rule

`python -m ocp.cli heldout` runs the held-out prospect (`config/heldout/`, never used while building) and the
held-out webhook scenarios **once**. It writes `reports/heldout.lock` first, with the config hash; a second run exits
with code 3, and CI checks the lock was committed exactly once. Gates are set on the development prospects and are not
loosened afterwards.
