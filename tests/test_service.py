import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocp import config
from ocp.kit.webhooks import sign
from ocp.service.app import create_app


@pytest.fixture
def api(tmp_path: Path) -> TestClient:
    return TestClient(create_app(str(tmp_path / "ocp.sqlite3"), "whsec_test"))


def post(api: TestClient, event: dict[str, object], secret: str = "whsec_test") -> int:
    body = json.dumps(event)
    return api.post("/v1/webhooks/alerts", content=body, headers={"X-Signature": sign(secret, int(time.time()), body), "content-type": "application/json"}).status_code


def test_health(api: TestClient) -> None:
    assert api.get("/healthz").json() == {"status": "ok"}


def test_webhook_to_case_to_decision(api: TestClient) -> None:
    e = {"event_id": "e1", "type": "created", "version": 1, "alert": {"id": "al-1", "category": "mixer", "rule": "indirect"}}
    assert post(api, e) == 200 and post(api, e) == 200
    assert post(api, {**e, "event_id": "x"}, "wrong") == 401
    assert len(api.get("/v1/cases").json()) == 1
    d = api.post("/v1/cases/al-1/decision", json={"decision": "close", "analyst": "ana", "reason": "known exchange hot wallet"})
    assert d.status_code == 200 and d.json()["status"] == "close"
    assert api.post("/v1/cases/al-1/decision", json={"decision": "escalate", "analyst": "ana", "reason": "changed my mind here"}).status_code == 409
    assert api.get("/v1/cases/nope").status_code == 404


def test_sanctions_case_needs_a_second_reviewer_to_close(api: TestClient) -> None:
    post(api, {"event_id": "s1", "type": "created", "version": 1, "alert": {"id": "al-2", "category": "sanctions"}})
    body = {"decision": "close", "analyst": "ana", "reason": "false match on cluster label"}
    assert api.post("/v1/cases/al-2/decision", json=body).status_code == 409
    assert api.post("/v1/cases/al-2/decision", json={**body, "second_reviewer": "ana"}).status_code == 409
    assert api.post("/v1/cases/al-2/decision", json={**body, "second_reviewer": "ben"}).status_code == 200


def test_compile_policy_and_refusals(api: TestClient) -> None:
    ok = api.post("/v1/policy/compile", json=config.prospect("uk-emi"))
    assert ok.status_code == 200 and ok.json()["max_hops"] == 2
    bad = api.post("/v1/policy/compile", json={"risk_appetite": {"prohibited": ["unicorns"]}})
    assert bad.status_code == 422 and "unknown" in bad.json()["detail"]


def test_draft_check(api: TestClient) -> None:
    body = {
        "evidence": [{"id": "E1", "label": "alert", "value": "indirect on mixer, EUR 1,250"}],
        "draft": {"recommend": "close", "sentences": [{"text": "EUR 1,250 to a mixer.", "cites": ["E1"]}, {"text": "Customer is a student.", "cites": []}]},
    }
    r = api.post("/v1/triage/check-draft", json=body).json()
    assert not r["accepted"] and any("uncited" in p for p in r["problems"])
