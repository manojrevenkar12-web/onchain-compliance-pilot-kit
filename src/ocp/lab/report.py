"""Writes REPORT.md, the README results block, one pilot plan per prospect and the console data from
reports/*.json. Never edited by hand: CI regenerates them and fails on a diff."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .. import config

ROOT = config.ROOT
START, END = "<!-- results:start -->", "<!-- results:end -->"
SHORT = {
    "as_is": "As found",
    "kit": "Pilot kit",
    "untuned": "Not tuned",
    "no_behavioral": "No behavioural rules",
    "no_rescreen": "No re-screening",
    "no_triage": "Manual review",
    "ungoverned_triage": "Ungoverned AI",
    "fifo_queue": "First in, first out",
}
WEBHOOK_LABEL = {
    "kit": "Kit receiver: signature, dedupe by event id, versioning; sender retries",
    "no_signature": "Without the signature check",
    "no_dedupe": "Without dedupe by event id",
    "no_versioning": "Without versioning (last delivery wins)",
    "no_retries": "Sender without retries",
}
KIND = {
    "forged": "forged event opened a case",
    "duplicate_ticket": "two tickets for one alert",
    "no_ticket": "case with no ticket",
    "double_logged": "event logged twice",
    "stale": "case left at an older version",
    "lost": "alert never reached case management",
}
CRITERIA = {
    "reportable_customers_escalated": "Reportable customers escalated in time",
    "sanctions_customers_escalated": "Sanctions-exposed customers escalated in time",
    "p90_working_hours_to_decision": "Working hours to a decision, p90",
    "backlog_alerts_at_end": "Alerts waiting at the end of the pilot",
    "reportable_missed_after_machine_close": "Reportable customers lost after a machine-closed alert",
}


def _load(name: str) -> dict[str, Any] | None:
    p = config.REPORTS / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def pct(x: float | None, d: int = 1) -> str:
    return "–" if x is None else f"{100 * x:.{d}f}%"


def num(x: float | None, d: int = 0) -> str:
    return "–" if x is None else f"{x:,.{d}f}"


Fmt = Callable[[float], str]
ROWS: list[tuple[str, str, Fmt]] = [
    ("Alerts a day", "alerts_per_day", lambda x: num(x, 1)),
    ("Alerts on customers who were really reportable", "alert_precision", lambda x: pct(x, 0)),
    ("**Reportable customers escalated in time**", "reportable_escalated_share", lambda x: pct(x, 1)),
    ("Sanctions-exposed customers escalated in time", "sanctions_escalated_share", lambda x: pct(x, 0)),
    ("Reportable customers who raised no alert at all", "_unalerted", lambda x: num(x, 1)),
    ("Escalations of customers who were not reportable", "wrong_escalations", lambda x: num(x, 1)),
    ("Working hours to a decision, p90", "working_hours_to_decision_p90", lambda x: num(x, 1)),
    ("Alerts waiting at the end of the pilot", "backlog_at_end", lambda x: num(x, 1)),
    ("Analyst minutes a day spent on alerts", "analyst_minutes_per_day", num),
    ("Alerts closed in the fast lane (10% sampled)", "fast_lane", lambda x: num(x, 1)),
    ("Reportable alerts closed without a full review", "reportable_alerts_closed_without_review", lambda x: num(x, 1)),
    ("Reportable customers lost after a machine-closed alert", "reportable_missed_after_machine_close", lambda x: num(x, 1)),
    ("Travel-rule holds on self-hosted withdrawals", "travel_rule_holds", num),
    ("**Prospect success criteria met** (of 5)", "criteria_met", lambda x: num(x, 1)),
]


def _v(m: dict[str, Any], key: str) -> float:
    if key == "_unalerted":
        return float(m["reportable_customers"] - m["reportable_alerted"])
    return float(m[key])


def _table(p: dict[str, Any], names: list[str]) -> list[str]:
    d = p["designs"]
    out = ["| | " + " | ".join(SHORT.get(n, n) for n in names) + " |", "|---|" + "---:|" * len(names)]
    for label, key, fmt in ROWS:
        cells = [fmt(_v(d[n], key)) for n in names]
        if "kit" in names:
            i = names.index("kit")
            cells[i] = f"**{cells[i]}**"
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    return out


def _criteria(p: dict[str, Any]) -> list[str]:
    a, k = p["designs"]["as_is"]["criteria"], p["designs"]["kit"]["criteria"]
    out = ["| Success criterion (from discovery) | Target | As found | Pilot kit |", "|---|---:|---:|---:|"]
    for c, label in CRITERIA.items():
        lim = k[c]["limit"]
        fmt = (lambda x: pct(x, 0)) if "escalated" in c else (lambda x: num(x, 1))
        tgt = ("≥ " if k[c]["kind"] == "min" else "≤ ") + fmt(lim)
        out.append(f"| {label} | {tgt} | {fmt(a[c]['value'])} (met {a[c]['met']}/{a[c]['of']}) | **{fmt(k[c]['value'])}** (met {k[c]['met']}/{k[c]['of']}) |")
    return out


def _webhooks(r: dict[str, Any]) -> list[str]:
    w = r["webhooks"]
    out = [f"| Receiver ({w['scenarios']} scenarios each) | Scenarios with a broken invariant | What broke |", "|---|---:|---|"]
    for k, v in w["variants"].items():
        what = ", ".join(f"{KIND.get(x, x)} ({n})" for x, n in sorted(v["by_kind"].items(), key=lambda kv: -kv[1])) or "nothing"
        b = num(v["scenarios_broken"])
        out.append(f"| {WEBHOOK_LABEL[k]} | {'**' + b + '**' if k == 'kit' else b} | {what} |")
    return out


def _gates(r: dict[str, Any]) -> list[str]:
    out = ["| Gate | Value | Limit | |", "|---|---:|---:|---|"]
    for g in r["gates"]["kit"]:
        out.append(f"| {g['gate']} | {g['value']:.4g} | {'≥' if g['kind'] == 'min' else '≤'} {g['limit']:g} | {'pass' if g['pass'] else '**FAIL**'} |")
    return out


def _intro(r: dict[str, Any]) -> str:
    w = r["windows"]
    names = "; ".join(f"{p['discovery']['name']} in {p['discovery']['jurisdiction']}" for p in r["prospects"].values())
    return (
        f"{len(r['seeds'])} simulated runs per prospect: {names}. Each run has {w['calibration_days']} days of shared history "
        f"(for compiling and tuning) and a {w['pilot_days']}-day pilot; every number is from the pilot window, mean of the runs."
    )


def dashboard(dev: dict[str, Any], held: dict[str, Any] | None) -> list[str]:
    P = dev["prospects"]
    out = ["_Generated by `ocp report` from `reports/*.json`. Do not edit by hand._", "", _intro(dev), ""]
    out += [
        "| Prospect | Alerts a day (as found → kit) | Reportable customers escalated in time | Alerts waiting at the end | Analyst minutes a day | Success criteria met |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for p in P.values():
        a, k = p["designs"]["as_is"], p["designs"]["kit"]
        out.append(
            f"| {p['discovery']['name']} | {num(a['alerts_per_day'], 1)} → **{num(k['alerts_per_day'], 1)}** | {pct(a['reportable_escalated_share'])} → **{pct(k['reportable_escalated_share'])}** "
            f"| {num(a['backlog_at_end'])} → **{num(k['backlog_at_end'])}** | {num(a['analyst_minutes_per_day'])} → **{num(k['analyst_minutes_per_day'])}** | {num(a['criteria_met'], 1)} → **{num(k['criteria_met'], 1)}** of 5 |"
        )
    wk = dev["webhooks"]["variants"]["kit"]
    ok = sum(g["pass"] for g in dev["gates"]["kit"])
    out += [
        "",
        f"Webhook lab: **{wk['scenarios_broken']} of {dev['webhooks']['scenarios']}** scenarios broke an invariant with the kit's receiver. Gates on the development prospects: **{ok} of {len(dev['gates']['kit'])} pass**.",
        "",
    ]
    if held:
        for p in held["prospects"].values():
            a, k = p["designs"]["as_is"], p["designs"]["kit"]
            hok = sum(g["pass"] for g in held["gates"]["kit"])
            out += [
                f"**Held-out prospect, run once:** {p['discovery']['name']} in {p['discovery']['jurisdiction']}, more mules and scam victims. Reportable customers escalated "
                f"{pct(a['reportable_escalated_share'])} → **{pct(k['reportable_escalated_share'])}**, alerts waiting {num(a['backlog_at_end'])} → **{num(k['backlog_at_end'])}**, "
                f"success criteria {num(k['criteria_met'], 1)} of 5, webhook lab **{held['webhooks']['variants']['kit']['scenarios_broken']} of {held['webhooks']['scenarios']}** broken; **{hok} of {len(held['gates']['kit'])} gates pass**.",
                "",
            ]
    return out


def report_md(dev: dict[str, Any], held: dict[str, Any] | None) -> str:
    out = ["# Report", "", "_Generated by `ocp report`. Do not edit by hand._", "", _intro(dev), ""]
    for split, r in (("Development prospects", dev), ("Held-out prospect (run once)", held)):
        if not r:
            continue
        out += [f"## {split}", ""]
        for p in r["prospects"].values():
            out += [f"### {p['discovery']['name']}: {p['discovery']['kind']}, {p['discovery']['jurisdiction']}", ""]
            out += _criteria(p) + [""] + _table(p, r["main"] + r["ablations"]) + [""]
        out += ["### Webhook lab", ""] + _webhooks(r) + ["", "### Gates", ""] + _gates(r) + [""]
    out += ["## What each design is", ""] + [f"- **{SHORT.get(n, n)}**: {dev['labels'][n]}" for n in dev["main"] + dev["ablations"]] + [""]
    return "\n".join(out)


def pilot_plan(p: dict[str, Any]) -> str:
    d, pol, k = p["discovery"], p["policy"], p["designs"]["kit"]
    ra = d["risk_appetite"]
    rv = d["review"]
    out = [
        f"# Pilot plan: {d['name']}",
        "",
        "_Generated by `ocp report` from the discovery notes in `config/` and the simulated pilot. Do not edit by hand._",
        "",
        f"**Who:** {d['kind']}, {d['jurisdiction']}, about {d['customers']:,} customers. **Team:** {rv['analysts']} analysts, "
        f"{rv['minutes_per_day_each']} minutes a day each on alerts, office hours {rv['office_hours'][0]}:00 to {rv['office_hours'][1]}:00.",
        "",
        f"**Risk appetite:** prohibited {', '.join(ra['prohibited'])}; high risk {', '.join(ra['high_risk'])}; restricted {', '.join(ra.get('restricted') or ['none'])}; "
        f"indirect exposure up to {ra['max_indirect_hops']} hops.",
        "",
        "## Rules compiled from discovery (before tuning on the shared history)",
        "",
        "| Rule | Fires on | Threshold | Severity |",
        "|---|---|---|---|",
    ]
    out += [f"| {r['rule']} | {r['fires']} | {r['threshold']} | {r['severity']} |" for r in pol["rules"]]
    if pol["notes"]:
        out += ["", "Notes for the customer:", ""] + [f"- {n}" for n in pol["notes"]]
    out += [
        "",
        "## Integration",
        "",
        "Alerts arrive by signed webhook, are de-duplicated by event id and applied in version order, and open one ticket each in case management. "
        "Each alert gets an evidence pack and a drafted disposition that cites it; low-risk alerts outside the hard rules go to a fast lane with 10% sampled for full review; "
        "sanctions, ransomware and darknet exposure, behavioural alerts and amounts of EUR 10,000 or more always get a full human review.",
        "",
    ]
    out += ["## Success criteria, and what the simulated pilot measured", ""] + _criteria(p) + [""]
    out += [f"Alerts a day: {num(k['alerts_per_day'], 1)}. Analyst minutes a day: {num(k['analyst_minutes_per_day'])} of {num(k['analyst_capacity_per_day'])} available.", ""]
    return "\n".join(out)


def console_data(dev: dict[str, Any], held: dict[str, Any] | None) -> dict[str, Any]:
    keys = [k for _, k, _ in ROWS if not k.startswith("_")] + ["reportable_customers", "reportable_alerted", "analyst_capacity_per_day", "working_hours_to_decision_p50", "drafts_wrong", "alerts"]

    def pick(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "windows": r["windows"],
            "seeds": r["seeds"],
            "labels": {n: SHORT.get(n, n) for n in r["main"] + r["ablations"]},
            "descriptions": r["labels"],
            "prospects": {
                name: {
                    "discovery": p["discovery"],
                    "rules": p["policy"]["rules"],
                    "notes": p["policy"]["notes"],
                    "designs": {n: {**{k: p["designs"][n][k] for k in keys}, "criteria": p["designs"][n]["criteria"]} for n in r["main"] + r["ablations"]},
                }
                for name, p in r["prospects"].items()
            },
            "webhooks": r["webhooks"],
            "gates": r["gates"],
        }

    return {"dev": pick(dev), "heldout": pick(held) if held else None, "criteria_labels": CRITERIA, "webhook_labels": WEBHOOK_LABEL, "webhook_kinds": KIND}


def write_all() -> None:
    dev = _load("dev")
    if dev is None:
        raise SystemExit("reports/dev.json is missing: run `ocp dev` first")
    held = _load("heldout")
    (ROOT / "REPORT.md").write_text(report_md(dev, held), encoding="utf-8")
    plans = ROOT / "reports" / "pilots"
    plans.mkdir(parents=True, exist_ok=True)
    for r in (dev, held):
        for name, p in (r or {}).get("prospects", {}).items():
            (plans / f"{name}.md").write_text(pilot_plan(p), encoding="utf-8")
    readme = ROOT / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        if START in text and END in text:
            head, rest = text.split(START, 1)
            _, tail = rest.split(END, 1)
            readme.write_text(head + START + "\n" + "\n".join(dashboard(dev, held)) + "\n" + END + tail, encoding="utf-8")
    web = ROOT / "web" / "public" / "data"
    web.mkdir(parents=True, exist_ok=True)
    (web / "report.json").write_text(json.dumps(console_data(dev, held), indent=1) + "\n", encoding="utf-8")
