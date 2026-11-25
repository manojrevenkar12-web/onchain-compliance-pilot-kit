"""Tuning on the history the customer shares: pick thresholds that reach the most customers already on file as
reportable, while the expected review time fits the team. Rules are independent, so each threshold's alerts are
computed once and combinations are scored as unions."""

from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass
from typing import Any

from ..domain import SEGMENTS, Alert, Book, Screening
from .engine import behavioral_alerts, screen_alerts
from .policy import Policy

PARAMS = ("indirect_share_prohibited", "indirect_share_high_risk", "high_risk_direct_min_eur", "structuring_count_7d", "restricted_24h_sum_eur")
RULES = {
    "indirect_share_prohibited": ("indirect", 3),
    "indirect_share_high_risk": ("indirect", 2),
    "high_risk_direct_min_eur": ("direct", 2),
    "structuring_count_7d": ("structuring-7d", 0),
    "restricted_24h_sum_eur": ("restricted-24h", 0),
}


@dataclass
class TuneResult:
    policy: Policy
    known_cases: int
    known_reached: int
    alerts_per_day: float
    minutes_per_day: float
    budget_per_day: float
    grid_size: int


def _set(p: Policy, param: str, v: float) -> Policy:
    q = copy.deepcopy(p)
    if param == "high_risk_direct_min_eur":
        q.high_risk_direct_min_eur = dict.fromkeys(SEGMENTS, float(v))
    else:
        setattr(q, param, type(getattr(p, param))(v))
    return q


def _part(alerts: list[Alert], param: str) -> list[Alert]:
    rule, sev = RULES[param]
    if rule in ("direct", "indirect"):
        return [a for a in alerts if a.family == rule and a.severity == sev]
    return [a for a in alerts if a.rule == rule]


def tune(policy: Policy, book: Book, scr: Screening, kit: dict[str, Any], minutes_per_alert: float, analyst_minutes_per_day: float) -> TuneResult:
    lo, hi = 0, book.calibration_hours
    days = hi / 24
    grid = kit["tune"]
    base_scr = screen_alerts(book, scr, policy, lo, hi)
    base_beh = behavioral_alerts(book, scr, policy, lo, hi)
    tuned_keys = {(a.family, a.severity) for p in PARAMS[:3] for a in _part(base_scr, p)}
    fixed = [a for a in base_scr if (a.family, a.severity) not in tuned_keys] + [a for a in base_beh if a.rule not in ("structuring-7d", "restricted-24h")]
    parts: dict[str, dict[float, list[Alert]]] = {}
    for param in PARAMS:
        parts[param] = {}
        for v in grid[param]:
            q = _set(policy, param, v)
            src = screen_alerts(book, scr, q, lo, hi) if param in PARAMS[:3] else behavioral_alerts(book, scr, q, lo, hi, (RULES[param][0],))
            parts[param][float(v)] = _part(src, param)
    known = book.known_cases
    budget = analyst_minutes_per_day * float(grid["capacity_use"])
    best: tuple[tuple[float, float], dict[str, float], int, float] | None = None
    combos = list(itertools.product(*[sorted(parts[p]) for p in PARAMS]))
    for combo in combos:
        alerts = fixed + [a for p, v in zip(PARAMS, combo, strict=True) for a in parts[p][v]]
        keys = {a.key for a in alerts}
        reached = len({a.cust for a in alerts} & known)
        load = len(keys) / days * minutes_per_alert
        score = (reached if load <= budget else -load, -len(keys))
        if best is None or score > best[0]:
            best = (score, dict(zip(PARAMS, combo, strict=True)), reached, len(keys) / days)
    assert best is not None
    out = policy
    for p, v in best[1].items():
        out = _set(out, p, v)
    out.notes = [*policy.notes, f"tuned on {int(days)} days of shared history: {best[2]} of {len(known)} known cases reached, {best[3]:.1f} alerts a day"]
    return TuneResult(out, len(known), best[2], best[3], best[3] * minutes_per_alert, budget, len(combos))
