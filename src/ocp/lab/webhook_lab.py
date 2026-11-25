"""The webhook lab: alert events for a pilot sent to the receiver the way the internet delivers them. Deliveries
are duplicated, reordered and retried after timeouts; the receiver sometimes dies after committing and before
answering; an attacker posts forged events and replays old ones. Afterwards: every real alert has exactly one
ticket and one case at its latest version, every event is in the activity log once, and nothing forged or
replayed got in. The same scenarios run against receivers with one safeguard removed."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from ..kit.webhooks import TOLERANCE_S, Receiver, Safeguards, sign
from ..rng import keyed

SECRET = "whsec_lab"
VARIANTS: dict[str, tuple[Safeguards, bool]] = {  # receiver safeguards, sender retries
    "kit": (Safeguards(), True),
    "no_signature": (Safeguards(signature=False), True),
    "no_dedupe": (Safeguards(dedupe=False), True),
    "no_versioning": (Safeguards(versioning=False), True),
    "no_retries": (Safeguards(), False),
}


def scenario(seed: int, guard: Safeguards, retries: bool) -> list[str]:
    r = keyed(seed, "webhooks")
    rec = Receiver(SECRET, guard=guard)
    now = 1_800_000_000
    latest: dict[str, int] = {}
    sent: list[tuple[int, str, str]] = []  # due time, event id, body
    for a in range(int(r.integers(3, 9))):
        aid = f"alert-{a}"
        n = int(r.integers(1, 5))
        for v in range(1, n + 1):
            eid = f"evt-{a}-{v}"
            body = json.dumps({"event_id": eid, "type": "created" if v == 1 else "updated", "version": v, "alert": {"id": aid, "risk_eur": int(100 * v), "rule": "indirect"}})
            sent.append((int(r.integers(0, 120)) + 30 * v, eid, body))
            latest[aid] = v
    forged = [json.dumps({"event_id": f"forged-{i}", "type": "created", "version": 1, "alert": {"id": f"fake-{i}", "risk_eur": 0}}) for i in range(int(r.integers(1, 3)))]
    queue: list[tuple[int, str, str, int, str]] = []  # due, body, header, attempt, the key the sender signs with
    for due, _eid, body in sorted(sent):
        queue.append((due, body, sign(SECRET, now + due, body), 0, SECRET))
        if r.random() < 0.25:  # the sender's queue delivers it twice
            queue.append((due + int(r.integers(0, 90)), body, sign(SECRET, now + due, body), 0, SECRET))
    for body in forged:
        queue.append((int(r.integers(0, 200)), body, sign("not-the-secret", now, body), 0, "not-the-secret"))
    if sent:  # a valid event captured and replayed much later
        _, _, body = sent[int(r.integers(0, len(sent)))]
        queue.append((TOLERANCE_S + 600, body, sign(SECRET, now, body), 9, ""))  # replayed as captured, never re-signed
    while queue:
        queue.sort(key=lambda q: (q[0], q[1]))
        i = int(r.integers(0, min(3, len(queue))))  # nearby deliveries can arrive out of order
        due, body, header, attempt, key = queue.pop(i)
        roll = r.random()
        if roll < 0.10:
            status = 503  # the receiver is down or deploying: nothing applied
        else:
            try:
                status = rec.handle(header, body, now + due, crash_after_commit=roll > 0.92)
            except ConnectionError:
                status = 0  # timeout after the commit: the sender cannot know it was applied
        if status not in (200, 401, 400) and retries and attempt < 8 and key:
            later = due + 30 * 2**attempt
            queue.append((later, body, sign(key, now + later, body), attempt + 1, key))
    # anything the sender gave up on is lost
    bad: list[str] = []
    cases = {c["alert_id"]: c for c in rec.cases()}
    tickets = Counter(rec.tickets())
    log = Counter(e for _, e in rec.activity())
    for aid, v in latest.items():
        if aid not in cases:
            bad.append(f"lost:{aid}")
        elif cases[aid]["version"] != v:
            bad.append(f"stale:{aid}")
        if tickets.get(aid, 0) > 1:
            bad.append(f"duplicate_ticket:{aid}")
        if aid in cases and tickets.get(aid, 0) == 0:
            bad.append(f"no_ticket:{aid}")
    bad += [f"forged:{a}" for a in cases if a.startswith("fake-")]
    bad += [f"double_logged:{e}" for e, n in log.items() if n > 1]
    return bad


def run_lab(n: int, base_seed: int) -> dict[str, Any]:
    out: dict[str, Any] = {"scenarios": n, "variants": {}}
    for name, (guard, retries) in VARIANTS.items():
        kinds: Counter[str] = Counter()
        broken = 0
        for i in range(n):
            bad = scenario(base_seed * 100_000 + i, guard, retries)
            broken += bool(bad)
            kinds.update({b.split(":")[0] for b in bad})
        out["variants"][name] = {"scenarios_broken": broken, "share_broken": broken / n, "by_kind": dict(sorted(kinds.items()))}
    return out
