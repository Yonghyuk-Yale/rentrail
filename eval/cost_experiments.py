"""Did cost cutting hurt quality? Two experiments with real model calls (gpt-6-luna).

1. Lease page selection: send only the pages that contain lease terms (default) vs. send every page.
   Run on a long real lease (58 pages; private, never committed) and on the 4-page sample lease.
2. Video keyframes: 6 keyframes (default) vs. 3 vs. 12 for the move-out walkthrough video.

Only numbers are saved (eval/cost_experiments.json) — no lease text.

    python eval/cost_experiments.py --lease "../data/RENTCafe_LeaseAgreement_Executed.pdf"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["RENTRAIL_DATA_DIR"] = tempfile.mkdtemp(prefix="rentrail_exp_")
os.environ["RENTRAIL_SEED_DEMO"] = "0"
sys.path.insert(0, str(ROOT / "backend"))

import auth  # noqa: E402
import cases  # noqa: E402
import db  # noqa: E402
import llm  # noqa: E402
import privacy  # noqa: E402
import storage  # noqa: E402

FIELDS = ["lease_start", "lease_end", "monthly_rent", "security_deposit", "inventory_form_hours",
          "move_out_notice_days", "auto_renews", "sublet_requires_consent", "insurance_min_liability"]


async def lease_variant(user: dict, pdf: bytes, budget: int, label: str) -> dict:
    cases.LEASE_CHAR_BUDGET = budget
    fid = storage.save(user["id"], "lease", label, "application/pdf", pdf)
    lid = db.insert("leases", user_id=user["id"], title=label, file_id=fid, created_at=db.now())
    rid = llm.start_run(user["id"], "lease", label)
    t = time.perf_counter()
    card = await cases.analyse_lease(user, lid, rid)
    llm.finish_run(rid)
    run = db.one("SELECT * FROM runs WHERE id = ?", (rid,))
    meta = db.loads(db.one("SELECT analysis_meta FROM leases WHERE id = ?", (lid,))["analysis_meta"], {})
    return {"variant": label, "pages_sent": len(meta["pages_sent"]), "page_count": meta["page_count"],
            "chars_sent": meta["chars_sent"], "chars_total": meta["chars_total"],
            "input_tokens": run["input_tokens"], "output_tokens": run["output_tokens"], "cost_usd": round(run["cost_usd"], 5),
            "seconds": round(time.perf_counter() - t, 1), "clauses": len(card["clauses"]), "red_flags": len(card["red_flags"]),
            "fields": {k: card.get(k) for k in FIELDS}}


async def video_variant(user: dict, video: bytes, frames: int) -> dict:
    kf, meta = privacy.video_keyframes(video, max_frames=frames)
    iid = db.insert("inspections", user_id=user["id"], kind="move_out", title=f"{frames} frames", inspected_on="2027-07-31", created_at=db.now())
    for fr in kf:
        fid = storage.save(user["id"], "frame", f"f{fr.t_seconds}", "image/jpeg", fr.jpeg)
        db.insert("evidence", inspection_id=iid, file_id=fid, room="Bedroom", label=f"{fr.t_seconds}s", t_seconds=fr.t_seconds, created_at=db.now())
    rid = llm.start_run(user["id"], "inspection", f"{frames} frames")
    t = time.perf_counter()
    rep = await cases.inspect(user, iid, rid)
    llm.finish_run(rid)
    run = db.one("SELECT * FROM runs WHERE id = ?", (rid,))
    return {"max_frames": frames, "frames_sent": len(kf), "input_tokens": run["input_tokens"], "output_tokens": run["output_tokens"],
            "cost_usd": round(run["cost_usd"], 5), "seconds": round(time.perf_counter() - t, 1),
            "crack_found": any("crack" in f["damage_type"].lower() for f in rep["findings"]),
            "findings": len(rep["findings"]), "false_alarms": sum(1 for f in rep["findings"] if "crack" not in f["damage_type"].lower())}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lease", type=Path, help="a long real lease PDF (kept private)")
    args = ap.parse_args()
    db.conn()
    uid = auth.create_user("exp@local.test", "Experiment User", "experiment-pass")
    user = db.one("SELECT * FROM users WHERE id = ?", (uid,))
    out: dict = {"model": "gpt-6-luna", "date": db.now(), "lease": [], "video": []}

    sample = (ROOT / "backend/sample_data/sample_lease.pdf").read_bytes()
    out["lease"].append({"doc": "sample (4 pages)", **await lease_variant(user, sample, cases.LEASE_CHAR_BUDGET, "sample-selected")})
    if args.lease and args.lease.exists():
        real = args.lease.read_bytes()
        for budget, label in ((60_000, "real-selected (default)"), (10_000_000, "real-all-pages")):
            out["lease"].append({"doc": "real lease (private)", **await lease_variant(user, real, budget, label)})
        a, b = out["lease"][-2]["fields"], out["lease"][-1]["fields"]
        out["lease_field_agreement"] = {k: a[k] == b[k] for k in FIELDS}
        for row in out["lease"]:
            if row["doc"].startswith("real"):
                row["fields"] = {k: ("found" if v is not None else None) for k, v in row["fields"].items()}  # no private values

    video = (ROOT / "backend/sample_data/media/After_Crack.mp4").read_bytes()
    for n in (3, 6, 12):
        out["video"].append(await video_variant(user, video, n))

    (ROOT / "eval/cost_experiments.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "date"}, indent=1, default=str))


if __name__ == "__main__":
    asyncio.run(main())
