"""Rentrail web server: the JSON API plus the built React app, on one port.

Run:  python run.py   (or: uvicorn app:app --app-dir backend --port 8460)
"""

from __future__ import annotations

import asyncio
import re
import secrets
import traceback
from datetime import date, timedelta
from typing import Any, Awaitable, Callable

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import auth
import cases
import clock
import config
import copilot
import db
import guard
import law
import llm
import privacy
import storage
from agents import ROSTER
from auth import current_user

app = FastAPI(title="Rentrail", version="1.0")
_TASKS: set = set()
_LOOP: asyncio.AbstractEventLoop | None = None  # the server's event loop; sync endpoints run in threads


# ---------------------------------------------------------------------------
# startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def _startup() -> None:
    global _LOOP
    _LOOP = asyncio.get_running_loop()
    db.conn()
    if config.SEED_DEMO:
        import demo
        demo.ensure_seeded()


# ---------------------------------------------------------------------------
# runs in the background
# ---------------------------------------------------------------------------

def start(user: dict, kind: str, title: str, work: Callable[[int], Awaitable[Any]], ref: str | None = None) -> dict:
    """Create a run, do the work in the background, return the run id at once (the UI polls)."""
    run_id = llm.start_run(user["id"], kind, title, ref)

    async def runner() -> None:
        try:
            result = await work(run_id)
            db.ex("UPDATE runs SET result = ? WHERE id = ?", (db.dumps(result), run_id))
            llm.finish_run(run_id)
        except guard.BudgetBlocked as exc:
            llm.finish_run(run_id, str(exc))
        except llm.ModelUnavailable as exc:
            llm.finish_run(run_id, str(exc))
        except Exception as exc:  # report, never crash the server
            traceback.print_exc()
            llm.finish_run(run_id, f"{type(exc).__name__}: {str(exc)[:400]}")

    future = asyncio.run_coroutine_threadsafe(runner(), _LOOP)
    _TASKS.add(future)
    future.add_done_callback(_TASKS.discard)
    return {"run_id": run_id}


def _need(row: dict | None, what: str = "Item") -> dict:
    if not row:
        raise HTTPException(404, f"{what} not found.")
    return row


def _sublet_for(user: dict, sublet_id: int) -> tuple[dict, str]:
    s = _need(db.one("SELECT * FROM sublets WHERE id = ?", (sublet_id,)), "Sublet")
    role = cases.sublet_role(s, user["id"])
    if not role:
        raise HTTPException(403, "You are not part of this sublet.")
    return s, role


def _inspection_for(user: dict, inspection_id: int) -> dict:
    insp = _need(db.one("SELECT * FROM inspections WHERE id = ?", (inspection_id,)), "Inspection")
    if insp["user_id"] == user["id"]:
        return insp
    if insp["sublet_id"]:
        _sublet_for(user, insp["sublet_id"])
        return insp
    raise HTTPException(403, "Not your inspection.")


def _can_view_file(user: dict, file_id: int) -> bool:
    row = db.one("SELECT user_id FROM files WHERE id = ?", (file_id,))
    if not row:
        return False
    if row["user_id"] == user["id"]:
        return True
    shared = db.one("SELECT i.sublet_id FROM evidence e JOIN inspections i ON i.id = e.inspection_id "
                    "WHERE (e.file_id = ? OR e.parent_file_id = ?) AND i.sublet_id IS NOT NULL", (file_id, file_id))
    if shared:
        s = db.one("SELECT * FROM sublets WHERE id = ?", (shared["sublet_id"],))
        return bool(s and cases.sublet_role(s, user["id"]))
    return False


async def _read_upload(f: UploadFile) -> bytes:
    data = await f.read()
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {config.MAX_UPLOAD_MB} MB.")
    return data


# ---------------------------------------------------------------------------
# health, auth, profile
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, **config.key_status(), "law": law.pack()["name"], "version": app.version}


def _set_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax", max_age=auth.SESSION_DAYS * 86400)


@app.post("/api/auth/register")
def register(resp: Response, body: dict = Body(...)) -> dict:
    uid = auth.create_user(body.get("email", ""), body.get("name", ""), body.get("password", ""), body.get("lang", "en"),
                           mode=body.get("mode", "tenant"))
    _set_cookie(resp, auth.new_session(uid))
    return {"user": auth.public_user(db.one("SELECT * FROM users WHERE id = ?", (uid,)))}


@app.post("/api/auth/login")
def login(resp: Response, body: dict = Body(...)) -> dict:
    user = auth.verify(body.get("email", ""), body.get("password", ""))
    if not user:
        raise HTTPException(401, "Wrong email or password.")
    _set_cookie(resp, auth.new_session(user["id"]))
    return {"user": auth.public_user(user)}


@app.post("/api/auth/demo")
def demo_login(resp: Response, body: dict = Body(...)) -> dict:
    import demo
    email = demo.DEMO_USERS.get(body.get("who", "alex"), {}).get("email")
    user = db.one("SELECT * FROM users WHERE email = ?", (email,)) if email else None
    if not user:
        demo.ensure_seeded()
        user = _need(db.one("SELECT * FROM users WHERE email = ?", (email,)), "Demo account")
    _set_cookie(resp, auth.new_session(user["id"]))
    return {"user": auth.public_user(user)}


@app.post("/api/auth/logout")
def logout(resp: Response, request: Request) -> dict:
    auth.end_session(request.cookies.get(auth.COOKIE))
    resp.delete_cookie(auth.COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(current_user)) -> dict:
    return {"user": auth.public_user(user), "today": clock.today(user).isoformat(),
            "tokens_today": guard.tokens_today(user["id"]), "daily_limit": config.USER_DAILY_TOKEN_LIMIT}


@app.patch("/api/me")
def update_me(body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    if "lang" in body and body["lang"] in ("en", "ko"):
        db.ex("UPDATE users SET lang = ? WHERE id = ?", (body["lang"], user["id"]))
    if body.get("mode") in auth.MODES:
        db.ex("UPDATE users SET mode = ? WHERE id = ?", (body["mode"], user["id"]))
    if "demo_today" in body:
        d = body["demo_today"]
        if d and not cases.parse_date(d):
            raise HTTPException(400, "Use YYYY-MM-DD.")
        db.ex("UPDATE users SET demo_today = ? WHERE id = ?", (d or None, user["id"]))
    return me(db.one("SELECT * FROM users WHERE id = ?", (user["id"],)))


@app.post("/api/demo/reset")
def demo_reset(user: dict = Depends(current_user)) -> dict:
    if not user["is_demo"]:
        raise HTTPException(403, "Only demo accounts can be reset.")
    import demo
    demo.reseed()
    return {"ok": True}


@app.get("/api/agents")
def roster() -> list[dict]:
    return ROSTER


@app.get("/api/law")
def law_pack() -> dict:
    return law.pack()


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------

@app.get("/api/files/{file_id}")
def get_file(file_id: int, request: Request, user: dict = Depends(current_user)) -> Response:
    """Files are cached by their SHA-256 fingerprint (ETag), never by id alone: after a demo reset the same
    id can point to a different file, and the browser must not show the old picture."""
    if not _can_view_file(user, file_id):
        raise HTTPException(404, "File not found.")
    meta = db.one("SELECT sha256, mime FROM files WHERE id = ?", (file_id,))
    etag = f'"{meta["sha256"]}"'
    headers = {"Cache-Control": "private, no-cache", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    row, data = storage.load(file_id)
    return Response(content=data, media_type=row["mime"], headers=headers)


@app.get("/api/files/{file_id}/verify")
def verify_file(file_id: int, user: dict = Depends(current_user)) -> dict:
    if not _can_view_file(user, file_id):
        raise HTTPException(404, "File not found.")
    row = db.one("SELECT sha256, created_at FROM files WHERE id = ?", (file_id,))
    return {"file_id": file_id, "sha256": row["sha256"], "uploaded_at": row["created_at"], "intact": storage.verify(file_id)}


# ---------------------------------------------------------------------------
# lease
# ---------------------------------------------------------------------------

@app.post("/api/leases")
async def upload_lease(file: UploadFile = File(...), user: dict = Depends(current_user)) -> dict:
    data = await _read_upload(file)
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Please upload the lease as a PDF.")
    fid = storage.save(user["id"], "lease", file.filename or "lease.pdf", "application/pdf", data)
    lid = db.insert("leases", user_id=user["id"], title=file.filename, file_id=fid, kind="lease",
                    signed_on=clock.today(user).isoformat(), created_at=clock.stamp(user["id"]))
    return {"lease_id": lid, **start(user, "lease", "Lease analysis", lambda rid: cases.analyse_lease(user, lid, rid), f"lease:{lid}")}


@app.post("/api/leases/{lease_id}/analyze")
def reanalyze(lease_id: int, user: dict = Depends(current_user)) -> dict:
    row = _need(db.one("SELECT * FROM leases WHERE id = ?", (lease_id,)), "Lease")
    if row["user_id"] != user["id"]:
        if not row.get("sublet_id"):
            raise HTTPException(404, "Lease not found.")
        _sublet_for(user, row["sublet_id"])
    return start(user, "lease", "Lease analysis", lambda rid: cases.analyse_lease(user, lease_id, rid), f"lease:{lease_id}")


@app.get("/api/leases/current")
def current_lease(kind: str = "", user: dict = Depends(current_user)) -> dict:
    """kind='' -> the contract that governs this user (sublease for a subtenant); kind='sublease' -> the
    sublease of the sublessor's sublet."""
    if kind == "sublease":
        s = db.one("SELECT * FROM sublets WHERE (owner_id = ? OR subtenant_id = ?) ORDER BY id DESC LIMIT 1", (user["id"], user["id"]))
        lease = cases.sublease_for(s["id"]) if s and cases.sublet_visible(s, user) else None
        if lease and not clock.visible(lease.get("signed_on"), user):
            lease = None
    else:
        lease = cases.lease_for_user(user)
    if lease:
        lease["analysis_meta"].pop("pages_masked", None)
        lease["analysis_meta"].pop("pii_map_file", None)
    return {"lease": lease}


@app.post("/api/lease/ask")
def lease_ask(body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    q = (body.get("question") or "").strip()[:500]
    if not q:
        raise HTTPException(400, "Ask a question.")
    return start(user, "lease_question", f"Lease Q: {q[:40]}", lambda rid: cases.lease_question(user, q, rid))


@app.get("/api/calendar")
def get_calendar(user: dict = Depends(current_user)) -> dict:
    return {"today": cases.user_today(user).isoformat(), "tasks": cases.calendar(user)}


@app.post("/api/tasks/{key}/toggle")
def toggle_task(key: str, user: dict = Depends(current_user)) -> dict:
    if db.one("SELECT 1 AS x FROM tasks_done WHERE user_id = ? AND task_key = ?", (user["id"], key)):
        db.ex("DELETE FROM tasks_done WHERE user_id = ? AND task_key = ?", (user["id"], key))
        return {"done": False}
    db.ex("INSERT INTO tasks_done (user_id, task_key, done_at) VALUES (?, ?, ?)", (user["id"], key, db.now()))
    return {"done": True}


# ---------------------------------------------------------------------------
# inspections and evidence
# ---------------------------------------------------------------------------

KINDS = ("move_in", "move_out", "sublet_handoff", "sublet_return")


def _inspection_public(insp: dict) -> dict:
    insp = dict(insp)
    insp["result"] = db.loads(insp.get("result"), None)
    ev = cases.evidence_for(insp["id"])
    insp["evidence"] = [{"id": e["id"], "file_id": e["file_id"], "parent_file_id": e["parent_file_id"], "room": e["room"],
                         "label": e["label"], "t_seconds": e["t_seconds"], "mime": e["mime"], "sha256": e["sha256"],
                         "uploaded_at": e["uploaded_at"], "meta": e["file_meta"]} for e in ev]
    vids = db.q("SELECT DISTINCT parent_file_id AS id FROM evidence WHERE inspection_id = ? AND parent_file_id IS NOT NULL", (insp["id"],))
    insp["videos"] = [storage.file_public(db.one("SELECT * FROM files WHERE id = ?", (v["id"],))) for v in vids]
    return insp


@app.get("/api/inspections")
def list_inspections(user: dict = Depends(current_user)) -> list[dict]:
    rows = db.q("SELECT * FROM inspections WHERE user_id = ? OR sublet_id IN "
                "(SELECT id FROM sublets WHERE owner_id = ? OR subtenant_id = ?) ORDER BY inspected_on, id",
                (user["id"], user["id"], user["id"]))
    mode = user.get("mode") or "tenant"
    rows = [r for r in rows if clock.visible(r["inspected_on"], user)
            and (mode != "subtenant" or r["sublet_id"])            # a subtenant sees only the sublet's records
            and (mode != "tenant" or not r["sublet_id"])]          # a tenant not subletting sees only their own
    return [_inspection_public(r) for r in rows]


@app.post("/api/inspections")
def create_inspection(body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    kind = body.get("kind")
    if kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {KINDS}")
    sublet_id = body.get("sublet_id")
    if sublet_id:
        _sublet_for(user, int(sublet_id))
    lease = cases.lease_for(user["id"])
    iid = db.insert("inspections", user_id=user["id"], lease_id=lease and lease["id"], sublet_id=sublet_id, kind=kind,
                    title=(body.get("title") or kind.replace("_", " ").title())[:80],
                    inspected_on=body.get("inspected_on") or clock.today(user).isoformat(), created_at=clock.stamp(user["id"]))
    if sublet_id:
        col = "handoff_id" if kind == "sublet_handoff" else "return_id" if kind == "sublet_return" else None
        if col:
            db.ex(f"UPDATE sublets SET {col} = ? WHERE id = ?", (iid, sublet_id))
    return _inspection_public(db.one("SELECT * FROM inspections WHERE id = ?", (iid,)))


@app.get("/api/inspections/{inspection_id}")
def get_inspection(inspection_id: int, user: dict = Depends(current_user)) -> dict:
    return _inspection_public(_inspection_for(user, inspection_id))


@app.post("/api/inspections/{inspection_id}/media")
async def add_media(inspection_id: int, files: list[UploadFile] = File(...), room: str = Form("Living room"),
                    user: dict = Depends(current_user)) -> dict:
    insp = _inspection_for(user, inspection_id)
    room = room.strip()[:40] or "Room"
    added = []
    for f in files:
        data = await _read_upload(f)
        mime = (f.content_type or "").lower()
        name = f.filename or "upload"
        if mime.startswith("video/") or name.lower().endswith((".mp4", ".mov", ".m4v", ".webm")):
            try:
                frames, meta = privacy.video_keyframes(data)
            except ValueError as exc:
                raise HTTPException(400, str(exc))
            vid = storage.save(user["id"], "video", name, mime or "video/mp4", data, meta)
            if meta["faces_blurred"]:
                guard.log(user["id"], "faces_blurred", {"file": name, "count": meta["faces_blurred"]})
            for fr in frames:
                fid = storage.save(user["id"], "frame", f"{name} @ {fr.t_seconds}s", "image/jpeg", fr.jpeg,
                                   {"from_video": vid, "t_seconds": fr.t_seconds, "faces_blurred": fr.faces_blurred})
                eid = db.insert("evidence", inspection_id=insp["id"], file_id=fid, parent_file_id=vid, room=room,
                                label=f"{name} @ {fr.t_seconds}s", t_seconds=fr.t_seconds, created_at=clock.stamp(user["id"]))
                added.append(eid)
        elif mime.startswith("image/") or name.lower().endswith((".jpg", ".jpeg", ".png", ".heic", ".webp")):
            try:
                clean, meta = privacy.sanitize_image(data)
            except Exception:
                raise HTTPException(400, f"Could not read image {name}.")
            if meta["gps_removed"] or meta["exif_removed"]:
                guard.log(user["id"], "exif_removed", {"file": name, "gps": meta["gps_removed"]})
            if meta["faces_blurred"]:
                guard.log(user["id"], "faces_blurred", {"file": name, "count": meta["faces_blurred"]})
            fid = storage.save(user["id"], "photo", name, "image/jpeg", clean, meta)
            added.append(db.insert("evidence", inspection_id=insp["id"], file_id=fid, room=room, label=name,
                                   created_at=clock.stamp(user["id"])))
        else:
            raise HTTPException(400, f"{name}: upload photos or videos.")
    db.ex("UPDATE inspections SET status = 'draft' WHERE id = ?", (insp["id"],))
    return {"added": added, "inspection": _inspection_public(db.one("SELECT * FROM inspections WHERE id = ?", (insp["id"],)))}


@app.delete("/api/evidence/{evidence_id}")
def delete_evidence(evidence_id: int, user: dict = Depends(current_user)) -> dict:
    ev = _need(db.one("SELECT * FROM evidence WHERE id = ?", (evidence_id,)), "Evidence")
    insp = _inspection_for(user, ev["inspection_id"])
    if insp["status"] == "done":
        raise HTTPException(409, "This inspection is sealed; evidence cannot be removed.")
    db.ex("DELETE FROM evidence WHERE id = ?", (evidence_id,))
    return {"ok": True}


@app.post("/api/inspections/{inspection_id}/run")
def run_inspection(inspection_id: int, user: dict = Depends(current_user)) -> dict:
    insp = _inspection_for(user, inspection_id)
    ref = f"sublet:{insp['sublet_id']}" if insp["sublet_id"] else f"inspection:{inspection_id}"
    return start(user, "inspection", f"{insp['kind'].replace('_', ' ').title()} inspection",
                 lambda rid: cases.inspect(user, inspection_id, rid), ref)


@app.post("/api/inspections/{inspection_id}/review")
def review_finding(inspection_id: int, body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    """Human in the loop: the Detective's findings are a draft. The person who took the photos can mark a
    finding as 'not damage' (with a reason) or restore it. Dismissed findings stay on record but are left out
    of comparisons, deposit cases and escrow settlements."""
    insp = _inspection_for(user, inspection_id)
    res = db.loads(insp["result"], None)
    if not res:
        raise HTTPException(409, "Run the inspection first.")
    action, idx = body.get("action"), int(body.get("index", -1))
    res.setdefault("dismissed", [])
    if action == "dismiss":
        if not 0 <= idx < len(res["findings"]):
            raise HTTPException(400, "No such finding.")
        f = res["findings"].pop(idx)
        f["dismissed_by"], f["dismissed_on"] = user["name"], clock.today(user).isoformat()
        f["dismiss_reason"] = (body.get("reason") or "Not damage (reviewed by the user)")[:200]
        res["dismissed"].append(f)
    elif action == "restore":
        if not 0 <= idx < len(res["dismissed"]):
            raise HTTPException(400, "No such dismissed finding.")
        f = res["dismissed"].pop(idx)
        for k in ("dismissed_by", "dismissed_on", "dismiss_reason"):
            f.pop(k, None)
        res["findings"].append(f)
    else:
        raise HTTPException(400, "action must be dismiss or restore")
    db.ex("UPDATE inspections SET result = ? WHERE id = ?", (db.dumps(res), inspection_id))
    return _inspection_public(db.one("SELECT * FROM inspections WHERE id = ?", (inspection_id,)))


@app.post("/api/compare")
def run_compare(body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    a, b = int(body["earlier_id"]), int(body["later_id"])
    _inspection_for(user, a), _inspection_for(user, b)
    return start(user, "compare", "Before vs. after", lambda rid: cases.compare(user, a, b, rid), f"compare:{a}:{b}")


@app.get("/api/precheck")
def get_precheck(user: dict = Depends(current_user)) -> dict:
    base, later = cases.precheck_records(user)
    pc = cases.latest_precheck(user)
    evidence = []
    for iid in ((pc["earlier_id"], pc["later_id"]) if pc else ()):
        row = db.one("SELECT * FROM inspections WHERE id = ?", (iid,))
        if row:
            evidence += _inspection_public(row)["evidence"]
    return {"precheck": pc and {"id": pc["id"], "run_id": pc["run_id"], "created_on": pc["created_on"], **(pc["result"] or {})},
            "evidence": evidence,
            "suggested": {"earlier": base and {"id": base["id"], "kind": base["kind"], "inspected_on": base["inspected_on"]},
                          "later": later and {"id": later["id"], "kind": later["kind"], "inspected_on": later["inspected_on"]}}}


@app.post("/api/precheck")
def run_precheck(body: dict = Body(default={}), user: dict = Depends(current_user)) -> dict:
    base, later = cases.precheck_records(user)
    a = int(body.get("earlier_id") or (base or {}).get("id") or 0)
    b = int(body.get("later_id") or (later or {}).get("id") or 0)
    if not a or not b:
        raise HTTPException(409, "Need a move-in (or hand-off) record and a newer analysed record first.")
    _inspection_for(user, a), _inspection_for(user, b)
    return start(user, "precheck", "Move-out precheck", lambda rid: cases.precheck(user, a, b, rid), f"precheck:{a}:{b}")


@app.get("/api/shield")
def get_shield(user: dict = Depends(current_user)) -> dict:
    return cases.shield(user)


# ---------------------------------------------------------------------------
# deposit cases
# ---------------------------------------------------------------------------

@app.get("/api/disputes")
def list_disputes(user: dict = Depends(current_user)) -> list[dict]:
    rows = db.q("SELECT * FROM disputes WHERE user_id = ? ORDER BY id DESC", (user["id"],))
    out = []
    for r in rows:
        r["facts"], r["result"] = db.loads(r["facts"], {}), db.loads(r["result"], None)
        if clock.visible(r["facts"].get("statement_received_date") or r["created_at"], user):
            out.append(r)
    return out


@app.post("/api/disputes")
async def create_dispute(file: UploadFile = File(...), move_in_id: int = Form(...), move_out_id: int = Form(...),
                         termination_date: str = Form(""), forwarding_address_date: str = Form(""),
                         statement_received_date: str = Form(""), deposit: str = Form(""),
                         keys_returned_date: str = Form(""),
                         user: dict = Depends(current_user)) -> dict:
    _inspection_for(user, move_in_id), _inspection_for(user, move_out_id)
    data = await _read_upload(file)
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Upload the landlord's statement as a PDF.")
    fid = storage.save(user["id"], "deduction", file.filename or "statement.pdf", "application/pdf", data)
    lease = cases.lease_for(user["id"])
    facts = {"termination_date": termination_date or None, "forwarding_address_date": forwarding_address_date or None,
             "statement_received_date": statement_received_date or clock.today(user).isoformat(), "deposit": float(deposit) if deposit else None,
             "keys_returned_date": keys_returned_date or None}
    did = db.insert("disputes", user_id=user["id"], lease_id=lease and lease["id"], move_in_id=move_in_id,
                    move_out_id=move_out_id, deduction_file_id=fid, facts=db.dumps(facts), created_at=clock.stamp(user["id"]))
    return {"dispute_id": did, **start(user, "deposit_case", "Deposit court case",
                                       lambda rid: cases.deposit_case(user, did, rid), f"dispute:{did}")}


@app.post("/api/disputes/{dispute_id}/rerun")
def rerun_dispute(dispute_id: int, user: dict = Depends(current_user)) -> dict:
    _need(db.one("SELECT id FROM disputes WHERE id = ? AND user_id = ?", (dispute_id, user["id"])), "Case")
    return start(user, "deposit_case", "Deposit court case", lambda rid: cases.deposit_case(user, dispute_id, rid),
                 f"dispute:{dispute_id}")


# ---------------------------------------------------------------------------
# sublets + escrow (simulated payments, everything dated on the simulated day)
# ---------------------------------------------------------------------------

def _sublet_public(s: dict, user: dict) -> dict:
    s = dict(s)
    s["role"] = cases.sublet_role(s, user["id"])
    state = cases.sublet_state(s, user)
    s["status"] = state["status"]
    s["steps"] = state["steps"]
    s["settlement"] = state["settlement"]
    s["utilities"] = db.loads(s.get("utilities"), None)
    s["docs"] = db.loads(s.get("docs"), None) if clock.visible(s.get("docs_on"), user) else None
    s["ledger"] = cases.ledger_rows(s["id"], user)
    s["escrow_balance"] = cases.escrow_balance(s["id"], user)
    s["utility_shares"] = cases.utility_shares(s, user)
    sub = cases.sublease_for(s["id"])
    s["sublease"] = ({"id": sub["id"], "file_id": sub["file_id"], "signed_on": sub.get("signed_on"),
                      "analysed": bool(sub["card"]), "monthly_rent": (sub["card"] or {}).get("monthly_rent"),
                      "utilities": (sub["card"] or {}).get("utilities", [])}
                     if sub and clock.visible(sub.get("signed_on"), user) else None)
    names = cases._names(s)
    s["owner_name"], s["subtenant_name"] = names["[PERSON_1]"], (names["[PERSON_2]"] if s["subtenant_id"] else None)
    end = cases.parse_date(s["end_date"])
    s["return_deadline"] = law.return_deadline(end, None).isoformat() if end else None
    s["today"] = clock.today(user).isoformat()
    if s["role"] != "sublessor":
        s["invite_code"] = None
    return s


def _visible_sublet(user: dict, sublet_id: int) -> tuple[dict, str]:
    s, role = _sublet_for(user, sublet_id)
    if not cases.sublet_visible(s, user):
        raise HTTPException(404, "This sublet does not exist yet on your current date.")
    return s, role


@app.get("/api/sublets")
def list_sublets(user: dict = Depends(current_user)) -> list[dict]:
    rows = db.q("SELECT * FROM sublets WHERE owner_id = ? OR subtenant_id = ? ORDER BY id DESC", (user["id"], user["id"]))
    return [_sublet_public(r, user) for r in rows if cases.sublet_visible(r, user)]


@app.post("/api/sublets")
def create_sublet(body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    s, e = cases.parse_date(body.get("start_date")), cases.parse_date(body.get("end_date"))
    if not (s and e and e > s):
        raise HTTPException(400, "Enter valid start and end dates.")
    if s <= clock.today(user):
        raise HTTPException(400, "The sublet must start after today (your current date).")
    deposit, rent = float(body.get("deposit") or 0), float(body.get("monthly_rent") or 0)
    lease = cases.lease_for(user["id"])
    sid = db.insert("sublets", owner_id=user["id"], lease_id=lease and lease["id"],
                    invite_code=secrets.token_hex(3).upper(), start_date=s.isoformat(), end_date=e.isoformat(),
                    monthly_rent=rent, deposit=deposit, utilities=db.dumps(body.get("utilities") or {}),
                    status="open", listed_on=clock.today(user).isoformat(), created_at=clock.stamp(user["id"]))
    return _sublet_public(db.one("SELECT * FROM sublets WHERE id = ?", (sid,)), user)


@app.post("/api/sublets/join")
def join_sublet(body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    code = (body.get("code") or "").strip().upper()
    s = _need(db.one("SELECT * FROM sublets WHERE invite_code = ?", (code,)), "Invite code")
    if s["owner_id"] == user["id"]:
        raise HTTPException(400, "This is your own sublet.")
    if s["subtenant_id"] and s["subtenant_id"] != user["id"]:
        raise HTTPException(409, "This sublet already has a subtenant.")
    db.ex("UPDATE sublets SET subtenant_id = ?, status = 'matched', matched_on = ? WHERE id = ?",
          (user["id"], clock.today(user).isoformat(), s["id"]))
    db.ex("UPDATE users SET mode = 'subtenant' WHERE id = ?", (user["id"],))
    return _sublet_public(db.one("SELECT * FROM sublets WHERE id = ?", (s["id"],)), user)


@app.post("/api/sublets/{sublet_id}/docs")
def sublet_docs(sublet_id: int, user: dict = Depends(current_user)) -> dict:
    _visible_sublet(user, sublet_id)
    return start(user, "sublet_docs", "Sublet documents", lambda rid: cases.sublet_docs(user, sublet_id, rid), f"sublet:{sublet_id}")


@app.post("/api/sublets/{sublet_id}/sublease")
async def upload_sublease(sublet_id: int, file: UploadFile = File(...), user: dict = Depends(current_user)) -> dict:
    s, role = _visible_sublet(user, sublet_id)
    data = await _read_upload(file)
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Upload the signed sublease as a PDF.")
    fid = storage.save(user["id"], "sublease", file.filename or "sublease.pdf", "application/pdf", data)
    lid = db.insert("leases", user_id=user["id"], title=file.filename, file_id=fid, kind="sublease", sublet_id=sublet_id,
                    signed_on=clock.today(user).isoformat(), created_at=clock.stamp(user["id"]))
    return {"lease_id": lid, **start(user, "lease", "Sublease analysis", lambda rid: cases.analyse_lease(user, lid, rid),
                                     f"sublet:{sublet_id}")}


def _luhn(number: str) -> bool:
    digits = [int(d) for d in number][::-1]
    total = sum(d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(digits))
    return total % 10 == 0


def _mock_payment(body: dict) -> tuple[str, str]:
    """Validate a SIMULATED card or bank transfer. Nothing is charged; only the last 4 digits are kept."""
    method = body.get("method")
    if method == "card":
        num = re.sub(r"\D", "", body.get("card_number", ""))
        if not (13 <= len(num) <= 19 and _luhn(num)):
            raise HTTPException(400, "Card number is not valid (use the test card 4242 4242 4242 4242).")
        return "card", f"•••• {num[-4:]}"
    if method == "ach":
        routing = re.sub(r"\D", "", body.get("routing", ""))
        account = re.sub(r"\D", "", body.get("account", ""))
        if len(routing) != 9 or len(account) < 4:
            raise HTTPException(400, "Routing number must be 9 digits and account at least 4 digits.")
        return "ach", f"acct •••• {account[-4:]}"
    raise HTTPException(400, "Choose card or bank transfer.")


def _reload(sublet_id: int, user: dict) -> dict:
    return _sublet_public(db.one("SELECT * FROM sublets WHERE id = ?", (sublet_id,)), user)


@app.post("/api/sublets/{sublet_id}/pay-deposit")
def pay_deposit(sublet_id: int, body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    s, role = _visible_sublet(user, sublet_id)
    if role != "subtenant":
        raise HTTPException(403, "Only the subtenant pays the sublet deposit.")
    if any(r["kind"] == "deposit_in" for r in cases.ledger_rows(sublet_id)):
        raise HTTPException(409, "The deposit is already in escrow.")
    method, masked = _mock_payment(body)
    cases.ledger_add(sublet_id, "deposit_in", s["deposit"], "subtenant", "escrow", method, masked,
                     "Sublet deposit held by Rentrail escrow (simulated)", user_id=user["id"])
    cases.ledger_add(sublet_id, "notice", 0, "escrow", "subtenant", "email",
                     note="Escrow notice sent: amount held + institution (CT-47a-21-h4)", user_id=user["id"])
    return _reload(sublet_id, user)


@app.post("/api/sublets/{sublet_id}/pay-rent")
def pay_rent(sublet_id: int, body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    s, role = _visible_sublet(user, sublet_id)
    if role != "subtenant":
        raise HTTPException(403, "Only the subtenant pays rent.")
    today = clock.today(user)
    start_d, end_d = cases.parse_date(s["start_date"]), cases.parse_date(s["end_date"])
    month = today.strftime("%Y-%m")
    if any(r["kind"] == "rent" and r.get("ref") == f"rent:{month}" for r in cases.ledger_rows(sublet_id)):
        raise HTTPException(409, f"Rent for {month} is already paid.")
    if (start_d and today < start_d.replace(day=1) - timedelta(days=10)) or (end_d and today > end_d):
        raise HTTPException(409, "Rent can be paid from 10 days before the sublet month until the sublet ends.")
    method, masked = _mock_payment(body)
    sub = cases.sublease_for(sublet_id)
    rent = ((sub or {}).get("card") or {}).get("monthly_rent") or s["monthly_rent"]
    cases.ledger_add(sublet_id, "rent", rent, "subtenant", "sublessor", method, masked,
                     f"Sublet rent for {month} (simulated)", user_id=user["id"], ref=f"rent:{month}")
    return _reload(sublet_id, user)


@app.post("/api/sublets/{sublet_id}/pay-utility")
def pay_utility(sublet_id: int, body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    s, role = _visible_sublet(user, sublet_id)
    if role != "subtenant":
        raise HTTPException(403, "Only the subtenant pays a utility share.")
    share = next((x for x in cases.utility_shares(s, user) if x["bill_id"] == int(body.get("bill_id", 0))), None)
    if not share:
        raise HTTPException(404, "No such utility share on this date.")
    if share["paid_on"]:
        raise HTTPException(409, "Already paid.")
    method, masked = _mock_payment(body)
    cases.ledger_add(sublet_id, "utility", share["subtenant_share"], "subtenant", "sublessor", method, masked,
                     f"{share['service']} share {share['overlap_days']}/{share['period_days']} days ({share['period']})",
                     user_id=user["id"], ref=share["ref"])
    return _reload(sublet_id, user)


@app.post("/api/sublets/{sublet_id}/settle")
def settle_sublet(sublet_id: int, user: dict = Depends(current_user)) -> dict:
    s, role = _visible_sublet(user, sublet_id)
    if cases.escrow_balance(sublet_id, user) <= 0:
        raise HTTPException(409, "No deposit in escrow on this date.")
    end_d = cases.parse_date(s["end_date"])
    if end_d and clock.today(user) < end_d:
        raise HTTPException(409, "The sublet has not ended yet on your current date.")
    return start(user, "sublet_settle", "Escrow settlement", lambda rid: cases.sublet_settle(user, sublet_id, rid), f"sublet:{sublet_id}")


@app.post("/api/sublets/{sublet_id}/decision")
def sublet_decision(sublet_id: int, body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    s, role = _visible_sublet(user, sublet_id)
    st = cases.sublet_state(s, user)["settlement"]
    if not st:
        raise HTTPException(409, "No settlement proposed yet.")
    if st.get("status") == "released":
        raise HTTPException(409, "Already paid out.")
    if role not in st["accepted_by"]:
        st["accepted_by"].append(role)
        st.setdefault("accepted_on", {})[role] = clock.today(user).isoformat()
    db.ex("UPDATE sublets SET settlement = ? WHERE id = ?", (db.dumps(st), sublet_id))
    if {"sublessor", "subtenant"} <= set(st["accepted_by"]):
        cases.sublet_release(sublet_id, user["id"])
    return _reload(sublet_id, user)


@app.post("/api/sublets/{sublet_id}/appeal")
def sublet_appeal(sublet_id: int, body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    s, role = _visible_sublet(user, sublet_id)
    if role != "subtenant":
        raise HTTPException(403, "Only the subtenant appeals the escrow proposal.")
    reason = (body.get("reason") or "").strip()
    if len(reason) < 10:
        raise HTTPException(400, "Explain why you disagree (at least a sentence).")
    if not cases.sublet_state(s, user)["settlement"]:
        raise HTTPException(409, "No settlement proposed yet.")
    return start(user, "sublet_appeal", "Escrow appeal", lambda rid: cases.sublet_appeal(user, sublet_id, reason, rid),
                 f"sublet:{sublet_id}")


@app.post("/api/sublets/{sublet_id}/invoice")
async def sublet_invoice(sublet_id: int, amount: float = Form(...), note: str = Form(""),
                         file: UploadFile | None = File(None), user: dict = Depends(current_user)) -> dict:
    s, role = _visible_sublet(user, sublet_id)
    if role != "sublessor":
        raise HTTPException(403, "Only the sublessor uploads the repair invoice.")
    fid = None
    if file is not None:
        data = await _read_upload(file)
        fid = storage.save(user["id"], "invoice", file.filename or "invoice", file.content_type or "application/octet-stream", data)
    try:
        cases.sublet_invoice(sublet_id, amount, fid, note, user["id"])
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return _reload(sublet_id, user)


@app.post("/api/sublets/{sublet_id}/reset")
def sublet_reset(sublet_id: int, user: dict = Depends(current_user)) -> dict:
    """Demo helper: clear the escrow ledger and the settlement (back to 'matched')."""
    _visible_sublet(user, sublet_id)
    cases.sublet_reset(sublet_id)
    return _reload(sublet_id, user)


# ---------------------------------------------------------------------------
# bills and insurance
# ---------------------------------------------------------------------------

@app.get("/api/bills")
def list_bills(user: dict = Depends(current_user)) -> list[dict]:
    rows = db.q("SELECT b.*, f.name AS file_name FROM bills b JOIN files f ON f.id = b.file_id WHERE b.user_id = ? "
                "ORDER BY COALESCE(b.issued_on, b.created_at) DESC", (user["id"],))
    rows = [r for r in rows if clock.visible(r.get("issued_on") or r["created_at"], user)]
    for r in rows:
        r["result"] = db.loads(r["result"], None)
    return rows


@app.post("/api/bills")
async def upload_bill(file: UploadFile = File(...), kind: str = Form("bill"), user: dict = Depends(current_user)) -> dict:
    if kind not in ("bill", "policy"):
        raise HTTPException(400, "kind must be bill or policy")
    data = await _read_upload(file)
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Upload a PDF.")
    fid = storage.save(user["id"], kind, file.filename or f"{kind}.pdf", "application/pdf", data)
    lease = cases.lease_for(user["id"])
    bid = db.insert("bills", user_id=user["id"], lease_id=lease and lease["id"], file_id=fid, kind=kind,
                    issued_on=clock.today(user).isoformat(), created_at=clock.stamp(user["id"]))
    return {"bill_id": bid, **start(user, kind, "Insurance policy" if kind == "policy" else "Utility bill",
                                    lambda rid: cases.read_bill(user, bid, rid), f"bill:{bid}")}


@app.post("/api/bills/{bill_id}/read")
def reread_bill(bill_id: int, user: dict = Depends(current_user)) -> dict:
    b = _need(db.one("SELECT * FROM bills WHERE id = ? AND user_id = ?", (bill_id, user["id"])), "Bill")
    return start(user, b["kind"], "Insurance policy" if b["kind"] == "policy" else "Utility bill",
                 lambda rid: cases.read_bill(user, bill_id, rid), f"bill:{bill_id}")


# ---------------------------------------------------------------------------
# copilot chat
# ---------------------------------------------------------------------------

@app.get("/api/chat")
def chat_history(user: dict = Depends(current_user)) -> list[dict]:
    return db.q("SELECT role, content, run_id, created_at FROM chat WHERE user_id = ? ORDER BY id DESC LIMIT 40", (user["id"],))[::-1]


@app.post("/api/chat")
def chat(body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    msg = (body.get("message") or "").strip()[:1500]
    if not msg:
        raise HTTPException(400, "Type a message.")
    history = chat_history(user)
    db.insert("chat", user_id=user["id"], role="user", content=msg, created_at=clock.stamp(user["id"]))

    page = str(body.get("page") or "")[:20]

    def starter(kind: str, title: str, fn, ref: str | None = None) -> int:
        return start(user, kind, title, fn, ref)["run_id"]

    async def work(rid: int) -> dict:
        fresh = db.one("SELECT * FROM users WHERE id = ?", (user["id"],))
        out = await copilot.chat(fresh, msg, history, rid, starter, page)
        db.insert("chat", user_id=user["id"], role="assistant", content=db.dumps(out), run_id=rid, created_at=clock.stamp(user["id"]))
        return out
    return start(user, "chat", f"Copilot: {msg[:40]}", work)


# ---------------------------------------------------------------------------
# runs, tokens, safety
# ---------------------------------------------------------------------------

def _run_visible(user: dict, run: dict) -> bool:
    if run["user_id"] == user["id"]:
        return True
    ref = run.get("ref") or ""
    if ref.startswith("sublet:"):
        s = db.one("SELECT * FROM sublets WHERE id = ?", (int(ref.split(":")[1]),))
        return bool(s and cases.sublet_role(s, user["id"]))
    return False


@app.get("/api/runs")
def list_runs(user: dict = Depends(current_user)) -> list[dict]:
    rows = db.q("SELECT id, kind, title, status, started_at, finished_at, input_tokens, cached_tokens, output_tokens, "
                "cost_usd, error, ref FROM runs WHERE user_id = ? ORDER BY id DESC LIMIT 100", (user["id"],))
    return rows


@app.get("/api/runs/{run_id}")
def get_run(run_id: int, user: dict = Depends(current_user)) -> dict:
    run = _need(llm.run_summary(run_id), "Run")
    if not _run_visible(user, run):
        raise HTTPException(404, "Run not found.")
    run["result"] = db.loads(run.get("result"), None)
    return run


@app.get("/api/tokens")
def token_stats(user: dict = Depends(current_user)) -> dict:
    by_agent = db.q("SELECT c.agent, COUNT(*) AS calls, SUM(c.input_tokens) AS input_tokens, SUM(c.cached_tokens) AS cached_tokens, "
                    "SUM(c.output_tokens) AS output_tokens, SUM(c.cost_usd) AS cost_usd, AVG(c.ms) AS avg_ms "
                    "FROM agent_calls c JOIN runs r ON r.id = c.run_id WHERE r.user_id = ? AND c.status = 'done' "
                    "GROUP BY c.agent ORDER BY cost_usd DESC", (user["id"],))
    by_kind = db.q("SELECT kind, COUNT(*) AS runs, AVG(input_tokens) AS avg_input, AVG(cached_tokens) AS avg_cached, "
                   "AVG(output_tokens) AS avg_output, AVG(cost_usd) AS avg_cost, SUM(cost_usd) AS total_cost "
                   "FROM runs WHERE user_id = ? AND status = 'done' GROUP BY kind ORDER BY total_cost DESC", (user["id"],))
    total = db.one("SELECT COUNT(*) AS runs, COALESCE(SUM(input_tokens),0) AS input_tokens, COALESCE(SUM(cached_tokens),0) AS cached_tokens, "
                   "COALESCE(SUM(output_tokens),0) AS output_tokens, COALESCE(SUM(cost_usd),0) AS cost_usd FROM runs WHERE user_id = ?", (user["id"],))
    return {"by_agent": by_agent, "by_kind": by_kind, "total": total, "price": llm.PRICE, "model": config.MODEL_NAME,
            "limits": {"run": config.RUN_TOKEN_LIMIT, "daily": config.USER_DAILY_TOKEN_LIMIT},
            "tokens_today": guard.tokens_today(user["id"])}


@app.get("/api/safety")
def safety_events(user: dict = Depends(current_user)) -> list[dict]:
    rows = db.q("SELECT * FROM safety_events WHERE user_id = ? ORDER BY id DESC LIMIT 200", (user["id"],))
    for r in rows:
        r["detail"] = db.loads(r["detail"], r["detail"])
    return rows


@app.post("/api/safety/selftest")
def safety_selftest(user: dict = Depends(current_user)) -> dict:
    import selftest
    return selftest.run_all()


# ---------------------------------------------------------------------------
# community: reviews, Q&A, stories
# ---------------------------------------------------------------------------

def _clean_post_text(text: str) -> tuple[str, dict]:
    m = privacy.mask_text(text or "")
    keep = {k: v for k, v in m.counts.items() if k in ("EMAIL", "PHONE", "SSN", "ACCOUNT")}
    out = text or ""
    for ph, value in m.mapping.items():
        if ph.split("_")[0].strip("[") in keep:
            out = out.replace(value, "[hidden]")
    return out, keep


@app.get("/api/posts")
def list_posts(category: str | None = None, user: dict = Depends(current_user)) -> list[dict]:
    sql = ("SELECT p.*, u.name AS author, (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id) AS likes, "
           "(SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comments, "
           "EXISTS(SELECT 1 FROM likes l WHERE l.post_id = p.id AND l.user_id = ?) AS liked "
           "FROM posts p JOIN users u ON u.id = p.user_id")
    params: list[Any] = [user["id"]]
    if category:
        sql += " WHERE p.category = ?"
        params.append(category)
    rows = db.q(sql + " ORDER BY p.created_at DESC LIMIT 200", params)
    return [r for r in rows if clock.visible(r["created_at"], user)][:100]


@app.post("/api/posts")
def create_post(body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    cat = body.get("category")
    if cat not in ("review", "qa", "story"):
        raise HTTPException(400, "category must be review, qa or story")
    title, tc = _clean_post_text((body.get("title") or "").strip()[:120])
    text, bc = _clean_post_text((body.get("body") or "").strip()[:4000])
    if not title or not text:
        raise HTTPException(400, "Title and text are required.")
    if tc or bc:
        guard.log(user["id"], "pii_masked", {"where": "community post", "counts": {**tc, **bc}})
    rating = body.get("rating")
    pid = db.insert("posts", user_id=user["id"], category=cat, title=title, body=text,
                    building=(body.get("building") or "")[:80],
                    rating=int(rating) if cat == "review" and rating else None, created_at=clock.stamp(user["id"]))
    return {"id": pid, "masked": {**tc, **bc}}


@app.get("/api/posts/{post_id}")
def get_post(post_id: int, user: dict = Depends(current_user)) -> dict:
    p = _need(db.one("SELECT p.*, u.name AS author FROM posts p JOIN users u ON u.id = p.user_id WHERE p.id = ?", (post_id,)), "Post")
    p["comments"] = [c for c in db.q("SELECT c.*, u.name AS author FROM comments c LEFT JOIN users u ON u.id = c.user_id "
                                     "WHERE c.post_id = ? ORDER BY c.created_at, c.id", (post_id,))
                     if clock.visible(c["created_at"], user)]
    p["likes"] = db.one("SELECT COUNT(*) AS n FROM likes WHERE post_id = ?", (post_id,))["n"]
    return p


@app.post("/api/posts/{post_id}/comments")
def add_comment(post_id: int, body: dict = Body(...), user: dict = Depends(current_user)) -> dict:
    _need(db.one("SELECT id FROM posts WHERE id = ?", (post_id,)), "Post")
    text, _ = _clean_post_text((body.get("body") or "").strip()[:2000])
    if not text:
        raise HTTPException(400, "Write something.")
    db.insert("comments", post_id=post_id, user_id=user["id"], body=text, created_at=clock.stamp(user["id"]))
    return get_post(post_id, user)


@app.post("/api/posts/{post_id}/like")
def like_post(post_id: int, user: dict = Depends(current_user)) -> dict:
    if db.one("SELECT 1 AS x FROM likes WHERE post_id = ? AND user_id = ?", (post_id, user["id"])):
        db.ex("DELETE FROM likes WHERE post_id = ? AND user_id = ?", (post_id, user["id"]))
    else:
        db.ex("INSERT INTO likes (post_id, user_id) VALUES (?, ?)", (post_id, user["id"]))
    return {"likes": db.one("SELECT COUNT(*) AS n FROM likes WHERE post_id = ?", (post_id,))["n"]}


@app.post("/api/posts/{post_id}/ask-dan")
def ask_dan(post_id: int, user: dict = Depends(current_user)) -> dict:
    p = _need(db.one("SELECT * FROM posts WHERE id = ?", (post_id,)), "Post")
    if p["category"] != "qa":
        raise HTTPException(400, "Counsel Dan answers Q&A posts only.")

    async def work(rid: int) -> dict:
        cases.officer_step(rid, user["id"], "Screen the community question", {
            "instruction_like_lines": guard.instruction_hits(p["title"] + " " + p["body"])[:3],
            "verdict": "passed on as fenced, quoted text"})
        r = await llm.call(copilot.counsel_answer(), run_id=rid, user_id=user["id"], agent_name="counsel",
                           purpose="Community Q&A answer", caller="user", deps=copilot.Ctx(rid, user["id"]),
                           prompt=guard.fence("COMMUNITY QUESTION", f"{p['title']}\n\n{p['body']}")
                           + "\n\nAnswer briefly in the language of the question, for any Connecticut renter.\n\n" + law.as_prompt())
        out = r.output.model_dump(mode="json")
        body = out["answer"] + ("\n\nSources: " + ", ".join(out["sources"]) if out["sources"] else "")
        db.insert("comments", post_id=post_id, user_id=None, body=body, is_ai=1, created_at=clock.stamp(user["id"]))
        return out
    return start(user, "community", "Counsel Dan answers a Q&A post", work, f"post:{post_id}")


# ---------------------------------------------------------------------------
# the React app
# ---------------------------------------------------------------------------

if (config.STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (config.STATIC_DIR / path).resolve()
        if path and candidate.is_file() and config.STATIC_DIR in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(config.STATIC_DIR / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def no_build() -> JSONResponse:
        return JSONResponse({"message": "Rentrail API is running. The web app is not built yet (frontend/dist missing)."})
