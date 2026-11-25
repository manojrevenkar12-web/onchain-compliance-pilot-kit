"""Shapes shared by the kit, the simulation and the service. No behaviour, no truth."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

CATEGORIES = (
    "sanctions",
    "ransomware",
    "darknet_market",
    "mixer",
    "scam",
    "stolen_funds",
    "no_kyc_exchange",
    "gambling",
    "exchange",
    "defi",
    "bridge",
    "merchant",
)
CAT = {c: i for i, c in enumerate(CATEGORIES)}
SEGMENTS = ("retail", "hnw", "business")
NONE = -1


@dataclass
class Book:
    """The customer's own records: who their customers are and what moved. Visible to the kit."""

    hours: int
    calibration_hours: int
    segment: np.ndarray  # per customer, index into SEGMENTS
    kyc_risk: np.ndarray  # per customer: 0 low, 1 medium, 2 high (their own rating)
    account_age_days: np.ndarray
    cust: np.ndarray  # per transfer
    hour: np.ndarray
    withdrawal: np.ndarray  # bool
    amount: np.ndarray  # EUR
    unhosted: np.ndarray  # bool: counterparty is a self-hosted wallet
    address: np.ndarray  # counterparty address id
    known_cases: set[int] = field(default_factory=set)  # customers already reported in the shared history


@dataclass
class Screening:
    """What the blockchain intelligence says about each transfer's counterparty, as of a given hour."""

    direct_cat: np.ndarray  # category index or NONE
    indirect_cat: np.ndarray
    indirect_share: np.ndarray
    indirect_hops: np.ndarray
    direct_known_at: np.ndarray  # hour the direct attribution became known (inf: never)
    indirect_known_at: np.ndarray

    def at(self, hour: np.ndarray | float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Direct and indirect findings as screening at `hour` would return them."""
        d = np.where(self.direct_known_at <= hour, self.direct_cat, NONE)
        vis = self.indirect_known_at <= hour
        i = np.where(vis, self.indirect_cat, NONE)
        return d, i, np.where(vis, self.indirect_share, 0.0), np.where(vis, self.indirect_hops, 0)


@dataclass(frozen=True)
class Alert:
    key: str  # stable across designs: the same transfer and rule family gives the same key
    cust: int
    transfer: int  # the transfer that raised it (for behavioural rules, the last one)
    hour: int  # when the alert exists
    rule: str
    family: str  # direct | indirect | behavioral
    category: str  # what it is about
    severity: int  # 3 critical, 2 high, 1 medium
    share: float = 0.0
    hops: int = 0
    amount: float = 0.0
