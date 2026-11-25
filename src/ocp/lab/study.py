"""The study: every design on every prospect with the same luck, the webhook lab, and the gates. The held-out
prospect runs once, behind reports/heldout.lock (ADR 0006)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .. import config
from ..kit.policy import compile_policy
from ..sim.evaluate import run_design
from ..world.world import build_site
from .webhook_lab import run_lab

REPORTS = config.REPORTS
LOCK = REPORTS / "heldout.lock"


class HeldOutLocked(RuntimeError):
    pass


def config_hash() -> str:
    h = hashlib.sha256()
    for p in sorted(config.CONFIG.rglob("*.yml")):
        h.update(p.read_bytes())
    return h.hexdigest()


def _round(x: Any) -> Any:
    if isinstance(x, (float, np.floating)):
        return round(float(x), 5)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v) for v in x]
    return x


def _mean(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in rows[0]:
        if k == "criteria":
            out[k] = {
                c: {
                    "met": sum(r[k][c]["pass"] for r in rows),
                    "of": len(rows),
                    "value": float(np.mean([r[k][c]["value"] for r in rows])),
                    "limit": rows[0][k][c]["limit"],
                    "kind": rows[0][k][c]["kind"],
                }
                for c in rows[0][k]
            }
        else:
            out[k] = float(np.mean([r.get(k, 0.0) for r in rows]))
    return out


def check_gates(res: dict[str, Any]) -> dict[str, Any]:
    g = config.gates()
    gk, gw = g["kit"], g["webhooks"]
    P = res["prospects"]
    kit = {p: P[p]["designs"]["kit"] for p in P}
    asis = {p: P[p]["designs"]["as_is"] for p in P}
    manual = {p: P[p]["designs"]["no_triage"] for p in P}
    met = sum(c["met"] for k in kit.values() for c in k["criteria"].values())
    total = sum(c["of"] for k in kit.values() for c in k["criteria"].values())
    rows = [
        ("Prospect success criteria the kit meets (share of prospect, seed and criterion)", met / total, gk["success_criteria_met_min"], "min"),
        (
            "Reportable customers escalated in time, points over the as-is (worst prospect)",
            min(100 * (kit[p]["reportable_escalated_share"] - asis[p]["reportable_escalated_share"]) for p in P),
            gk["reportable_escalated_over_as_is_pts_min"],
            "min",
        ),
        ("Sanctions-exposed customers escalated in time (worst prospect)", min(kit[p]["sanctions_escalated_share"] for p in P), gk["sanctions_escalated_min"], "min"),
        ("Reportable customers lost after a machine-closed alert (worst prospect)", max(kit[p]["reportable_missed_after_machine_close"] for p in P), gk["missed_after_machine_close_max"], "max"),
        (
            "Analyst minutes a day, ratio to the same rules reviewed by hand (worst prospect)",
            max(kit[p]["analyst_minutes_per_day"] / max(manual[p]["analyst_minutes_per_day"], 1e-9) for p in P),
            gk["analyst_minutes_vs_manual_max"],
            "max",
        ),
        ("Alerts waiting at the end, ratio to the as-is (worst prospect)", max(kit[p]["backlog_at_end"] / max(asis[p]["backlog_at_end"], 1e-9) for p in P), gk["backlog_vs_as_is_max"], "max"),
    ]
    w = res["webhooks"]["variants"]
    rows.append(("Webhook-lab scenarios with a broken invariant, kit receiver", w["kit"]["scenarios_broken"], gw["kit_scenarios_broken_max"], "max"))
    if gw["each_safeguard_matters"]:
        rows.append(("Fewest broken scenarios with one safeguard removed", min(v["scenarios_broken"] for k, v in w.items() if k != "kit"), 1, "min"))
    out = [{"gate": n, "value": float(v), "limit": float(lim), "kind": k, "pass": bool(v <= lim if k == "max" else v >= lim)} for n, v, lim, k in rows]
    return {"kit": out, "kit_pass": all(r["pass"] for r in out)}


def run_split(split: str) -> dict[str, Any]:
    seeds = [int(s) for s in config.seeds()[split]]
    variant = "heldout" if split == "heldout" else "dev"
    dcfg = config.designs()
    kit = config.kit()
    res: dict[str, Any] = {
        "split": split,
        "seeds": seeds,
        "labels": {n: d["label"] for n, d in dcfg["designs"].items()},
        "main": dcfg["main"],
        "ablations": dcfg["ablations"],
        "prospects": {},
    }
    for name in config.prospect_names(split):
        per: dict[str, list[dict[str, Any]]] = {n: [] for n in dcfg["designs"]}
        sizes = []
        for s in seeds:
            site = build_site(s, name, variant)
            sizes.append({"seed": s, "customers": len(site.book.segment), "transfers": len(site.book.cust), "reportable": len(site.reportable_in(site.book.calibration_hours, site.book.hours))})
            for n, d in dcfg["designs"].items():
                per[n].append(run_design(site, d["switches"], kit))
        disc = config.prospect(name)
        res["prospects"][name] = {
            "discovery": {k: disc[k] for k in ("name", "kind", "jurisdiction", "customers", "risk_appetite", "review", "success_criteria")},
            "policy": compile_policy(disc, kit).as_dict(),
            "sizes": sizes,
            "designs": {n: _mean(rows) for n, rows in per.items()},
            "per_seed": [
                {"seed": s, **{n: {k: per[n][i][k] for k in ("reportable_escalated_share", "alerts_per_day", "backlog_at_end", "criteria_met")} for n in dcfg["main"]}} for i, s in enumerate(seeds)
            ],
        }
    days = build_site(seeds[0], config.prospect_names(split)[0], variant).cfg
    res["windows"] = {"calibration_days": int(days["calibration_days"]), "pilot_days": int(days["pilot_days"])}
    nw = int(config.seeds()["webhook_scenarios_heldout" if split == "heldout" else "webhook_scenarios_dev"])
    res["webhooks"] = run_lab(nw, 7 if split == "heldout" else 1)
    res["gates"] = check_gates(res)
    return _round(res)


def write(split: str, res: dict[str, Any]) -> Path:
    REPORTS.mkdir(exist_ok=True)
    p = REPORTS / f"{split}.json"
    p.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    return p


def run_heldout_once() -> dict[str, Any]:
    if LOCK.exists():
        raise HeldOutLocked(f"{LOCK} exists: the held-out prospect has been run. Add a new one under a new name and an ADR.")
    REPORTS.mkdir(exist_ok=True)
    LOCK.write_text(json.dumps({"seeds": config.seeds()["heldout"], "prospects": config.prospect_names("heldout"), "config_sha256": config_hash()}, indent=1) + "\n", encoding="utf-8")
    res = run_split("heldout")
    write("heldout", res)
    return res
