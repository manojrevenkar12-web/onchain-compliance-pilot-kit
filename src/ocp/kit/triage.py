"""AI-assisted alert triage. For each alert the kit gathers an evidence pack from the customer's book and the
screening result, a model scores how likely the customer is reportable, and a drafter writes a disposition that
cites the evidence. Code then decides the route: hard rules first, the score second. The analyst decides the case.

The drafter is a template by default. Any other drafter (for example an LLM) must pass the same check: every
sentence cites evidence that exists, and every number it quotes appears in that evidence. A draft that fails is
replaced by the template draft."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from ..domain import CAT, SEGMENTS, Alert, Book

FAMILY = {"direct": 0, "indirect": 1, "behavioral": 2}


@dataclass(frozen=True)
class Evidence:
    id: str
    label: str
    value: str


@dataclass(frozen=True)
class Draft:
    recommend: str  # escalate | close
    sentences: tuple[tuple[str, tuple[str, ...]], ...]  # text, cited evidence ids
    drafter: str

    def text(self) -> str:
        return " ".join(f"{s} [{', '.join(c)}]" for s, c in self.sentences)


class Context:
    """What the kit knows about each customer up to now: built from the book, never from the truth."""

    def __init__(self, book: Book) -> None:
        self.book = book
        order = np.argsort(book.cust, kind="stable")
        self.by_cust: dict[int, np.ndarray] = {}
        cs = book.cust[order]
        bounds = np.flatnonzero(np.diff(cs)) + 1
        for chunk in np.split(order, bounds):
            if len(chunk):
                self.by_cust[int(book.cust[chunk[0]])] = chunk

    def activity(self, cust: int, hour: int) -> dict[str, float]:
        b = self.book
        ks = self.by_cust.get(cust, np.array([], dtype=int))
        past = ks[(b.hour[ks] <= hour) & (b.hour[ks] > hour - 7 * 24)]
        wd = past[b.withdrawal[past]]
        dep = past[~b.withdrawal[past]]
        return {
            "transfers_7d": float(len(past)),
            "unhosted_withdrawals_7d": float(b.unhosted[wd].sum()),
            "withdrawn_eur_7d": float(b.amount[wd].sum()),
            "deposited_eur_7d": float(b.amount[dep].sum()),
        }


def features(a: Alert, book: Book, ctx: Context, prior_alerts: int) -> list[float]:
    act = ctx.activity(a.cust, a.hour)
    return [
        float(a.severity),
        float(FAMILY[a.family]),
        float(CAT.get(a.category, -1)),
        a.share,
        float(a.hops),
        float(np.log1p(a.amount)),
        float(book.segment[a.cust]),
        float(book.kyc_risk[a.cust]),
        float(np.log1p(book.account_age_days[a.cust])),
        float(prior_alerts),
        act["transfers_7d"],
        act["unhosted_withdrawals_7d"],
        float(np.log1p(act["withdrawn_eur_7d"])),
        float(np.log1p(act["deposited_eur_7d"])),
        float("rescreen" in a.rule),
    ]


class Scorer:
    """Gradient-boosted trees on alerts from the shared history, labelled by the customer's own case file."""

    def __init__(self, seed: int = 0) -> None:
        self.model = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08, max_leaf_nodes=15, l2_regularization=1.0, random_state=seed)
        self.fitted = False
        self.base_rate = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> Scorer:
        self.base_rate = float(y.mean()) if len(y) else 0.0
        if len(y) >= 30 and 0 < y.sum() < len(y):
            self.model.fit(X, y)
            self.fitted = True
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        if not len(X):
            return np.zeros(0)
        if not self.fitted:
            return np.full(len(X), max(self.base_rate, 0.5))  # no model: nothing goes to the fast lane
        return np.asarray(self.model.predict_proba(X)[:, 1])


def evidence(a: Alert, book: Book, ctx: Context, prior_alerts: int, p: float) -> list[Evidence]:
    act = ctx.activity(a.cust, a.hour)
    seg = SEGMENTS[int(book.segment[a.cust])]
    ev = [
        Evidence("E1", "alert", f"{a.rule} on {a.category}, severity {a.severity}, EUR {a.amount:,.0f}"),
        Evidence("E2", "exposure", f"{a.share:.0%} at {a.hops} hops" if a.family == "indirect" else ("direct counterparty" if a.family == "direct" else "pattern across transfers")),
        Evidence("E3", "customer", f"{seg}, KYC risk {['low', 'medium', 'high'][int(book.kyc_risk[a.cust])]}, account age {int(book.account_age_days[a.cust])} days"),
        Evidence(
            "E4",
            "last 7 days",
            f"{int(act['transfers_7d'])} transfers, {int(act['unhosted_withdrawals_7d'])} to self-hosted wallets, EUR {act['withdrawn_eur_7d']:,.0f} out, EUR {act['deposited_eur_7d']:,.0f} in",
        ),
        Evidence("E5", "earlier alerts", f"{prior_alerts} on this customer in the pilot"),
        Evidence("E6", "model score", f"{p:.2f} chance the customer is reportable"),
    ]
    if "rescreen" in a.rule:
        ev.append(Evidence("E7", "timing", "counterparty attributed after the transfer; raised by re-screening"))
    return ev


def template_draft(a: Alert, ev: list[Evidence], p: float, threshold: float) -> Draft:
    ids = {e.id: e for e in ev}
    s: list[tuple[str, tuple[str, ...]]] = [(f"Alert {a.rule} on {a.category}.", ("E1",))]
    if a.family == "indirect":
        s.append((f"Exposure is {ids['E2'].value}.", ("E2",)))
    if "E3" in ids:
        s.append((f"Customer profile: {ids['E3'].value}.", ("E3",)))
    if "E4" in ids:
        s.append((f"Recent activity: {ids['E4'].value}.", ("E4",)))
    if "E7" in ids:
        s.append(("The counterparty was attributed after the transfer.", ("E7",)))
    rec = "escalate" if p >= threshold else "close"
    s.append((f"Recommend {rec}: score {p:.2f}.", ("E6",)))
    return Draft(rec, tuple(s), "template")


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def check_draft(d: Draft, ev: list[Evidence]) -> list[str]:
    """Problems with a draft: uncited sentences, citations to evidence that does not exist, numbers not in the
    cited evidence, or a recommendation outside the allowed set."""
    ids = {e.id: e for e in ev}
    bad = []
    if d.recommend not in ("escalate", "close"):
        bad.append(f"recommendation {d.recommend!r} is not escalate or close")
    for text, cites in d.sentences:
        if not cites:
            bad.append(f"uncited: {text}")
            continue
        missing = [c for c in cites if c not in ids]
        if missing:
            bad.append(f"cites missing evidence {missing}: {text}")
            continue
        pool = " ".join(ids[c].value + " " + ids[c].label for c in cites)
        allowed = set(_NUM.findall(pool))
        for n in _NUM.findall(text):
            if n not in allowed and n.replace(",", "") not in {x.replace(",", "") for x in allowed}:
                bad.append(f"number {n} is not in {cites}: {text}")
    return bad


Drafter = Callable[[Alert, list[Evidence], float, float], Draft]


def draft_checked(a: Alert, ev: list[Evidence], p: float, threshold: float, drafter: Drafter | None = None) -> tuple[Draft, list[str]]:
    if drafter is None:
        return template_draft(a, ev, p, threshold), []
    d = drafter(a, ev, p, threshold)
    problems = check_draft(d, ev)
    return (template_draft(a, ev, p, threshold), problems) if problems else (d, [])


def route(a: Alert, p: float, cfg: dict[str, Any], governed: bool = True) -> str:
    """fast | normal | priority | auto_close. Hard rules come before the score."""
    t = cfg["triage"]
    if not governed:
        return "auto_close" if p < float(t["ungoverned_auto_close_below"]) else ("priority" if p >= float(t["priority_above"]) else "normal")
    hard = t["never_fast_lane"]
    blocked = a.category in hard["categories"] or a.family in hard["families"] or a.amount >= float(hard["min_amount_eur"])
    if a.severity >= 3 or p >= float(t["priority_above"]):
        return "priority"
    if p < float(t["fast_lane_below"]) and not blocked:
        return "fast"
    return "normal"
