"""The pilot's integration service: signed alert webhooks into cases, analyst decisions with a second reviewer for
the categories that must never be closed alone, policy compilation from discovery notes, and the draft check any
AI drafter has to pass."""

from __future__ import annotations

import os
import time
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .. import config
from ..kit.policy import DiscoveryError, compile_policy
from ..kit.triage import Draft, Evidence, check_draft
from ..kit.webhooks import Receiver

SECOND_REVIEW = {"sanctions", "ransomware", "darknet_market"}


class Decision(BaseModel):
    decision: Literal["escalate", "close"]
    analyst: str = Field(min_length=2, max_length=64)
    reason: str = Field(min_length=10, max_length=2000)
    second_reviewer: str | None = Field(default=None, max_length=64)


class EvidenceIn(BaseModel):
    id: str
    label: str
    value: str


class SentenceIn(BaseModel):
    text: str = Field(max_length=2000)
    cites: list[str]


class DraftIn(BaseModel):
    recommend: str
    sentences: list[SentenceIn]


class DraftCheck(BaseModel):
    evidence: list[EvidenceIn]
    draft: DraftIn


def create_app(db_path: str | None = None, secret: str | None = None) -> FastAPI:
    rec = Receiver(secret or os.environ.get("OCP_WEBHOOK_SECRET", "whsec_dev"), db_path or os.environ.get("OCP_DB", "ocp.sqlite3"))
    kit = config.kit()
    app = FastAPI(title="Onchain compliance pilot kit", version="1.0.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/webhooks/alerts")
    async def webhook(request: Request, x_signature: str = Header(default="")) -> dict[str, Any]:
        body = (await request.body()).decode("utf-8", errors="replace")
        status = rec.handle(x_signature, body, int(time.time()))
        if status == 401:
            raise HTTPException(401, "signature missing, wrong or outside the time window")
        if status == 400:
            raise HTTPException(400, "event must have event_id, type, version and alert.id")
        return {"status": "accepted"}

    @app.get("/v1/cases")
    def cases(status: str | None = None) -> list[dict[str, Any]]:
        return [c for c in rec.cases() if status is None or c["status"] == status]

    @app.get("/v1/cases/{alert_id}")
    def case(alert_id: str) -> dict[str, Any]:
        for c in rec.cases():
            if c["alert_id"] == alert_id:
                return c
        raise HTTPException(404, "no case for this alert")

    @app.post("/v1/cases/{alert_id}/decision")
    def decide(alert_id: str, body: Decision) -> dict[str, Any]:
        c = case(alert_id)
        if c["status"] != "open":
            raise HTTPException(409, f"case is already {c['status']}")
        cat = str(c["alert"].get("category", ""))
        if body.decision == "close" and cat in SECOND_REVIEW and (not body.second_reviewer or body.second_reviewer == body.analyst):
            raise HTTPException(409, f"closing a {cat} case needs a second reviewer other than {body.analyst}")
        rec.decide(alert_id, body.model_dump())
        return case(alert_id)

    @app.post("/v1/policy/compile")
    def compile_(discovery: dict[str, Any]) -> dict[str, Any]:
        try:
            return compile_policy(discovery, kit).as_dict()
        except DiscoveryError as e:
            raise HTTPException(422, str(e)) from e

    @app.post("/v1/triage/check-draft")
    def check(body: DraftCheck) -> dict[str, Any]:
        ev = [Evidence(e.id, e.label, e.value) for e in body.evidence]
        d = Draft(body.draft.recommend, tuple((s.text, tuple(s.cites)) for s in body.draft.sentences), "external")
        problems = check_draft(d, ev)
        return {"accepted": not problems, "problems": problems}

    return app
