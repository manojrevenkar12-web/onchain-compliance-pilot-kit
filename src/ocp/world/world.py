"""A prospect's customers and their transfers, and what every counterparty really is. Keyed randomness: every
design sees the same customers, transfers, attributions and analyst luck.

The kit gets two things from here, through ocp.sim: the customer's own book (ocp.domain.Book) and the screening
results an intelligence API would return as of a given hour (ocp.domain.Screening). The truth (who is a mule,
which transfer is part of a scheme) stays here."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from typing import Any

import numpy as np
import yaml

from ..config import CONFIG, prospect
from ..domain import CAT, CATEGORIES, NONE, SEGMENTS, Book, Screening
from ..rng import keyed

INF = float("inf")


@cache
def _world() -> dict[str, Any]:
    data = yaml.safe_load((CONFIG / "world.yml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def world_cfg(variant: str) -> dict[str, Any]:
    return dict(_world()[variant])


@dataclass
class Site:
    seed: int
    variant: str
    name: str
    cfg: dict[str, Any]
    book: Book
    screening: Screening
    ctype: np.ndarray  # per customer: index into TYPES
    bad: np.ndarray  # per transfer: part of a reportable scheme
    typology: np.ndarray  # per transfer: index into TYPES (the scheme it belongs to), NONE otherwise
    types: tuple[str, ...]
    reportable_types: frozenset[int]
    _luck: dict[tuple[object, ...], float] = field(default_factory=dict)

    def luck(self, *key: object) -> float:
        if key not in self._luck:
            self._luck[key] = float(keyed(self.seed, self.name, "luck", *key).random())
        return self._luck[key]

    def reportable_in(self, lo: int, hi: int) -> set[int]:
        """Customers with a reportable transfer in [lo, hi) hours."""
        m = self.bad & (self.book.hour >= lo) & (self.book.hour < hi)
        return set(int(c) for c in np.unique(self.book.cust[m]))

    def sanctions_in(self, lo: int, hi: int) -> set[int]:
        si = self.types.index("sanctions_evader")
        m = self.bad & (self.typology == si) & (self.book.hour >= lo) & (self.book.hour < hi)
        return set(int(c) for c in np.unique(self.book.cust[m]))


class _Entities:
    """Counterparty entities per category, each attributed (or not) from some hour on."""

    def __init__(self, seed: int, name: str, cfg: dict[str, Any], hours: int) -> None:
        self.cfg = cfg["categories"]
        self.seed, self.name, self.hours = seed, name, hours
        self.pool: dict[int, list[tuple[float, float]]] = {}

    def known_at(self, cat: int, k: int, born: float | None = None) -> float:
        """When the intelligence attributes entity k of this category: its birth plus the category's lag. A scheme
        passes `born` (the scheme starts with a fresh entity); background entities have their own birth."""
        pool = self.pool.setdefault(cat, [])
        while len(pool) <= k:
            r = keyed(self.seed, self.name, "entity", cat, len(pool))
            c = self.cfg[CATEGORIES[cat]]
            lo, hi = c["lag_days"]
            lag = float(r.uniform(lo, hi + 1e-9)) * 24 if r.random() < float(c["coverage"]) else INF
            birth = float(r.uniform(-90 * 24, self.hours))
            pool.append((lag, birth))
        lag, birth = pool[k]
        return (birth if born is None else born) + lag


def build_site(seed: int, name: str, variant: str = "dev") -> Site:
    cfg = world_cfg(variant)
    disc = prospect(name)
    cal_h = int(cfg["calibration_days"]) * 24
    hours = cal_h + int(cfg["pilot_days"]) * 24
    types = tuple(cfg["customer_types"])
    tshare = np.array([cfg["customer_types"][t]["share"] for t in types], dtype=float)
    reportable = frozenset(i for i, t in enumerate(types) if cfg["customer_types"][t]["reportable"])
    n = int(disc["customers"])
    r = keyed(seed, name, "customers")
    ctype = r.choice(len(types), size=n, p=tshare / tshare.sum())
    sp = np.array([disc["segments"][s] for s in SEGMENTS], dtype=float)
    segment = r.choice(len(SEGMENTS), size=n, p=sp / sp.sum())
    risky = np.isin(ctype, list(reportable))
    kyc = np.where(r.random(n) < np.where(risky, 0.35, 0.08), 2, np.where(r.random(n) < 0.25, 1, 0))
    age = np.where(risky & (r.random(n) < 0.6), r.integers(1, 60, n), r.integers(10, 2500, n))

    ents = _Entities(seed, name, cfg, hours)
    inc = cfg["incidental_exposure"]
    inc_cats = [CAT[c] for c in inc["categories"]]
    inc_p = np.array(list(inc["categories"].values()), dtype=float)
    thr = float(disc["travel_rule"]["unhosted_threshold_eur"])
    lam = float(cfg["transfers_per_customer_per_window"]) * hours / (cal_h)  # over both windows
    mu = cfg["amount_eur_lognormal"]
    rows: list[tuple[Any, ...]] = []  # cust, hour, wd, amount, unhosted, address, dcat, dknown, icat, ishare, ihops, iknown, bad, typology
    next_addr = [0]

    def addr() -> int:
        next_addr[0] += 1
        return next_addr[0]

    def entity(rc: np.random.Generator, cat: int, k: int | None = None, born: float | None = None) -> tuple[int, float, int]:
        k = int(rc.integers(0, 40)) if k is None else k
        return cat, ents.known_at(cat, k, born), 1_000_000 + cat * 1000 + k

    for c in range(n):
        rc = keyed(seed, name, "cust", c)
        seg = SEGMENTS[segment[c]]
        m, s = mu["normal" if seg == "retail" else seg]
        own = [addr() for _ in range(int(rc.integers(1, 4)))]
        t = types[ctype[c]]
        k_bg = int(rc.poisson(lam * (0.5 if t in ("mule", "structurer") else 1.0)))
        for _ in range(k_bg):  # ordinary activity
            h = int(rc.integers(0, hours))
            wd = bool(rc.random() < 0.5)
            amt = float(rc.lognormal(m, s))
            u = rc.random()
            if t == "gambler" and rc.random() < 0.45:
                cat, kn, a = entity(rc, CAT["gambling"], int(rc.integers(0, 6)))
                rows.append((c, h, wd, amt * 0.3, False, a, cat, kn, NONE, 0.0, 0, INF, False, NONE))
                continue
            if u < 0.45:
                cat, kn, a = entity(rc, CAT["exchange"])
            elif u < 0.57:
                cat, kn, a = entity(rc, CAT["defi"])
            elif u < 0.62:
                cat, kn, a = entity(rc, CAT["merchant"])
            elif u < 0.65:
                cat, kn, a = entity(rc, CAT["bridge"])
            elif u < 0.67:
                cat, kn, a = entity(rc, CAT["gambling"])
            elif u < 0.70:
                cat, kn, a = entity(rc, CAT["no_kyc_exchange"])
            else:
                a = own[int(rc.integers(0, len(own)))] if rc.random() < 0.7 else addr()
                ic, ish, ih, ik = NONE, 0.0, 0, INF
                if rc.random() < float(inc["share_of_unhosted"]):
                    ic = inc_cats[int(rc.choice(len(inc_cats), p=inc_p / inc_p.sum()))]
                    ish = float(rc.uniform(*inc["share"]))
                    ih = int(rc.integers(inc["hops"][0], inc["hops"][1] + 1))
                    ik = ents.known_at(ic, int(rc.integers(0, 40)))
                rows.append((c, h, wd, amt, True, a, NONE, INF, ic, ish, ih, ik, False, NONE))
                continue
            rows.append((c, h, wd, amt, False, a, cat, kn, NONE, 0.0, 0, INF, False, NONE))

        ti = ctype[c]
        start = int(rc.integers(0, hours - 24 * 10))
        if t == "scam_victim":
            k = int(rc.integers(40, 400))  # a scam site of its own, born when the scheme starts
            via_wallet = rc.random() < 0.35
            amt = float(rc.lognormal(m, 0.5)) * 0.6
            wallet = addr()  # the "platform" deposit address the victim is told to pay
            h = start
            for _ in range(int(rc.integers(3, 7))):
                amt *= float(rc.uniform(1.1, 1.8))
                if via_wallet:
                    kn = ents.known_at(CAT["scam"], k, start)
                    rows.append((c, h, True, amt, True, wallet, NONE, INF, CAT["scam"], float(rc.uniform(0.6, 0.95)), 1, kn, True, ti))
                else:
                    cat, kn, a = entity(rc, CAT["scam"], k, start)
                    rows.append((c, h, True, amt, False, a, cat, kn, NONE, 0.0, 0, INF, True, ti))
                h += int(rc.integers(12, 72))
        elif t == "mule":
            h = start
            for _ in range(int(rc.integers(6, 16))):
                src = CAT["scam"] if rc.random() < 0.7 else CAT["stolen_funds"]
                kn = ents.known_at(src, int(rc.integers(40, 400)), h - float(rc.uniform(0, 72)))
                amt = float(rc.lognormal(7.0, 0.8))
                rows.append((c, h, False, amt, True, addr(), NONE, INF, src, float(rc.uniform(0.3, 0.9)), int(rc.integers(1, 3)), kn, True, ti))
                h2 = h + int(rc.integers(1, 12))
                dest = CAT["mixer"] if rc.random() < 0.3 else CAT["no_kyc_exchange"]
                if rc.random() < 0.25:
                    rows.append((c, h2, True, amt * 0.95, True, addr(), NONE, INF, NONE, 0.0, 0, INF, True, ti))
                else:
                    cat, kn2, a = entity(rc, dest)
                    rows.append((c, h2, True, amt * 0.95, False, a, cat, kn2, NONE, 0.0, 0, INF, True, ti))
                h += int(rc.integers(4, 48))
        elif t == "darknet_buyer":
            h = start
            for _ in range(int(rc.integers(2, 7))):
                amt = float(rc.lognormal(5.0, 0.6))
                if rc.random() < 0.7:
                    cat, kn, a = entity(rc, CAT["darknet_market"], int(rc.integers(0, 8)))
                    rows.append((c, h, True, amt, False, a, cat, kn, NONE, 0.0, 0, INF, True, ti))
                else:
                    kn = ents.known_at(CAT["darknet_market"], int(rc.integers(0, 8)))
                    rows.append((c, h, True, amt, True, addr(), NONE, INF, CAT["darknet_market"], float(rc.uniform(0.6, 0.95)), 1, kn, True, ti))
                h += int(rc.integers(24, 200))
        elif t == "structurer":
            h = start
            for _ in range(int(rc.integers(8, 21))):
                rows.append((c, h, True, thr * float(rc.uniform(0.7, 0.99)), True, addr(), NONE, INF, NONE, 0.0, 0, INF, True, ti))
                h += int(rc.integers(2, 20))
        elif t == "sanctions_evader":
            h = start
            for _ in range(int(rc.integers(2, 6))):
                amt = float(rc.lognormal(m + 1, 0.8))
                wd = bool(rc.random() < 0.6)
                if rc.random() < 0.3:
                    cat, kn, a = entity(rc, CAT["sanctions"], int(rc.integers(0, 5)))
                    rows.append((c, h, wd, amt, False, a, cat, kn, NONE, 0.0, 0, INF, True, ti))
                else:
                    kn = ents.known_at(CAT["sanctions"], int(rc.integers(0, 5)))
                    rows.append((c, h, wd, amt, True, addr(), NONE, INF, CAT["sanctions"], float(rc.uniform(0.15, 0.8)), int(rc.integers(1, 3)), kn, True, ti))
                h += int(rc.integers(24, 150))

    rows = [x for x in rows if 0 <= x[1] < hours]
    rows.sort(key=lambda x: (x[1], x[0]))
    col: list[tuple[Any, ...]] = list(zip(*rows, strict=True))
    book = Book(
        hours=hours,
        calibration_hours=cal_h,
        segment=segment,
        kyc_risk=kyc,
        account_age_days=age,
        cust=np.array(col[0], dtype=int),
        hour=np.array(col[1], dtype=int),
        withdrawal=np.array(col[2], dtype=bool),
        amount=np.array(col[3], dtype=float),
        unhosted=np.array(col[4], dtype=bool),
        address=np.array(col[5], dtype=int),
    )
    scr = Screening(
        direct_cat=np.array(col[6], dtype=int),
        direct_known_at=np.array(col[7], dtype=float),
        indirect_cat=np.array(col[8], dtype=int),
        indirect_share=np.array(col[9], dtype=float),
        indirect_hops=np.array(col[10], dtype=int),
        indirect_known_at=np.array(col[11], dtype=float),
    )
    site = Site(seed, variant, name, cfg, book, scr, ctype, np.array(col[12], dtype=bool), np.array(col[13], dtype=int), types, reportable)
    known = keyed(seed, name, "known-cases")
    share = float(cfg["analysts"]["known_case_share"])
    book.known_cases = {c for c in sorted(site.reportable_in(0, cal_h)) if known.random() < share}
    return site


def analyst_right(site: Site, alert_key: str, draft: str) -> bool:
    """Whether the analyst decides this alert correctly. draft: none | right | wrong (what the agent proposed)."""
    a = site.cfg["analysts"]
    p = {"none": a["accuracy_manual"], "right": a["accuracy_with_right_draft"], "wrong": a["accuracy_with_wrong_draft"]}[draft]
    return site.luck("analyst", alert_key) < float(p)
