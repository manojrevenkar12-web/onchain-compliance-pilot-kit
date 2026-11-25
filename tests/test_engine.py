import numpy as np

from ocp import config
from ocp.domain import CAT, NONE, Book, Screening
from ocp.kit.engine import all_alerts, behavioral_alerts, screen_alerts
from ocp.kit.policy import compile_policy

INF = float("inf")
DISC = {
    "name": "t",
    "risk_appetite": {"prohibited": ["sanctions", "ransomware", "darknet_market"], "high_risk": ["mixer", "scam"], "restricted": ["gambling"], "max_indirect_hops": 3},
    "travel_rule": {"unhosted_threshold_eur": 1000},
}


def make(rows: list[tuple]) -> tuple[Book, Screening]:
    # cust, hour, withdrawal, amount, unhosted, address, dcat, dknown, icat, ishare, ihops, iknown
    a = list(zip(*rows, strict=True))
    book = Book(
        2000,
        1000,
        np.zeros(3, dtype=int),
        np.zeros(3, dtype=int),
        np.full(3, 500),
        np.array(a[0]),
        np.array(a[1]),
        np.array(a[2], dtype=bool),
        np.array(a[3], dtype=float),
        np.array(a[4], dtype=bool),
        np.array(a[5]),
    )
    scr = Screening(np.array(a[6]), np.array(a[8]), np.array(a[9], dtype=float), np.array(a[10]), np.array(a[7], dtype=float), np.array(a[11], dtype=float))
    return book, scr


def test_direct_indirect_and_rescreen() -> None:
    pol = compile_policy(DISC, config.kit())
    book, scr = make(
        [
            (0, 10, True, 50.0, False, 1, CAT["sanctions"], 0.0, NONE, 0.0, 0, INF),  # prohibited, any amount
            (1, 20, True, 50.0, True, 2, NONE, INF, CAT["mixer"], 0.5, 1, 0.0),  # high-risk indirect over threshold
            (1, 30, True, 50.0, True, 3, NONE, INF, CAT["mixer"], 0.01, 1, 0.0),  # under the share threshold
            (2, 40, True, 300.0, False, 4, CAT["scam"], 100.0, NONE, 0.0, 0, INF),  # scam attributed 60 hours later
        ]
    )
    alerts = screen_alerts(book, scr, pol, 0, 2000)
    rules = sorted((a.cust, a.rule) for a in alerts)
    assert rules == [(0, "direct"), (1, "indirect"), (2, "direct-rescreen")]
    assert [a.hour for a in alerts if a.rule == "direct-rescreen"] == [100]
    pol.rescreen_days = 0
    assert sorted(a.rule for a in screen_alerts(book, scr, pol, 0, 2000)) == ["direct", "indirect"]


def test_structuring_and_escalating_payments() -> None:
    pol = compile_policy(DISC, config.kit())
    rows = [(0, 10 + 10 * i, True, 900.0, True, 100 + i, NONE, INF, NONE, 0.0, 0, INF) for i in range(5)]  # just under the threshold
    rows += [(1, 50 + 24 * i, True, 300.0 * (i + 1), True, 7, NONE, INF, NONE, 0.0, 0, INF) for i in range(4)]  # rising, one payee
    book, scr = make(rows)
    got = {(a.cust, a.rule) for a in behavioral_alerts(book, scr, pol, 0, 2000)}
    assert (0, "structuring-7d") in got and (1, "escalating-payments") in got
    pol.behavioral = False
    assert behavioral_alerts(book, scr, pol, 0, 2000) == []


def test_all_alerts_are_unique_by_key() -> None:
    pol = compile_policy(DISC, config.kit())
    book, scr = make([(0, 10, True, 50.0, False, 1, CAT["sanctions"], 0.0, NONE, 0.0, 0, INF)] * 1)
    keys = [a.key for a in all_alerts(book, scr, pol, 0, 2000)]
    assert len(keys) == len(set(keys))
