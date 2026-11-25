"""Runs a policy over the customer's transfers and the screening results, the way transaction monitoring would:
each transfer is screened when it happens, and again if a counterparty is attributed later (re-screening)."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from ..domain import CAT, CATEGORIES, NONE, SEGMENTS, Alert, Book, Screening
from .policy import Policy

FAMILIES = ("direct", "indirect", "behavioral")


def _groups(policy: Policy) -> np.ndarray:
    g = np.zeros(len(CAT) + 1, dtype=int)  # last slot: NONE
    for c in policy.prohibited:
        g[CAT[c]] = 3
    for c in policy.high_risk:
        g[CAT[c]] = 2
    for c in policy.restricted:
        g[CAT[c]] = 1
    return g


def _screen(book: Book, policy: Policy, g: np.ndarray, d: np.ndarray, i: np.ndarray, sh: np.ndarray, ho: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    seg = book.segment[book.cust] if policy.segments else np.zeros(len(book.cust), dtype=int)
    floor = np.array([policy.high_risk_direct_min_eur[s] for s in SEGMENTS])[seg]
    gd, gi = g[d], g[i]
    direct = (gd == 3) | ((gd == 2) & (book.amount >= floor)) | ((gd == 1) & (not policy.behavioral))
    indirect = ((gi == 3) & (ho <= policy.max_hops) & (sh >= policy.indirect_share_prohibited)) | (
        (gi == 2) & (ho <= min(policy.high_risk_hops, policy.max_hops)) & (sh >= policy.indirect_share_high_risk)
    )
    return direct, indirect


def _alert(book: Book, k: int, hour: int, rule: str, family: str, cat: int, sev: int, share: float = 0.0, hops: int = 0) -> Alert:
    return Alert(f"{k}:{family}", int(book.cust[k]), int(k), int(hour), rule, family, CATEGORIES[cat] if cat >= 0 else "none", sev, float(share), int(hops), float(book.amount[k]))


def screen_alerts(book: Book, scr: Screening, policy: Policy, lo: int, hi: int) -> list[Alert]:
    """Direct and indirect exposure alerts for transfers in [lo, hi), including re-screening hits."""
    g = _groups(policy)
    out: list[Alert] = []
    win = (book.hour >= lo) & (book.hour < hi)
    d, i, sh, ho = scr.at(book.hour)
    direct, indirect = _screen(book, policy, g, d, i, sh, ho)
    for k in np.flatnonzero(win & direct):
        out.append(_alert(book, k, book.hour[k], "direct", "direct", d[k], int(g[d[k]])))
    for k in np.flatnonzero(win & indirect):
        out.append(_alert(book, k, book.hour[k], "indirect", "indirect", i[k], int(g[i[k]]), sh[k], ho[k]))
    if policy.rescreen_days:
        # the counterparty was attributed after the transfer: screen again when that happens
        late_d = np.isfinite(scr.direct_known_at) & (scr.direct_known_at > book.hour) & (scr.direct_known_at <= book.hour + 24 * policy.rescreen_days)
        late_i = np.isfinite(scr.indirect_known_at) & (scr.indirect_known_at > book.hour) & (scr.indirect_known_at <= book.hour + 24 * policy.rescreen_days)
        d2, i2, sh2, ho2 = scr.at(book.hour + 24 * policy.rescreen_days)  # what is known by the end of the re-screening window
        direct2, indirect2 = _screen(book, policy, g, d2, i2, sh2, ho2)
        when_d = np.ceil(np.where(late_d, scr.direct_known_at, np.inf))
        when_i = np.ceil(np.where(late_i, scr.indirect_known_at, np.inf))
        for k in np.flatnonzero(late_d & direct2 & ~direct & (book.hour >= lo - 24 * policy.rescreen_days) & (when_d >= lo) & (when_d < hi)):
            out.append(_alert(book, k, int(when_d[k]), "direct-rescreen", "direct", d2[k], int(g[d2[k]])))
        for k in np.flatnonzero(late_i & indirect2 & ~indirect & (book.hour >= lo - 24 * policy.rescreen_days) & (when_i >= lo) & (when_i < hi)):
            out.append(_alert(book, k, int(when_i[k]), "indirect-rescreen", "indirect", i2[k], int(g[i2[k]]), sh2[k], ho2[k]))
    return out


def behavioral_alerts(
    book: Book, scr: Screening, policy: Policy, lo: int, hi: int, rules: tuple[str, ...] = ("restricted-24h", "structuring-7d", "pass-through", "escalating-payments")
) -> list[Alert]:
    """Patterns across a customer's transfers. Each rule alerts once per customer per window it fires in."""
    if not policy.behavioral:
        return []
    g = _groups(policy)
    d, i, sh, _ = scr.at(book.hour)
    by_cust: dict[int, list[int]] = defaultdict(list)
    span = 44 * 24  # the longest look-back: 14 days of payments after 30 days of history
    for k in np.flatnonzero((book.hour >= lo - span) & (book.hour < hi)):
        by_cust[int(book.cust[k])].append(int(k))
    out: list[Alert] = []
    thr = policy.travel_rule_eur
    for c, ks in by_cust.items():
        if "restricted-24h" in rules:
            m = [k for k in ks if book.withdrawal[k] and d[k] != NONE and g[d[k]] == 1]
            last = -(10**9)
            for j, k in enumerate(m):
                total = sum(book.amount[x] for x in m[: j + 1] if book.hour[x] > book.hour[k] - 24)
                if total >= policy.restricted_24h_sum_eur and book.hour[k] >= lo and book.hour[k] - last >= 24:
                    out.append(Alert(f"{k}:restricted-24h", c, k, int(book.hour[k]), "restricted-24h", "behavioral", "restricted", 1, 0.0, 0, float(total)))
                    last = int(book.hour[k])
        if "structuring-7d" in rules:
            m = [k for k in ks if book.withdrawal[k] and book.unhosted[k] and 0.6 * thr <= book.amount[k] < thr]
            last = -(10**9)
            for j, k in enumerate(m):
                n = sum(1 for x in m[: j + 1] if book.hour[x] > book.hour[k] - 7 * 24)
                if n >= policy.structuring_count_7d and book.hour[k] >= lo and book.hour[k] - last >= 7 * 24:
                    out.append(
                        Alert(
                            f"{k}:structuring-7d",
                            c,
                            k,
                            int(book.hour[k]),
                            "structuring-7d",
                            "behavioral",
                            "structuring",
                            2,
                            0.0,
                            0,
                            float(sum(book.amount[x] for x in m[: j + 1] if book.hour[x] > book.hour[k] - 7 * 24)),
                        )
                    )
                    last = int(book.hour[k])
        if "escalating-payments" in rules:  # the shape of a victim paying a scam: new payee, rising amounts
            wds = [k for k in ks if book.withdrawal[k]]
            by_payee: dict[int, list[int]] = defaultdict(list)
            for k in wds:
                by_payee[int(book.address[k])].append(k)
            for payee, pk in by_payee.items():
                first = pk[0]
                earlier = [x for x in ks if book.address[x] == payee and book.hour[x] < book.hour[first]]
                if earlier or any(book.hour[x] < book.hour[first] - 30 * 24 for x in pk):
                    continue
                run = [pk[0]]
                for k in pk[1:]:
                    if book.amount[k] > book.amount[run[-1]] and book.hour[k] - book.hour[run[0]] <= 14 * 24:
                        run.append(k)
                    else:
                        run = [k]
                    total = float(book.amount[run].sum())
                    if len(run) >= policy.escalating_count_14d and total >= policy.escalating_min_total_eur and lo <= book.hour[k] < hi:
                        out.append(Alert(f"{k}:escalating-payments", c, k, int(book.hour[k]), "escalating-payments", "behavioral", "payee pattern", 2, 0.0, 0, total))
                        break
        if "pass-through" in rules:
            risky_in = [k for k in ks if not book.withdrawal[k] and (max(g[d[k]], g[i[k]] if sh[k] >= 0.05 else 0) >= 2)]
            for k in risky_in:
                outs = [x for x in ks if book.withdrawal[x] and 0 <= book.hour[x] - book.hour[k] <= policy.pass_through_hours]
                sent = sum(book.amount[x] for x in outs)
                if outs and sent >= policy.pass_through_share * book.amount[k]:
                    w = outs[-1]
                    if lo <= book.hour[w] < hi:
                        out.append(Alert(f"{w}:pass-through", c, w, int(book.hour[w]), "pass-through", "behavioral", "pass-through", 2, 0.0, 0, float(sent)))
    return out


def all_alerts(book: Book, scr: Screening, policy: Policy, lo: int, hi: int) -> list[Alert]:
    seen: set[str] = set()
    out = []
    for a in sorted(screen_alerts(book, scr, policy, lo, hi) + behavioral_alerts(book, scr, policy, lo, hi), key=lambda a: (a.hour, a.key)):
        if a.key not in seen:
            seen.add(a.key)
            out.append(a)
    return out
