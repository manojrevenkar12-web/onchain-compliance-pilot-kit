"""ocp dev | heldout | report | gate | webhooks | plan | serve"""

from __future__ import annotations

import argparse
import json
import sys

from .lab import report, study


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ocp")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dev", help="every design on the development prospects, then the reports")
    sub.add_parser("heldout", help="the held-out prospect, once (reports/heldout.lock)")
    sub.add_parser("report", help="regenerate REPORT.md, the README block and the console data")
    g = sub.add_parser("gate", help="exit 1 unless every gate passes on a split")
    g.add_argument("split", nargs="?", default="dev")
    f = sub.add_parser("webhooks", help="the webhook lab alone")
    f.add_argument("--n", type=int, default=200)
    pl = sub.add_parser("plan", help="compile a discovery file into a policy and print it")
    pl.add_argument("discovery")
    s = sub.add_parser("serve", help="the webhook receiver and case API")
    s.add_argument("--port", type=int, default=8080)
    a = ap.parse_args(argv)
    if a.cmd == "dev":
        study.write("dev", study.run_split("dev"))
        report.write_all()
    elif a.cmd == "heldout":
        try:
            study.run_heldout_once()
        except study.HeldOutLocked as e:
            print(e, file=sys.stderr)
            return 3
        report.write_all()
    elif a.cmd == "report":
        report.write_all()
    elif a.cmd == "gate":
        res = json.loads((study.REPORTS / f"{a.split}.json").read_text(encoding="utf-8"))
        for row in res["gates"]["kit"]:
            print(("PASS " if row["pass"] else "FAIL ") + f"{row['gate']}: {row['value']:.4g} ({row['kind']} {row['limit']:g})")
        return 0 if res["gates"]["kit_pass"] else 1
    elif a.cmd == "webhooks":
        from .lab.webhook_lab import run_lab

        print(json.dumps(run_lab(a.n, 1), indent=1))
    elif a.cmd == "plan":
        import yaml

        from . import config
        from .kit.policy import compile_policy

        with open(a.discovery, encoding="utf-8") as fh:
            disc = yaml.safe_load(fh)
        print(json.dumps(compile_policy(disc, config.kit()).as_dict(), indent=1))
    elif a.cmd == "serve":
        import uvicorn

        uvicorn.run("ocp.service.app:create_app", factory=True, host="0.0.0.0", port=a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
