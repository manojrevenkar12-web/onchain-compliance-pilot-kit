import json

from ocp.kit.webhooks import Receiver, Safeguards, sign, verify
from ocp.lab.webhook_lab import VARIANTS, run_lab, scenario

NOW = 1_800_000_000


def ev(eid: str, kind: str, v: int, aid: str = "a1") -> str:
    return json.dumps({"event_id": eid, "type": kind, "version": v, "alert": {"id": aid, "category": "mixer"}})


def test_sign_and_verify() -> None:
    h = sign("s", NOW, "{}")
    assert verify("s", h, "{}", NOW) and not verify("t", h, "{}", NOW)
    assert not verify("s", h, "{}", NOW + 301)  # replayed too late
    assert not verify("s", "garbage", "{}", NOW)


def test_once_in_order_one_ticket() -> None:
    r = Receiver("s")
    b1, b2 = ev("e1", "created", 1), ev("e2", "updated", 2)
    for b in (b2, b1, b1, b2):
        assert r.handle(sign("s", NOW, b), b, NOW) == 200
    assert r.cases()[0]["version"] == 2 and r.tickets() == ["a1"]
    assert [e for _, e in r.activity()] == ["e2"]  # the late version 1 is recorded as seen, never applied
    assert r.handle(sign("x", NOW, b1), b1, NOW) == 401 and r.handle(sign("s", NOW, "{}"), "{}", NOW) == 400


def test_without_dedupe_a_duplicate_is_logged_twice_and_without_versioning_old_wins() -> None:
    r = Receiver("s", guard=Safeguards(dedupe=False))
    b1 = ev("e1", "created", 1)
    r.handle(sign("s", NOW, b1), b1, NOW)
    r.handle(sign("s", NOW, b1), b1, NOW)
    assert [e for _, e in r.activity()] == ["e1", "e1"] and r.tickets() == ["a1"]
    r2 = Receiver("s", guard=Safeguards(versioning=False))
    b2 = ev("e2", "updated", 2)
    for b in (b2, b1):
        r2.handle(sign("s", NOW, b), b, NOW)
    assert r2.cases()[0]["version"] == 1


def test_lab_kit_holds_and_each_safeguard_matters() -> None:
    res = run_lab(80, 2)["variants"]
    assert res["kit"]["scenarios_broken"] == 0
    assert all(v["scenarios_broken"] > 0 for k, v in res.items() if k != "kit")
    g, retries = VARIANTS["no_versioning"]
    assert scenario(5, g, retries) == scenario(5, g, retries)
