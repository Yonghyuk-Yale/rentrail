"""No-AI check of the time machine: what each demo user sees on key dates.

    python scripts/check_timeline.py      (uses a throwaway data folder)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["RENTRAIL_DATA_DIR"] = tempfile.mkdtemp(prefix="rentrail_tl_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import cases  # noqa: E402
import clock  # noqa: E402
import db  # noqa: E402
import demo  # noqa: E402


def view(email: str, day: str, mode: str | None = None) -> None:
    u = db.one("SELECT * FROM users WHERE email = ?", (email,))
    u["demo_today"] = day
    if mode:
        u["mode"] = mode
    insp = [i["title"][:22] for i in db.q("SELECT * FROM inspections ORDER BY inspected_on")
            if clock.visible(i["inspected_on"], u) and ((u["mode"] == "subtenant") == bool(i["sublet_id"]) or u["mode"] == "sublessor")]
    bills = [b["kind"] + "@" + b["issued_on"] for b in db.q("SELECT * FROM bills WHERE user_id = ?", (u["id"],)) if clock.visible(b["issued_on"], u)]
    subs = []
    for s in db.q("SELECT * FROM sublets"):
        if cases.sublet_visible(s, u) and cases.sublet_role(s, u["id"]):
            st = cases.sublet_state(s, u)
            subs.append(f"{st['status']} escrow={cases.escrow_balance(s['id'], u)} ledger={len(cases.ledger_rows(s['id'], u))}")
    lease = cases.lease_for_user(u)
    tasks = [t["title_en"][:30] for t in cases.calendar(u) if t["days_left"] is not None and 0 <= t["days_left"] <= 30]
    print(f"{email.split('@')[0]:6} {mode or u['mode']:9} {day}: lease={(lease or {}).get('kind')} | inspections={insp} | "
          f"bills={len(bills)} | sublet={subs} | next30={tasks}")


if __name__ == "__main__":
    db.conn()
    demo.seed_raw()
    for day in ("2026-08-01", "2027-04-20", "2027-05-25", "2027-07-10", "2027-07-30", "2027-08-25"):
        view("alex@demo.rentrail", day, "sublessor")
    for day in ("2027-04-20", "2027-05-01", "2027-05-25", "2027-06-02", "2027-07-10", "2027-07-30"):
        view("jordan@demo.rentrail", day)
