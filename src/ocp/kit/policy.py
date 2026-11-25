"""From discovery notes to a monitoring policy. The customer's risk appetite decides which categories are
prohibited, high risk or restricted; the kit turns that into rules with thresholds a person can read and change."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..domain import CATEGORIES, SEGMENTS

SEVERE = ("sanctions", "ransomware", "darknet_market")


@dataclass
class Policy:
    name: str
    prohibited: list[str]
    high_risk: list[str]
    restricted: list[str]
    max_hops: int
    indirect_share_prohibited: float
    indirect_share_high_risk: float
    high_risk_direct_min_eur: dict[str, float]
    restricted_24h_sum_eur: float
    structuring_count_7d: int
    travel_rule_eur: float
    pass_through_hours: int
    pass_through_share: float
    rescreen_days: int
    high_risk_hops: int = 2
    escalating_count_14d: int = 3
    escalating_min_total_eur: float = 1000.0
    behavioral: bool = True
    segments: bool = True
    notes: list[str] = field(default_factory=list)

    def rules(self) -> list[dict[str, Any]]:
        """The policy as a reviewable list of rules: what fires, on what, at which threshold."""
        out: list[dict[str, Any]] = [
            {"rule": "prohibited-direct", "fires": f"any transfer with {', '.join(self.prohibited)}", "threshold": "any amount", "severity": "critical"},
            {
                "rule": "prohibited-indirect",
                "fires": f"funds from {', '.join(self.prohibited)} within {self.max_hops} hops",
                "threshold": f"share >= {self.indirect_share_prohibited:.1%}",
                "severity": "critical",
            },
            {
                "rule": "high-risk-direct",
                "fires": f"any transfer with {', '.join(self.high_risk)}",
                "threshold": ", ".join(f"{s} >= EUR {v:,.0f}" for s, v in self.high_risk_direct_min_eur.items()),
                "severity": "high",
            },
            {
                "rule": "high-risk-indirect",
                "fires": f"funds from {', '.join(self.high_risk)} within {min(self.high_risk_hops, self.max_hops)} hops",
                "threshold": f"share >= {self.indirect_share_high_risk:.0%}",
                "severity": "high",
            },
        ]
        if not self.behavioral:
            out.append({"rule": "restricted-direct", "fires": f"any transfer with {', '.join(self.restricted)}", "threshold": "any amount", "severity": "medium"})
        if self.rescreen_days:
            out.append({"rule": "rescreen", "fires": "a past counterparty is attributed later", "threshold": f"within {self.rescreen_days} days", "severity": "as the rule it would have fired"})
        if self.behavioral:
            out += [
                {
                    "rule": "restricted-24h",
                    "fires": f"sent to {', '.join(self.restricted) or 'restricted'} in 24 h",
                    "threshold": f"total >= EUR {self.restricted_24h_sum_eur:,.0f}",
                    "severity": "medium",
                },
                {
                    "rule": "structuring-7d",
                    "fires": f"unhosted withdrawals at 60-100% of EUR {self.travel_rule_eur:,.0f} in 7 days",
                    "threshold": f"count >= {self.structuring_count_7d}",
                    "severity": "high",
                },
                {
                    "rule": "escalating-payments",
                    "fires": "rising payments to one counterparty the customer had not paid in the 30 days before",
                    "threshold": f"{self.escalating_count_14d} in 14 days, total >= EUR {self.escalating_min_total_eur:,.0f}",
                    "severity": "high",
                },
                {
                    "rule": "pass-through",
                    "fires": f"deposit with high-risk or prohibited exposure forwarded within {self.pass_through_hours} h",
                    "threshold": f"forwarded >= {self.pass_through_share:.0%}",
                    "severity": "high",
                },
            ]
        return out

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "rules": self.rules()}


class DiscoveryError(ValueError):
    pass


def compile_policy(discovery: dict[str, Any], kit: dict[str, Any]) -> Policy:
    """Refuses discovery notes it cannot turn into rules safely, instead of guessing."""
    ra = discovery.get("risk_appetite") or {}
    groups = {g: list(ra.get(g) or []) for g in ("prohibited", "high_risk", "restricted")}
    unknown = sorted({c for v in groups.values() for c in v} - set(CATEGORIES))
    if unknown:
        raise DiscoveryError(f"unknown categories in risk appetite: {unknown}")
    seen: dict[str, str] = {}
    for g, cats in groups.items():
        for c in cats:
            if c in seen:
                raise DiscoveryError(f"{c} is listed as both {seen[c]} and {g}")
            seen[c] = g
    notes = []
    for c in SEVERE:  # a risk appetite that leaves out a severe category is almost always an omission
        if c not in seen:
            groups["prohibited"].append(c)
            notes.append(f"{c} was not in the risk appetite; treated as prohibited. Confirm with the customer.")
    hops = int(ra.get("max_indirect_hops", 3))
    if not 1 <= hops <= 6:
        raise DiscoveryError("max_indirect_hops must be between 1 and 6")
    thr = float((discovery.get("travel_rule") or {}).get("unhosted_threshold_eur", 1000))
    c = kit["compile"]
    return Policy(
        name=str(discovery.get("name", "prospect")),
        prohibited=groups["prohibited"],
        high_risk=groups["high_risk"],
        restricted=groups["restricted"],
        max_hops=hops,
        indirect_share_prohibited=float(c["indirect_share_prohibited"]),
        indirect_share_high_risk=float(c["indirect_share_high_risk"]),
        high_risk_direct_min_eur={s: float(c["high_risk_direct_min_eur"][s]) for s in SEGMENTS},
        restricted_24h_sum_eur=float(c["restricted_24h_sum_eur"]),
        structuring_count_7d=int(c["structuring_count_7d"]),
        travel_rule_eur=thr,
        pass_through_hours=int(c["pass_through_hours"]),
        pass_through_share=float(c["pass_through_share"]),
        rescreen_days=int(c["rescreen_days"]),
        escalating_count_14d=int(c["escalating_count_14d"]),
        escalating_min_total_eur=float(c["escalating_min_total_eur"]),
        notes=notes,
    )


def vendor_default(discovery: dict[str, Any]) -> Policy:
    """The out-of-the-box rule pack a team starts with: every risky category, any share, any amount, 3 hops,
    no behavioural rules, no re-screening, no segments."""
    risky = ["sanctions", "ransomware", "darknet_market", "mixer", "scam", "stolen_funds"]
    return Policy(
        name="vendor default",
        prohibited=risky[:3],
        high_risk=risky[3:],
        restricted=["gambling", "no_kyc_exchange"],
        max_hops=3,
        indirect_share_prohibited=0.0,
        indirect_share_high_risk=0.0,
        high_risk_direct_min_eur=dict.fromkeys(SEGMENTS, 0.0),
        restricted_24h_sum_eur=0.0,
        structuring_count_7d=10**6,
        travel_rule_eur=float((discovery.get("travel_rule") or {}).get("unhosted_threshold_eur", 1000)),
        pass_through_hours=0,
        pass_through_share=2.0,
        rescreen_days=0,
        high_risk_hops=3,
        behavioral=False,
        segments=False,
    )
