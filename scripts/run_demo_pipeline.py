"""Live through the demo story with the real agents, each step on its simulated date (real model calls).

Used to (1) test the whole app end to end and (2) produce the fixtures shipped with the repo:
    (delete backend/sample_data/fixtures and instance/ first for a clean raw seed)
    python run.py --no-browser            (in another terminal)
    python scripts/run_demo_pipeline.py   [--base http://127.0.0.1:8460]
    python backend/demo.py export
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx


def wait(c: httpx.Client, run_id: int, label: str, timeout: float = 420) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = c.get(f"/api/runs/{run_id}").json()
        if r["status"] in ("done", "failed"):
            calls = ", ".join(f"{x['agent']}({x['input_tokens']}/{x['cached_tokens']}/{x['output_tokens']})" for x in r["calls"])
            print(f"[{r['status']}] {label:<44} run {run_id}: in {r['input_tokens']:>6} cached {r['cached_tokens']:>6} "
                  f"out {r['output_tokens']:>5} ${r['cost_usd']:.5f} {time.time() - t0:5.1f}s | {calls}")
            if r["status"] == "failed":
                print("   error:", r.get("error"))
            return r
        time.sleep(2)
    raise TimeoutError(label)


class Person:
    def __init__(self, base: str, who: str):
        self.c = httpx.Client(base_url=base, timeout=120)
        self.c.post("/api/auth/demo", json={"who": who}).raise_for_status()

    def at(self, day: str, mode: str | None = None) -> "Person":
        body = {"demo_today": day, "lang": "en"}
        if mode:
            body["mode"] = mode
        self.c.patch("/api/me", json=body).raise_for_status()
        return self

    def run(self, path: str, label: str, body: dict | None = None) -> dict:
        r = self.c.post(path, json=body or {})
        if r.status_code >= 400:
            print(f"[skip] {label}: {r.status_code} {r.text[:200]}")
            return {}
        return wait(self.c, r.json()["run_id"], label)

    def insp(self, title_prefix: str) -> dict:
        return next(i for i in self.c.get("/api/inspections").json() if i["title"].startswith(title_prefix))


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8460")
    args = ap.parse_args()
    alex, jordan = Person(args.base, "alex"), Person(args.base, "jordan")

    # 2026: lease, move-in, first bills
    alex.at("2026-08-01", "tenant")
    lease = alex.c.get("/api/leases/current").json()["lease"]
    alex.run(f"/api/leases/{lease['id']}/analyze", "Clerk: master lease (Aug 1 2026)")
    alex.run(f"/api/inspections/{alex.insp('Move-in walkthrough')['id']}/run", "Detective: move-in, clean (Aug 1 2026)")
    # Human in the loop: in the story the move-in unit is clean, so anything the Detective flags here is a false
    # alarm that Alex reviews and marks "Not damage" (it stays on record as dismissed).
    mi = alex.insp("Move-in walkthrough")
    for f in (mi["result"] or {}).get("findings", []):
        alex.c.post(f"/api/inspections/{mi['id']}/review", json={"action": "dismiss", "index": 0,
                    "reason": f"Not damage - Alex checked the {f['room'].lower()} in person: clean at move-in"})
        print(f"[review] dismissed move-in false alarm: {f['room']} {f['item']} {f['damage_type']} ({f['confidence']})")
    alex.run("/api/chat", "Copilot: first week (Aug 1 2026)", {"message": "What do I need to do in my first week?", "page": "home"})
    alex.at("2026-09-10")
    for b in alex.c.get("/api/bills").json():
        alex.run(f"/api/bills/{b['id']}/read", f"Treasurer: {b['file_name']}")

    # 2027 spring: sublet listed, matched, documents, sublease
    alex.at("2027-04-20", "sublessor")
    sid = alex.c.get("/api/sublets").json()[0]["id"]
    alex.run(f"/api/sublets/{sid}/docs", "Sheriff: consent letter + draft (Apr 20)")
    jordan.at("2027-05-01")
    jordan.run("/api/chat", "Copilot (Jordan): deposit (May 1)", {"message": "When do I need to pay the sublet deposit, and is it safe?", "page": "home"})
    alex.at("2027-05-12")
    sub = alex.c.get("/api/leases/current?kind=sublease").json()["lease"]
    alex.run(f"/api/leases/{sub['id']}/analyze", "Clerk: sublease (May 12)")
    jordan.at("2027-05-23")
    for p in jordan.c.get("/api/posts?category=qa").json():
        jordan.run(f"/api/posts/{p['id']}/ask-dan", f"Counsel: Q&A #{p['id']} (May 23)")

    # summer: hand-off, June bill, return, settlement
    alex.at("2027-06-01")
    alex.run(f"/api/inspections/{alex.insp('Sublet hand-off')['id']}/run", "Detective: hand-off (Jun 1)")
    alex.at("2027-07-08")
    for b in alex.c.get("/api/bills").json():
        if not b["result"]:
            alex.run(f"/api/bills/{b['id']}/read", f"Treasurer: {b['file_name']} (Jul 8)")
    alex.at("2027-07-28")
    alex.run(f"/api/inspections/{alex.insp('Sublet return')['id']}/run", "Detective: return (Jul 28)")
    alex.at("2027-07-29")
    alex.run("/api/precheck", "Detective + Counsel: move-out precheck (Jul 29)")
    alex.at("2027-07-30")
    alex.run(f"/api/sublets/{sid}/settle", "Sheriff + Chief: escrow settlement (Jul 30)")
    alex.c.post(f"/api/sublets/{sid}/decision", json={"decision": "accept"})

    # move-out and the landlord's statement
    alex.at("2027-07-31", "tenant")
    alex.run(f"/api/inspections/{alex.insp('Move-out walkthrough')['id']}/run", "Detective: move-out (Jul 31)")
    alex.run(f"/api/inspections/{alex.insp('Safety test')['id']}/run", "Detective: safety-test video")
    alex.run("/api/compare", "Detective: move-in vs move-out", {"earlier_id": alex.insp("Move-in walkthrough")["id"],
                                                                "later_id": alex.insp("Move-out walkthrough")["id"]})
    alex.at("2027-08-24")
    d = alex.c.get("/api/disputes").json()[0]
    alex.run(f"/api/disputes/{d['id']}/rerun", "Counsel + Chief: deposit case (Aug 24)")
    alex.at("2027-08-27")
    for p in alex.c.get("/api/posts?category=qa").json():
        if p["comments"] == 0:
            alex.run(f"/api/posts/{p['id']}/ask-dan", f"Counsel: Q&A #{p['id']} (Aug 27)")

    # where the demo starts
    alex.at("2026-08-01", "tenant")
    jordan.at("2027-06-02")
    t = alex.c.get("/api/tokens").json()["total"]
    print(f"ALEX TOTAL runs {t['runs']} in {t['input_tokens']} cached {t['cached_tokens']} out {t['output_tokens']} ${t['cost_usd']:.4f}")


if __name__ == "__main__":
    main()
