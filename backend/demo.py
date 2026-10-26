"""Demo accounts and the demo story, so a first-time visitor sees a full tenancy at once.

Story (all fictional): Alex Kim, a Yale student, rents Unit 4B at "77 Bulldog Lane" from
Aug 1 2026 to Jul 31 2027 (lease signed Jul 10; the unit is clean at move-in, and Alex later gouges
the floor and chips a hallway wall), lists the place for the summer on Apr 15 2027, matches
with intern Jordan Rivera on Apr 28, signs a sublease on May 10 (,950/month, ,500 deposit in escrow
on May 20), hands off on Jun 1 (Alex's two defects are recorded there, so they are pre-existing for Jordan), gets it
back on Jul 28 with a new bedroom wall crack (Jordan's), moves out Jul 31, and on
Aug 24 receives a late deduction statement with a hidden prompt injection. See TIMELINE.

Two ways to seed
1. fixtures (sample_data/fixtures/): a snapshot of the demo database captured from REAL runs
   (real agent outputs and real token counts). Imported as-is into an empty database.
2. raw: if there are no fixtures, create the accounts and upload the sample documents and media
   without running any model; the visitor presses the Run buttons.

    python backend/demo.py export   # save the current demo database as fixtures
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import auth
import config
import db
import privacy
import storage

DEMO_PASSWORD = "rentrail-demo"
DEMO_USERS = {
    "alex": {"email": "alex@demo.rentrail", "name": "Alex Kim", "lang": "en", "demo_today": "2026-08-01", "mode": "tenant"},
    "jordan": {"email": "jordan@demo.rentrail", "name": "Jordan Rivera", "lang": "en", "demo_today": "2027-06-01", "mode": "subtenant"},
    "minji": {"email": "minji@demo.rentrail", "name": "Minji Park", "lang": "ko", "demo_today": "2026-09-01", "mode": "tenant"},
}
FIXTURES = config.SAMPLE_DIR / "fixtures"
MEDIA = config.SAMPLE_DIR / "media"
TABLES = ["users", "files", "leases", "inspections", "evidence", "disputes", "sublets", "ledger", "bills",
          "tasks_done", "runs", "agent_calls", "safety_events", "posts", "comments", "likes", "chat", "prechecks"]


def _uid(who: str) -> int | None:
    row = db.one("SELECT id FROM users WHERE email = ?", (DEMO_USERS[who]["email"],))
    return row["id"] if row else None


def ensure_seeded() -> None:
    if db.one("SELECT id FROM users WHERE email = ?", (DEMO_USERS["alex"]["email"],)):
        return
    if (FIXTURES / "demo_db.json").exists() and not db.one("SELECT id FROM users LIMIT 1"):
        import_fixtures()
    else:
        seed_raw()
    for u in DEMO_USERS.values():  # older fixtures have no mode column
        db.ex("UPDATE users SET mode = ? WHERE email = ? AND (mode IS NULL OR mode = 'tenant')", (u["mode"], u["email"]))


def reseed() -> None:
    db.reset_all()
    if config.FILES_DIR.exists():
        shutil.rmtree(config.FILES_DIR)
    db.conn()
    ensure_seeded()


# ---------------------------------------------------------------------------
# raw seed (no model calls). Every record carries the date it really happens in the story, so the
# time machine shows only what exists on the chosen day.
# ---------------------------------------------------------------------------

TIMELINE = {
    "lease_signed": "2026-07-10", "policy_issued": "2026-07-25", "move_in": "2026-08-01",
    "first_bills": ("2026-09-03", "2026-09-05"),
    "sublet_listed": "2027-04-15", "sublet_matched": "2027-04-28", "sublease_signed": "2027-05-10",
    "deposit_paid": "2027-05-20", "handoff": "2027-06-01", "june_bill": "2027-07-06", "sublet_return": "2027-07-28",
    "move_out": "2027-07-31", "statement": "2027-08-24",
}


def _at(day: str, hh: str = "10:00:00") -> str:
    return f"{day}T{hh}+00:00"


def _pdf(user_id: int, name: str, kind: str, day: str) -> int:
    return storage.save(user_id, kind, name, "application/pdf", (config.SAMPLE_DIR / name).read_bytes(), when=_at(day))


def _add_media(user_id: int, inspection_id: int, room: str, names: list[str], day: str) -> None:
    for name in names:
        path = MEDIA / name
        if not path.exists():
            continue
        data = path.read_bytes()
        if name.lower().endswith(".mp4"):
            frames, meta = privacy.video_keyframes(data)
            vid = storage.save(user_id, "video", name, "video/mp4", data, meta, when=_at(day))
            for fr in frames:
                fid = storage.save(user_id, "frame", f"{name} @ {fr.t_seconds}s", "image/jpeg", fr.jpeg,
                                   {"from_video": vid, "t_seconds": fr.t_seconds, "faces_blurred": fr.faces_blurred}, when=_at(day))
                db.insert("evidence", inspection_id=inspection_id, file_id=fid, parent_file_id=vid, room=room,
                          label=f"{name} @ {fr.t_seconds}s", t_seconds=fr.t_seconds, created_at=_at(day))
        else:
            clean, meta = privacy.sanitize_image(data)
            fid = storage.save(user_id, "photo", name, "image/jpeg", clean, meta, when=_at(day))
            db.insert("evidence", inspection_id=inspection_id, file_id=fid, room=room, label=name, created_at=_at(day))


def _inspection(user_id: int, lease_id: int | None, kind: str, title: str, on: str, sublet_id: int | None = None) -> int:
    return db.insert("inspections", user_id=user_id, lease_id=lease_id, sublet_id=sublet_id, kind=kind, title=title,
                     inspected_on=on, created_at=_at(on))


def seed_raw() -> None:
    import cases

    T = TIMELINE
    ids = {}
    for who, u in DEMO_USERS.items():
        ids[who] = auth.create_user(u["email"], u["name"], DEMO_PASSWORD, u["lang"], is_demo=True, mode=u["mode"])
        db.ex("UPDATE users SET demo_today = ? WHERE id = ?", (u["demo_today"], ids[who]))
    alex, jordan, minji = ids["alex"], ids["jordan"], ids["minji"]

    # Master lease (signed in July, starts Aug 1)
    lease_file = _pdf(alex, "sample_lease.pdf", "lease", T["lease_signed"])
    lease_id = db.insert("leases", user_id=alex, title="sample_lease.pdf", file_id=lease_file, kind="lease",
                         signed_on=T["lease_signed"], created_at=_at(T["lease_signed"]))

    # Move-in day: the unit is clean. (The floor/wall photos are the author's real photos with the defect
    # digitally removed - labelled EDITED - because Alex causes those two defects later in the story.)
    m_in = _inspection(alex, lease_id, "move_in", "Move-in walkthrough (clean)", T["move_in"])
    _add_media(alex, m_in, "Living room", ["EDITED_Proof_1-1_no_defect.jpg", "EDITED_Proof_1-2_no_defect.jpg"], T["move_in"])
    _add_media(alex, m_in, "Hallway", ["EDITED_Proof_2-1_no_defect.jpg", "EDITED_Proof_2-2_no_defect.jpg"], T["move_in"])
    _add_media(alex, m_in, "Bedroom", ["Before_Crack.mp4"], T["move_in"])

    # Bills arrive on their statement dates
    for name, kind, day in [("sample_policy.pdf", "policy", T["policy_issued"]),
                            ("sample_bill_conservice.pdf", "bill", T["first_bills"][0]),
                            ("sample_bill_electric.pdf", "bill", T["first_bills"][1]),
                            ("sample_bill_electric_jun2027.pdf", "bill", T["june_bill"])]:
        fid = _pdf(alex, name, kind, day)
        db.insert("bills", user_id=alex, lease_id=lease_id, file_id=fid, kind=kind, issued_on=day, created_at=_at(day))

    # Summer sublet: listed -> matched -> sublease signed -> deposit -> hand-off -> return
    sid = db.insert("sublets", owner_id=alex, subtenant_id=jordan, lease_id=lease_id, invite_code="DAN427",
                    start_date=T["handoff"], end_date=T["sublet_return"], monthly_rent=1950, deposit=1500,
                    utilities=db.dumps({"electricity": "subtenant"}), status="matched",
                    listed_on=T["sublet_listed"], matched_on=T["sublet_matched"], created_at=_at(T["sublet_listed"]))
    sub_file = _pdf(alex, "sample_sublease.pdf", "sublease", T["sublease_signed"])
    db.insert("leases", user_id=alex, title="sample_sublease.pdf", file_id=sub_file, kind="sublease", sublet_id=sid,
              signed_on=T["sublease_signed"], created_at=_at(T["sublease_signed"]))
    cases.ledger_add(sid, "deposit_in", 1500, "subtenant", "escrow", "card", "•••• 4242",
                     "Sublet deposit held by Rentrail escrow (simulated)", ts=_at(T["deposit_paid"]))
    cases.ledger_add(sid, "notice", 0, "escrow", "subtenant", "email", note="Escrow notice sent: amount held + institution (CT-47a-21-h4)",
                     ts=_at(T["deposit_paid"], "10:00:05"))
    cases.ledger_add(sid, "rent", 1950, "subtenant", "sublessor", "ach", "acct •••• 6789", "Sublet rent for 2027-06 (simulated)",
                     ts=_at("2027-06-01", "09:00:00"), ref="rent:2027-06")
    cases.ledger_add(sid, "rent", 1950, "subtenant", "sublessor", "ach", "acct •••• 6789", "Sublet rent for 2027-07 (simulated)",
                     ts=_at("2027-07-01", "09:00:00"), ref="rent:2027-07")
    # Hand-off: Alex's own damage (floor gouge, wall chip) is found and recorded HERE, before Jordan moves in,
    # so it is pre-existing for Jordan. The bedroom wall is still clean.
    h = _inspection(alex, lease_id, "sublet_handoff", "Sublet hand-off (Alex -> Jordan)", T["handoff"], sid)
    _add_media(alex, h, "Living room", ["Proof_1-1.jpg", "Proof_1-2.jpg"], T["handoff"])
    _add_media(alex, h, "Hallway", ["Proof_2-1.jpg", "Proof_2-2.jpg"], T["handoff"])
    _add_media(alex, h, "Bedroom", ["Before_Crack.mp4"], T["handoff"])
    # Return: the same two defects, plus a new bedroom wall crack made during the sublet.
    r = _inspection(alex, lease_id, "sublet_return", "Sublet return (Jordan -> Alex)", T["sublet_return"], sid)
    _add_media(alex, r, "Living room", ["Proof_1-1.jpg", "Proof_1-2.jpg"], T["sublet_return"])
    _add_media(alex, r, "Hallway", ["Proof_2-1.jpg", "Proof_2-2.jpg"], T["sublet_return"])
    _add_media(alex, r, "Bedroom", ["After_Crack.mp4"], T["sublet_return"])
    db.ex("UPDATE sublets SET handoff_id = ?, return_id = ? WHERE id = ?", (h, r, sid))

    # Move-out and the landlord's statement
    m_out = _inspection(alex, lease_id, "move_out", "Move-out walkthrough", T["move_out"])
    _add_media(alex, m_out, "Living room", ["Proof_1-1.jpg", "Proof_1-2.jpg"], T["move_out"])
    _add_media(alex, m_out, "Hallway", ["Proof_2-1.jpg", "Proof_2-2.jpg"], T["move_out"])
    _add_media(alex, m_out, "Bedroom", ["After_Crack.mp4"], T["move_out"])
    inj = _inspection(alex, lease_id, "move_out", "Safety test - wall with text addressed to AI", T["move_out"])
    _add_media(alex, inj, "Bedroom", ["Crack_-_AI_no_report.mp4"], T["move_out"])
    ded = _pdf(alex, "sample_deductions.pdf", "deduction", T["statement"])
    db.insert("disputes", user_id=alex, lease_id=lease_id, move_in_id=m_in, move_out_id=m_out, deduction_file_id=ded,
              facts=db.dumps({"termination_date": T["move_out"], "forwarding_address_date": T["move_out"],
                              "statement_received_date": T["statement"], "deposit": 4300, "keys_returned_date": T["move_out"]}),
              created_at=_at(T["statement"]))

    posts = [
        (minji, "story", "48시간 점검표, 저는 이렇게 했어요", "입주 첫날 짐도 못 풀었는데 계약서에 48시간 안에 하자를 적어 내라고 되어 있더라고요. "
         "방마다 영상을 한 바퀴 찍어서 올렸더니 바닥 패임이랑 벽 찍힘이 자동으로 정리됐어요.", "", None, "2026-08-20"),
        (minji, "review", "Management answers repair requests fast - but only in writing", "Requests by phone were ignored. "
         "Portal requests were fixed in 2 days. Keep the written record!", "Chapel St area (demo)", 4, "2026-11-02"),
        (jordan, "qa", "Do I get interest on my sublet deposit?", "I paid a $1,500 sublet deposit for two months. Is interest owed in Connecticut?",
         "", None, "2027-05-22"),
        (jordan, "review", "Summer sublet near campus - smooth hand-off", "Hand-off inspection took 10 minutes with both of us in the room. "
         "The deposit sat in escrow, so I did not have to trust a stranger with $1,500.", "77 Bulldog Lane (demo)", 5, "2027-08-05"),
        (alex, "qa", "Can my landlord charge carpet cleaning \"regardless of condition\" in CT?",
         "My lease says professional carpet cleaning regardless of condition. The carpet was fine when I left. Can they deduct it?",
         "", None, "2027-08-26"),
    ]
    for uid, cat, title, body, building, rating, day in posts:
        db.insert("posts", user_id=uid, category=cat, title=title, body=body, building=building, rating=rating, created_at=_at(day))


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def export_fixtures() -> Path:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    files_dir = FIXTURES / "files"
    if files_dir.exists():
        shutil.rmtree(files_dir)
    files_dir.mkdir()
    dump = {t: db.q(f"SELECT * FROM {t}") for t in TABLES}
    for row in dump["files"]:
        _, data = storage.load(row["id"])
        (files_dir / f"{row['id']}.bin").write_bytes(data)
        row["path"] = None
    (FIXTURES / "demo_db.json").write_text(json.dumps(dump, ensure_ascii=False, indent=0, default=str), encoding="utf-8")
    return FIXTURES


def import_fixtures() -> None:
    dump = json.loads((FIXTURES / "demo_db.json").read_text(encoding="utf-8"))
    config.FILES_DIR.mkdir(parents=True, exist_ok=True)
    import secrets
    from storage import _fernet
    f = _fernet()
    for row in dump["files"]:
        name = f"{secrets.token_hex(12)}.bin"
        data = (FIXTURES / "files" / f"{row['id']}.bin").read_bytes()
        (config.FILES_DIR / name).write_bytes(f.encrypt(data))
        row["path"] = name
    with db.tx() as c:
        for t in TABLES:
            for row in dump.get(t, []):
                cols = ", ".join(row)
                c.execute(f"INSERT INTO {t} ({cols}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        print("exported to", export_fixtures())
    elif len(sys.argv) > 1 and sys.argv[1] == "reseed":
        reseed()
        print("reseeded")
    else:
        ensure_seeded()
        print("seeded")
