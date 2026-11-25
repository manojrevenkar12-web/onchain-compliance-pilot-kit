"""One design on one prospect: build the policy (vendor default, compiled, or compiled and tuned on the shared
history), raise the pilot window's alerts, route and draft them, and let the analysts work the queue hour by hour.
Every outcome is scored against the world's truth."""

from __future__ import annotations

from typing import Any

import numpy as np

from .. import config
from ..kit.engine import all_alerts
from ..kit.policy import compile_policy, vendor_default
from ..kit.queue import Queue, Team
from ..kit.triage import Context, Scorer, draft_checked, evidence, features, route
from ..kit.tune import tune
from ..world.world import Site, analyst_right


def build_policy(site: Site, sw: dict[str, Any], kit: dict[str, Any], team: Team) -> tuple[Any, dict[str, Any]]:
    disc = config.prospect(site.name)
    info: dict[str, Any] = {}
    if sw["policy"] == "vendor":
        pol = vendor_default(disc)
    else:
        pol = compile_policy(disc, kit)
        pol.behavioral = bool(sw.get("behavioral", True))
        pol.segments = bool(sw.get("segments", True))
        if not sw.get("rescreen", True):
            pol.rescreen_days = 0
        if sw["policy"] == "tuned":
            per = kit["review"]["minutes_assisted" if sw["triage"] != "off" else "minutes_manual"]
            res = tune(pol, site.book, site.screening, kit, float(per), team.minutes_per_calendar_day())
            pol = res.policy
            info = {"known_cases": res.known_cases, "known_reached": res.known_reached, "alerts_per_day_history": res.alerts_per_day, "grid": res.grid_size}
    return pol, info


def run_design(site: Site, sw: dict[str, Any], kit: dict[str, Any] | None = None) -> dict[str, Any]:
    kit = kit or config.kit()
    disc = config.prospect(site.name)
    b = site.book
    rv = disc["review"]
    team = Team(int(rv["analysts"]), float(rv["minutes_per_day_each"]), (int(rv["office_hours"][0]), int(rv["office_hours"][1])))
    pol, info = build_policy(site, sw, kit, team)
    cal, end = b.calibration_hours, b.hours
    ctx = Context(b)
    triage = str(sw["triage"])
    scorer = Scorer(site.seed)
    if triage != "off":
        hist = all_alerts(b, site.screening, pol, 0, cal)
        seen: dict[int, int] = {}
        X, y = [], []
        for a in hist:
            X.append(features(a, b, ctx, seen.get(a.cust, 0)))
            y.append(int(a.cust in b.known_cases))
            seen[a.cust] = seen.get(a.cust, 0) + 1
        scorer.fit(np.array(X), np.array(y))
    alerts = all_alerts(b, site.screening, pol, cal, end)
    truth = site.reportable_in(cal, end)
    sanctions = site.sanctions_in(cal, end)
    rcfg = kit["review"]
    delay = int(np.ceil(float(rcfg["polling_delay_hours"]))) if sw["delivery"] == "polling" else 0
    q = Queue(str(sw["queue"]))
    prior: dict[int, int] = {}
    meta: dict[str, dict[str, Any]] = {}
    threshold = float(kit["triage"]["draft_escalate_above"])
    by_hour: dict[int, list[Any]] = {}
    for a in alerts:
        by_hour.setdefault(a.hour + delay, []).append(a)
    m: dict[str, float] = dict.fromkeys(
        ("auto_closed", "auto_closed_reportable", "fast_lane", "fast_lane_reportable_closed", "sampled", "minutes_used", "wrong_escalations", "drafts_rejected", "drafts_wrong"), 0.0
    )
    decided: list[float] = []
    escalated_at: dict[int, float] = {}  # customer -> first escalation hour (within deadline)
    closed_by_machine: set[int] = set()  # customers with an alert closed without a full human review
    deadline = float(rv["escalation_deadline_working_hours"])
    for h in range(cal, end):
        for a in by_hour.get(h, []):
            n_prior = prior.get(a.cust, 0)
            prior[a.cust] = n_prior + 1
            rep = a.cust in truth
            if triage == "off":
                meta[a.key] = {"a": a, "lane": "manual", "draft": "none", "rep": rep}
                q.push(a.key, float(rcfg["minutes_manual"]), "normal", h, float(a.severity))
                continue
            p = float(scorer.score(np.array([features(a, b, ctx, n_prior)]))[0])
            ev = evidence(a, b, ctx, n_prior, p)
            d, problems = draft_checked(a, ev, p, threshold)
            m["drafts_rejected"] += bool(problems)
            right = (d.recommend == "escalate") == rep
            m["drafts_wrong"] += not right
            lane = route(a, p, kit, governed=(triage == "governed"))
            meta[a.key] = {"a": a, "lane": lane, "draft": "right" if right else "wrong", "rep": rep, "p": p}
            if lane == "auto_close":
                m["auto_closed"] += 1
                m["auto_closed_reportable"] += rep
                closed_by_machine.add(a.cust)
                decided.append(0.0)
                continue
            if lane == "fast":
                m["fast_lane"] += 1
                q.push(a.key, float(rcfg["minutes_fast_lane"]), "fast", h, p)
                continue
            q.push(a.key, float(rcfg["minutes_assisted"]), lane, h, p + a.severity)
        for it in q.work(team.minutes_in_hour(h)):
            mm = meta[it.key]
            a = mm["a"]
            m["minutes_used"] += it.minutes
            waited = team.working_hours(a.hour, h + 1)
            decided.append(waited)
            if mm["lane"] == "fast":
                if site.luck("sample", a.key) < float(rcfg["sample_fast_lane"]):
                    m["sampled"] += 1
                    m["minutes_used"] += float(rcfg["minutes_assisted"])
                    ok = analyst_right(site, a.key, "wrong" if mm["rep"] else "right")
                    escalate = mm["rep"] == ok
                else:
                    escalate = False
                    m["fast_lane_reportable_closed"] += mm["rep"]
                    closed_by_machine.add(a.cust)
            else:
                ok = analyst_right(site, a.key, mm["draft"])
                escalate = mm["rep"] == ok
            if escalate:
                if not mm["rep"]:
                    m["wrong_escalations"] += 1
                elif waited <= deadline and a.cust not in escalated_at:
                    escalated_at[a.cust] = h + 1
    days = (end - cal) / 24
    caught = set(escalated_at)
    alerted = {a.cust for a in alerts}
    tr = float(disc["travel_rule"]["unhosted_threshold_eur"])
    tr_mask = b.withdrawal & b.unhosted & (b.amount >= tr)
    pilot = (b.hour >= cal) & (b.hour < end)
    holds = int((tr_mask & pilot).sum())
    if sw["policy"] != "vendor":  # proven self-hosted wallets are remembered per customer
        pairs = set()
        first = np.zeros(len(b.cust), dtype=bool)
        for k in np.flatnonzero(tr_mask):
            pair = (int(b.cust[k]), int(b.address[k]))
            if pair not in pairs:
                pairs.add(pair)
                first[k] = True
        holds = int((first & pilot).sum())
    out: dict[str, Any] = {
        **m,
        **{f"tune_{k}": float(v) for k, v in info.items()},
        "alerts": float(len(alerts)),
        "alerts_per_day": len(alerts) / days,
        "alert_precision": sum(1 for a in alerts if a.cust in truth) / max(len(alerts), 1),
        "reportable_customers": float(len(truth)),
        "reportable_alerted": float(len(alerted & truth)),
        "reportable_escalated": float(len(caught & truth)),
        "reportable_escalated_share": len(caught & truth) / max(len(truth), 1),
        "sanctions_customers": float(len(sanctions)),
        "sanctions_escalated_share": len(caught & sanctions) / max(len(sanctions), 1) if sanctions else 1.0,
        "reportable_alerts_closed_without_review": m["auto_closed_reportable"] + m["fast_lane_reportable_closed"],
        "reportable_missed_after_machine_close": float(len((truth - caught) & closed_by_machine)),
        "backlog_at_end": float(len(q)),
        "working_hours_to_decision_p50": float(np.percentile(decided, 50)) if decided else 0.0,
        "working_hours_to_decision_p90": float(np.percentile(decided, 90)) if decided else 0.0,
        "analyst_minutes_per_day": m["minutes_used"] / days,
        "analyst_capacity_per_day": team.minutes_per_calendar_day(),
        "minutes_per_alert": m["minutes_used"] / max(len(alerts) - len(q) - m["auto_closed"], 1),
        "travel_rule_holds": float(holds),
        "rules": float(len(pol.rules())),
    }
    crit = disc["success_criteria"]
    checks = {
        "reportable_customers_escalated": (out["reportable_escalated_share"], float(crit["reportable_customers_escalated_min"]), "min"),
        "sanctions_customers_escalated": (out["sanctions_escalated_share"], float(crit["sanctions_customers_escalated_min"]), "min"),
        "p90_working_hours_to_decision": (out["working_hours_to_decision_p90"], float(crit["p90_working_hours_to_decision_max"]), "max"),
        "backlog_alerts_at_end": (out["backlog_at_end"], float(crit["backlog_alerts_at_end_max"]), "max"),
        "reportable_missed_after_machine_close": (out["reportable_missed_after_machine_close"], float(crit["reportable_missed_after_machine_close_max"]), "max"),
    }
    out["criteria"] = {k: {"value": v, "limit": lim, "kind": kind, "pass": bool(v >= lim if kind == "min" else v <= lim)} for k, (v, lim, kind) in checks.items()}
    out["criteria_met"] = float(sum(c["pass"] for c in out["criteria"].values()))
    out["criteria_total"] = float(len(checks))
    return out
