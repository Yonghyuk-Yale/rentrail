"""The workflows. Each one is a *run*: code prepares safe inputs, agents do the judgement,
code does every date and dollar calculation, and everything is recorded for the Agent Room.

Pipelines
- analyse_lease:   Checkpoint (visible text, masking) -> Clerk (Lease Card)
- inspect:         Checkpoint (EXIF/faces/keyframes at upload) -> Detective (findings) -> Checkpoint (text-in-image check)
- compare:         Detective (earlier vs later)
- deposit_case:    Checkpoint (deduction PDF) -> Detective compare -> Counsel (brief) -> Chief Justice (ruling + letter)
- sublet_docs:     Sheriff (consent letter, sublease draft, duties)
- sublet_settle:   Detective compare -> Sheriff (claim) -> Chief Justice (ruling) -> code splits the escrow
- bill / policy:   Checkpoint (visible text, masking) -> Treasurer
- precheck:        Checkpoint -> Detective compare -> Counsel (repair category, DIY?) -> code prices it
- shield:          code only: how well the deposit is protected today
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic_ai import BinaryContent

import agents
import clock
import db
import guard
import law
import privacy
import storage
from agents import Ctx
from llm import call

MAX_IMAGES_PER_CALL = 12
CONFIDENCE_MIN = 0.75  # findings below this are shown as "possible" only (eval: true defects >= 0.83, false alarms 0.51-0.68)
LEASE_CHAR_BUDGET = 60_000

LEASE_PRIORITY = {
    "within 48 hours": 30, "inventory and condition": 12, "move-out notice": 12, "days' advance written": 12,
    "written notice": 4, "sublet": 8, "assignment": 3, "reletting": 6, "automatically renew": 10, "renew": 3,
    "security deposit": 4, "deduct": 4, "forwarding address": 6, "insurance": 3, "liability": 2,
    "utilit": 3, "conservice": 4, "rekey": 4, "buy-out": 4, "late charge": 4, "carpet": 3,
}
LEASE_KEYWORDS = [
    "security deposit", "deposit", "deduct", "move-out", "move out", "notice", "inventory", "condition",
    "sublet", "assign", "replacement", "renew", "terminat", "buy-out", "buyout", "reletting", "utilit",
    "insurance", "repair", "key", "late", "rent", "lease term", "begins", "ends", "carpet", "clean",
    "wear", "damage", "forwarding", "pet", "animal",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{2})", value.strip())
    if m:  # "2026-12" -> last day of that month
        y, mo = int(m.group(1)), int(m.group(2))
        nxt = date(y + (mo == 12), mo % 12 + 1, 1)
        return nxt - timedelta(days=1)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def user_today(user: dict) -> date:
    return clock.today(user)


def officer_step(run_id: int | None, user_id: int, purpose: str, detail: dict) -> None:
    """Record the Checkpoint as the first step of a run (plain code, 0 tokens), so every trace shows
    that untrusted input was screened before any AI agent - including the Boss - read it."""
    if not run_id:
        return
    seq = db.one("SELECT COALESCE(MAX(seq), 0) + 1 AS s FROM agent_calls WHERE run_id = ?", (run_id,))["s"]
    db.insert("agent_calls", run_id=run_id, seq=seq, agent="officer", caller="user", purpose=purpose,
              input_preview="(untrusted input from the user or a third party)", output=db.dumps(detail),
              status="done", ms=0, created_at=db.now())


def _pii_map_save(user_id: int, mapping: dict, label: str) -> int | None:
    if not mapping:
        return None
    return storage.save(user_id, "pii_map", label, "application/json", db.dumps(mapping).encode())


def pii_map_load(file_id: int | None, user_id: int) -> dict:
    if not file_id:
        return {}
    try:
        _, data = storage.load(file_id, user_id)
        return db.loads(data.decode(), {})
    except FileNotFoundError:
        return {}


def lease_for(user_id: int, lease_id: int | None = None) -> dict | None:
    """The user's own master lease (not a sublease they created as sublessor)."""
    if lease_id:
        row = db.one("SELECT * FROM leases WHERE id = ? AND user_id = ?", (lease_id, user_id))
    else:
        row = db.one("SELECT * FROM leases WHERE user_id = ? AND COALESCE(kind, 'lease') = 'lease' "
                     "ORDER BY id DESC LIMIT 1", (user_id,))
    if row:
        row["card"] = db.loads(row["card"], None)
        row["analysis_meta"] = db.loads(row["analysis_meta"], {})
    return row


def lease_for_user(user: dict) -> dict | None:
    """The contract that governs this user today: a subtenant's sublease, otherwise the master lease."""
    if (user.get("mode") or "tenant") == "subtenant":
        s = db.one("SELECT * FROM sublets WHERE subtenant_id = ? ORDER BY id DESC LIMIT 1", (user["id"],))
        sub = sublease_for(s["id"]) if s else None
        return sub if sub and clock.visible(sub.get("signed_on"), user) else None
    return lease_for(user["id"])


def _card_brief(card: dict | None) -> str:
    if not card:
        return "No Lease Card yet."
    keep = {k: card.get(k) for k in (
        "lease_start", "lease_end", "monthly_rent", "security_deposit", "inventory_form_hours",
        "move_out_notice_days", "auto_renews", "sublet_requires_consent", "sublet_terms_en",
        "insurance_required", "insurance_min_liability", "repair_request_method", "utilities")}
    clauses = [f"- {c['key']} (p.{c.get('page')}): {c['plain_en']} Quote: \"{c.get('quote', '')[:160]}\""
               for c in card.get("clauses", [])]
    return "LEASE CARD\n" + db.dumps(keep) + "\nCLAUSES\n" + "\n".join(clauses)


# ---------------------------------------------------------------------------
# Lease
# ---------------------------------------------------------------------------

def _select_pages(pages: list[str], budget: int | None = None) -> list[int]:
    budget = budget or LEASE_CHAR_BUDGET  # read at call time so experiments can change it
    total = sum(len(p) for p in pages)
    if total <= budget:
        return list(range(len(pages)))
    scored = []
    for i, text in enumerate(pages):
        low = " ".join(text.lower().split())  # PDFs break phrases across lines ("within 48 / hours")
        # v2: phrases that carry a deadline or a money rule weigh more than generic words, so the
        # page with the actual 48-hour form rule beats a page that merely says "deposit" ten times.
        score = sum(w * low.count(k) for k, w in LEASE_PRIORITY.items()) + sum(low.count(k) for k in LEASE_KEYWORDS) / 10
        scored.append((score, i))
    chosen = {0, 1} & set(range(len(pages)))
    used = sum(len(pages[i]) for i in chosen)

    def take(i: int) -> None:
        nonlocal used
        if i not in chosen and used + len(pages[i]) <= budget:
            chosen.add(i)
            used += len(pages[i])

    # v3 (1) coverage: every deadline/money rule phrase gets the page where it appears most.
    flat = [" ".join(p.lower().split()) for p in pages]
    for phrase, weight in sorted(LEASE_PRIORITY.items(), key=lambda kv: -kv[1]):
        if weight >= 8:
            counts = [(f.count(phrase), i) for i, f in enumerate(flat)]
            best = max(counts)
            if best[0]:
                take(best[1])
    # v3 (2) density: then the pages with the most rule text per character (long boilerplate pages lose).
    for score, i in sorted(((s / max(len(pages[i]), 500), i) for s, i in scored), reverse=True):
        if score > 0:
            take(i)
    return sorted(chosen)


def prepare_document(user: dict, file_id: int, run_id: int | None, label: str,
                     extra_names: list[str] = ()) -> dict:
    """The Checkpoint: visible text only, injection scan, personal data masked."""
    row, data = storage.load(file_id, user["id"])
    pdf = guard.read_pdf(data)
    full = "\n".join(pdf.pages)
    names = [user["name"], *privacy.guess_names(full), *extra_names]
    joined = "\n".join(f"=== PAGE {i + 1} ===\n{t}" for i, t in enumerate(pdf.pages))
    masked = privacy.mask_text(joined, names)
    masked_pages = re.split(r"=== PAGE \d+ ===\n", masked.text)[1:]
    visible_hits = guard.instruction_hits(full)
    hidden_hits = [h for h in pdf.hidden]
    if hidden_hits:
        guard.log(user["id"], "hidden_text_removed", {"document": label, "file_id": file_id, "removed": hidden_hits[:5]}, run_id)
    if visible_hits:
        guard.log(user["id"], "instruction_text_flagged", {"document": label, "file_id": file_id, "lines": visible_hits[:5]}, run_id)
    if masked.counts:
        guard.log(user["id"], "pii_masked", {"document": label, "counts": masked.counts}, run_id)
    officer_step(run_id, user["id"], f"Screen {label} PDF", {
        "pages": len(pdf.pages), "hidden_text_removed": hidden_hits[:3], "instruction_lines_flagged": visible_hits[:3],
        "personal_data_masked": masked.counts, "verdict": "passed on as fenced, masked evidence"})
    return {"pages": masked_pages, "raw_pages": pdf.pages, "mapping": masked.mapping, "counts": masked.counts,
            "hidden": hidden_hits, "instruction_hits": visible_hits, "page_count": len(pdf.pages)}


async def analyse_lease(user: dict, lease_id: int, run_id: int) -> dict:
    lease = db.one("SELECT * FROM leases WHERE id = ? AND user_id = ?", (lease_id, user["id"]))
    doc = prepare_document(user, lease["file_id"], run_id, "lease")
    chosen = _select_pages(doc["pages"])
    text = "\n".join(f"=== PAGE {i + 1} ===\n{doc['pages'][i]}" for i in chosen)
    kind = lease.get("kind") or "lease"
    prompt = (f"The {'SUBLEASE (between a sublessor and a subtenant)' if kind == 'sublease' else 'lease'} has "
              f"{doc['page_count']} pages. You are given pages {[i + 1 for i in chosen]} "
              "(selected by Rentrail because they contain lease terms). Fill the Lease Card"
              + (" from the sublessor-subtenant terms (the 'tenant' is the subtenant)" if kind == "sublease" else "")
              + ".\n\n"
              + guard.fence("LEASE", text))
    ctx = Ctx(run_id=run_id, user_id=user["id"], page_count=doc["page_count"])
    result = await call(agents.clerk_card(), run_id=run_id, user_id=user["id"], agent_name="clerk",
                        purpose="Lease Card", prompt=prompt, caller="chief_justice", deps=ctx)
    card = result.output.model_dump(mode="json")
    pii_id = _pii_map_save(user["id"], doc["mapping"], f"lease {lease_id} pii map")
    meta = {"page_count": doc["page_count"], "pages_sent": [i + 1 for i in chosen],
            "chars_total": sum(len(p) for p in doc["pages"]), "chars_sent": len(text),
            "masked": doc["counts"], "hidden_removed": len(doc["hidden"]),
            "instruction_hits": doc["instruction_hits"][:5], "pii_map_file": pii_id,
            "pages_masked": doc["pages"]}
    db.ex("UPDATE leases SET card = ?, analysis_meta = ?, page_count = ?, run_id = ? WHERE id = ?",
          (db.dumps(card), db.dumps(meta), doc["page_count"], run_id, lease_id))
    return card


def _top_pages(pages: list[str], question: str, k: int = 4) -> list[int]:
    words = [w for w in re.findall(r"[a-z]{4,}", question.lower())]
    scored = sorted(((sum(p.lower().count(w) for w in words), i) for i, p in enumerate(pages)), reverse=True)
    return sorted(i for s, i in scored[:k] if s > 0) or list(range(min(k, len(pages))))


async def lease_question(user: dict, question: str, run_id: int, caller: str = "user") -> dict:
    lease = lease_for_user(user)
    if not lease or not lease["card"]:
        return {"answer_en": "No analysed lease yet.", "answer_ko": "아직 분석된 계약서가 없습니다.", "pages": [],
                "quotes": [], "not_in_lease": True}
    pages = lease["analysis_meta"].get("pages_masked") or []
    top = _top_pages(pages, question)
    text = "\n".join(f"=== PAGE {i + 1} ===\n{pages[i]}" for i in top)
    prompt = (f"Question from the tenant: {question}\n\n{_card_brief(lease['card'])}\n\n" + guard.fence("LEASE PAGES", text))
    ctx = Ctx(run_id=run_id, user_id=user["id"], page_count=lease["page_count"] or len(pages))
    result = await call(agents.clerk_answer(), run_id=run_id, user_id=user["id"], agent_name="clerk",
                        purpose="Lease question", prompt=prompt, caller=caller, deps=ctx)
    return result.output.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Inspections
# ---------------------------------------------------------------------------

def evidence_for(inspection_id: int) -> list[dict]:
    rows = db.q("SELECT e.*, f.mime, f.sha256, f.kind AS file_kind, f.meta AS file_meta, f.created_at AS uploaded_at "
                "FROM evidence e JOIN files f ON f.id = e.file_id WHERE e.inspection_id = ? ORDER BY e.id", (inspection_id,))
    for r in rows:
        r["file_meta"] = db.loads(r["file_meta"], {})
    return rows


def _image_parts(user_id: int, evidence: list[dict], limit: int = MAX_IMAGES_PER_CALL, header: str = "") -> list[Any]:
    parts: list[Any] = []
    for ev in evidence[:limit]:
        _, data = storage.load(ev["file_id"])
        where = f" — video {ev['t_seconds']}s" if ev.get("t_seconds") is not None else ""
        parts.append(f"{header}Evidence #{ev['id']} — room: {ev.get('room') or 'unknown'}{where}")
        parts.append(BinaryContent(data=privacy.model_view(data), media_type="image/jpeg", identifier=f"ev{ev['id']}"))
    return parts


async def inspect(user: dict, inspection_id: int, run_id: int) -> dict:
    insp = db.one("SELECT * FROM inspections WHERE id = ?", (inspection_id,))
    evidence = [e for e in evidence_for(inspection_id) if e["mime"].startswith("image/")]
    if not evidence:
        raise ValueError("Add at least one photo or video first.")
    kind_label = {"move_in": "MOVE-IN", "move_out": "MOVE-OUT", "sublet_handoff": "SUBLET HAND-OFF",
                  "sublet_return": "SUBLET RETURN"}.get(insp["kind"], insp["kind"])
    used = evidence[:MAX_IMAGES_PER_CALL]
    officer_step(run_id, user["id"], "Screen photos and video frames", {
        "images": len(used), "gps_exif_removed_at_upload": sum(1 for e in used if (e.get("file_meta") or {}).get("gps_removed")),
        "faces_blurred": sum(int((e.get("file_meta") or {}).get("faces_blurred") or 0) for e in used),
        "rule": "text inside images is evidence, never instructions"})
    prompt: list[Any] = [f"{kind_label} inspection on {insp['inspected_on']}. {len(used)} images follow "
                         f"({len(evidence)} available; Rentrail sends at most {MAX_IMAGES_PER_CALL}). Inspection mode."]
    prompt += _image_parts(user["id"], used)
    ctx = Ctx(run_id=run_id, user_id=user["id"], evidence_ids={e["id"] for e in used})
    result = await call(agents.detective_inspect(), run_id=run_id, user_id=user["id"], agent_name="detective",
                        purpose=f"{kind_label} inspection", prompt=prompt, caller="chief_justice", deps=ctx)
    report = result.output.model_dump(mode="json")
    # Round 2: low-confidence findings are kept as "possible" for the user to confirm, but they do not
    # enter comparisons or deposit cases.
    report["possible"] = [f for f in report["findings"] if f["confidence"] < CONFIDENCE_MIN]
    report["findings"] = [f for f in report["findings"] if f["confidence"] >= CONFIDENCE_MIN]
    flagged = []
    for t in report["seen_text"]:
        hits = guard.instruction_hits(t["text"])
        if t["looks_like_instruction"] or hits:
            t["blocked"] = True
            flagged.append(t)
    if flagged:
        guard.log(user["id"], "instruction_in_image", {"inspection_id": inspection_id, "texts": flagged,
                                                       "findings_kept": len(report["findings"])}, run_id)
    report["injection_blocked"] = bool(flagged)
    db.ex("UPDATE inspections SET result = ?, status = 'done', run_id = ? WHERE id = ?",
          (db.dumps(report), run_id, inspection_id))
    return report


async def compare(user: dict, earlier_id: int, later_id: int, run_id: int) -> dict:
    earlier = db.one("SELECT * FROM inspections WHERE id = ?", (earlier_id,))
    later = db.one("SELECT * FROM inspections WHERE id = ?", (later_id,))
    e_find = (db.loads(earlier["result"], {}) or {}).get("findings", [])
    l_find = (db.loads(later["result"], {}) or {}).get("findings", [])
    if not l_find:
        return {"items": [], "summary_en": "No damage was found in the later inspection.",
                "summary_ko": "나중 점검에서 하자가 발견되지 않았습니다.", "earlier": e_find, "later": l_find}
    e_ev = [e for e in evidence_for(earlier_id) if e["mime"].startswith("image/")]
    l_ev = [e for e in evidence_for(later_id) if e["mime"].startswith("image/")]
    l_ids = {f["evidence_id"] for f in l_find}
    later_imgs = [e for e in l_ev if e["id"] in l_ids][:5]
    # Round 3: pair each later image with the earlier image of the same spot. Walkthrough videos follow
    # the same route, so the same room + the closest timestamp (or the same photo name) is the best match.
    def counterpart(later_ev: dict) -> dict | None:
        same_room = [e for e in e_ev if e.get("room") == later_ev.get("room")]
        if not same_room:
            return None
        if later_ev.get("t_seconds") is not None:
            timed = [e for e in same_room if e.get("t_seconds") is not None]
            if timed:
                return min(timed, key=lambda e: abs(e["t_seconds"] - later_ev["t_seconds"]))
        return next((e for e in same_room if e.get("label") == later_ev.get("label")), same_room[0])

    earlier_imgs = [c for c in (counterpart(e) for e in later_imgs) if c]
    earlier_imgs += [e for e in e_ev if e["id"] in {f["evidence_id"] for f in e_find}]
    seen, earlier_pick = set(), []
    for e in earlier_imgs:
        if e["id"] not in seen:
            seen.add(e["id"])
            earlier_pick.append(e)
    earlier_pick = earlier_pick[:6]
    prompt: list[Any] = [
        f"Comparison mode. EARLIER record: {earlier['kind']} on {earlier['inspected_on']}. "
        f"LATER record: {later['kind']} on {later['inspected_on']}.",
        "EARLIER findings (index: finding):\n" + "\n".join(
            f"{i}: [{f['room']}] {f['item']} — {f['damage_type']} at {f['location']} (evidence #{f['evidence_id']})"
            for i, f in enumerate(e_find)) if e_find else "EARLIER findings: none recorded (the unit was recorded as clean).",
        "LATER findings (index: finding):\n" + "\n".join(
            f"{i}: [{f['room']}] {f['item']} — {f['damage_type']} at {f['location']} (evidence #{f['evidence_id']})"
            for i, f in enumerate(l_find)),
    ]
    prompt += _image_parts(user["id"], earlier_pick, header="EARLIER ")
    prompt += _image_parts(user["id"], later_imgs, header="LATER ")
    ctx = Ctx(run_id=run_id, user_id=user["id"], extra={"n_later": len(l_find), "n_earlier": len(e_find),
                                                         "earlier_ids": {e["id"] for e in earlier_pick}})
    result = await call(agents.detective_compare(), run_id=run_id, user_id=user["id"], agent_name="detective",
                        purpose="Before vs. after comparison", prompt=prompt, caller="chief_justice", deps=ctx)
    comp = result.output.model_dump(mode="json")
    by_id = {e["id"]: e for e in l_ev}
    for it in comp["items"]:
        it["later"] = l_find[it["move_out_index"]]
        mi = it.get("matched_move_in_index")
        it["earlier"] = e_find[mi] if mi is not None and 0 <= mi < len(e_find) else None
        if not it.get("earlier_evidence_id"):  # fall back to the same-room, closest-timestamp frame
            twin = counterpart(by_id.get(it["later"]["evidence_id"], {"room": it["later"]["room"]}))
            it["earlier_evidence_id"] = twin["id"] if twin else None
    comp["earlier_id"], comp["later_id"] = earlier_id, later_id
    return comp


# ---------------------------------------------------------------------------
# Deposit case
# ---------------------------------------------------------------------------

_MONEY_LINE = re.compile(r"^\s*(?:\d+[.)]\s*)?(?P<item>[A-Za-z][^$\n]{2,90}?)[\s.:–-]*\$\s?(?P<amt>\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*$", re.M)
_SKIP = re.compile(r"total|deposit (?:held|paid|amount|received)|balance|refund|interest", re.I)


def parse_deductions(text: str) -> list[dict]:
    items = []
    for m in _MONEY_LINE.finditer(text):
        label = " ".join(m.group("item").split()).strip(" .:-")
        if _SKIP.search(label):
            continue
        items.append({"item": label, "amount": float(m.group("amt").replace(",", ""))})
    return items


def deposit_facts(user: dict, dispute: dict, lease: dict | None) -> dict:
    facts = db.loads(dispute["facts"], {})
    card = (lease or {}).get("card") or {}
    deposit = float(facts.get("deposit") or card.get("security_deposit") or 0)
    term = parse_date(facts.get("termination_date") or card.get("lease_end"))
    fwd = parse_date(facts.get("forwarding_address_date"))
    received = parse_date(facts.get("statement_received_date"))
    start = parse_date(card.get("lease_start"))
    out: dict[str, Any] = {"deposit": deposit, "termination_date": term and term.isoformat(),
                           "forwarding_address_date": fwd and fwd.isoformat(),
                           "statement_received_date": received and received.isoformat(),
                           "keys_returned_date": facts.get("keys_returned_date")}
    if term:
        deadline = law.return_deadline(term, fwd)
        out["return_deadline"] = deadline.isoformat()
        out["forwarding_address_given"] = fwd is not None
        if received:
            out["statement_late"] = received > deadline
            out["days_late"] = max(0, (received - deadline).days)
        out["interest"] = law.deposit_interest(deposit, start, term) if start else 0.0
        out["double_damages"] = round(deposit * law.pack()["deposit_rules"]["late_penalty_multiplier"], 2)
    if start and card.get("monthly_rent"):
        cap = law.pack()["deposit_rules"]["max_months_under_62"] * float(card["monthly_rent"])
        out["deposit_cap"] = cap
        out["deposit_above_cap"] = deposit > cap + 0.01
    return out


def _benchmarks_text() -> str:
    """Rentrail's repair price table as a reference for what a fair repair amount looks like."""
    t = repair_table()
    rows = [f"- {v['en']}: professional repair ${v['pro'][0]}-${v['pro'][1]}" for v in t["items"].values()]
    return ("REPAIR PRICE BENCHMARKS (Rentrail planning table, rough ranges for a small apartment; use them to judge "
            "whether a claimed repair amount is reasonable, and name the benchmark you used):\n" + "\n".join(rows))


async def deposit_case(user: dict, dispute_id: int, run_id: int) -> dict:
    dispute = db.one("SELECT * FROM disputes WHERE id = ? AND user_id = ?", (dispute_id, user["id"]))
    lease = lease_for(user["id"], dispute["lease_id"])
    lease_map = pii_map_load((lease or {}).get("analysis_meta", {}).get("pii_map_file"), user["id"])
    doc = prepare_document(user, dispute["deduction_file_id"], run_id, "deduction statement",
                           extra_names=[v for k, v in lease_map.items() if k.startswith("[PERSON")][:20])
    visible = "\n".join(doc["raw_pages"])
    parsed = parse_deductions(visible)
    facts = deposit_facts(user, dispute, lease)

    comparison = await compare(user, dispute["move_in_id"], dispute["move_out_id"], run_id)
    evid_ids = {it["later"]["evidence_id"] for it in comparison["items"]} | {
        it["earlier"]["evidence_id"] for it in comparison["items"] if it.get("earlier")} | {
        it["earlier_evidence_id"] for it in comparison["items"] if it.get("earlier_evidence_id")}
    mi = db.one("SELECT inspected_on FROM inspections WHERE id = ?", (dispute["move_in_id"],))["inspected_on"]
    mo = db.one("SELECT inspected_on FROM inspections WHERE id = ?", (dispute["move_out_id"],))["inspected_on"]
    comp_text = "\n".join(
        f"- later #{it['move_out_index']} [{it['later']['room']}] {it['later']['item']} {it['later']['damage_type']} "
        f"(Exhibit E{it['later']['evidence_id']}, move-out {mo}) => {it['status']}"
        + (f", matches Exhibit E{it['earlier']['evidence_id']} (move-in {mi})" if it.get("earlier") else "")
        + (f", same spot was clean at move-in in Exhibit E{it['earlier_evidence_id']} ({mi})"
           if not it.get("earlier") and it.get("earlier_evidence_id") else "")
        + f". {it['reason_en']}" for it in comparison["items"]) or "No damage found at move-out."
    pages_text = "\n".join(f"=== PAGE {i + 1} ===\n{p}" for i, p in enumerate(doc["pages"]))
    prompt = (
        "DEADLINE FACTS (computed by Rentrail code, trust these):\n" + db.dumps(facts) + "\n\n"
        "DEDUCTION ITEMS parsed by Rentrail code (use these items and amounts):\n" + db.dumps(parsed) + "\n\n"
        "MOVE-IN vs MOVE-OUT COMPARISON:\n" + comp_text + "\n\n" + _card_brief(lease and lease["card"]) + "\n\n"
        + _benchmarks_text() + "\n\n"
        + law.as_prompt() + "\n\n" + guard.fence("LANDLORD DEDUCTION STATEMENT", pages_text)
        + ("\n\nRentrail's checkpoint removed hidden (invisible) text from this document before you saw it."
           if doc["hidden"] else "")
    )
    ctx = Ctx(run_id=run_id, user_id=user["id"], evidence_ids=evid_ids,
              page_count=(lease or {}).get("page_count") or 0)
    brief = (await call(agents.counsel_brief(), run_id=run_id, user_id=user["id"], agent_name="counsel",
                        purpose="Deposit brief", prompt=prompt, caller="chief_justice", deps=ctx)).output
    brief_json = brief.model_dump(mode="json")

    claims = {it["item"].strip().lower(): it["amount"] for it in parsed} or {
        it.item.strip().lower(): it.amount_claimed for it in brief.items}
    ruling_prompt = (
        "Ruling mode — deposit case. Use the facts; the refund amount in your letter must equal "
        "REFUND_REQUESTED below once you set the approved deductions (Rentrail recomputes it).\n"
        "FACTS:\n" + db.dumps(facts) + "\n\nCOUNSEL BRIEF:\n" + db.dumps(brief_json) + "\n\n"
        "The tenant signs as [PERSON_1]. Use the item names exactly as in the brief.\n\n" + law.as_prompt()
    )
    ctx2 = Ctx(run_id=run_id, user_id=user["id"], evidence_ids=evid_ids, max_claims=claims,
               page_count=ctx.page_count)
    ruling = (await call(agents.chief_ruling(), run_id=run_id, user_id=user["id"], agent_name="chief_justice",
                         purpose="Final ruling + letter", prompt=ruling_prompt, caller="counsel", deps=ctx2)).output
    ruling_json = ruling.model_dump(mode="json")

    claimed_total = round(sum(claims.values()), 2)
    approved_total = round(sum(min(i.approved_deduction, claims.get(i.item.strip().lower(), i.approved_deduction))
                               for i in ruling.items), 2)
    refund = round(max(0.0, facts.get("deposit", 0) + facts.get("interest", 0) - approved_total), 2)
    money = {"deposit": facts.get("deposit", 0), "interest": facts.get("interest", 0), "claimed_total": claimed_total,
             "approved_total": approved_total, "refund_requested": refund,
             "landlord_keeps": approved_total, "statute_double_damages": facts.get("double_damages") if facts.get("statement_late") else None}
    mapping = {**lease_map, **doc["mapping"]}
    result = {"facts": facts, "parsed_items": parsed, "comparison": comparison, "brief": brief_json,
              "ruling": ruling_json, "money": money,
              "letter_en": privacy.unmask(ruling.letter_en, mapping),
              "officer": {"hidden_removed": doc["hidden"], "instruction_lines": doc["instruction_hits"],
                          "masked": doc["counts"]}}
    db.ex("UPDATE disputes SET result = ?, status = 'done', run_id = ? WHERE id = ?", (db.dumps(result), run_id, dispute_id))
    return result


# ---------------------------------------------------------------------------
# Sublets (everything is "as of" the user's simulated date)
# ---------------------------------------------------------------------------

def sublet_role(sublet: dict, user_id: int) -> str | None:
    if sublet["owner_id"] == user_id:
        return "sublessor"
    if sublet["subtenant_id"] == user_id:
        return "subtenant"
    return None


def sublease_for(sublet_id: int) -> dict | None:
    row = db.one("SELECT * FROM leases WHERE kind = 'sublease' AND sublet_id = ? ORDER BY id DESC LIMIT 1", (sublet_id,))
    if row:
        row["card"] = db.loads(row["card"], None)
        row["analysis_meta"] = db.loads(row["analysis_meta"], {})
    return row


def sublet_visible(s: dict, user: dict) -> bool:
    role = sublet_role(s, user["id"])
    if role == "sublessor":
        return clock.visible(s.get("listed_on") or s.get("created_at"), user)
    if role == "subtenant":
        return clock.visible(s.get("matched_on"), user)
    return False


def ledger_rows(sublet_id: int, user: dict | None = None) -> list[dict]:
    rows = db.q("SELECT * FROM ledger WHERE sublet_id = ? ORDER BY ts, id", (sublet_id,))
    return [r for r in rows if user is None or clock.visible(r["ts"], user)]


def ledger_add(sublet_id: int, kind: str, amount: float, from_party: str, to_party: str,
               method: str = "escrow", masked_account: str = "", note: str = "", ts: str | None = None,
               user_id: int | None = None, ref: str | None = None) -> None:
    db.insert("ledger", sublet_id=sublet_id, ts=ts or clock.stamp(user_id), kind=kind, amount=round(amount, 2),
              from_party=from_party, to_party=to_party, method=method, masked_account=masked_account, note=note, ref=ref)


ESCROW_IN = ("deposit_in", "interest_credit")
ESCROW_OUT = ("refund", "payout")


def escrow_balance(sublet_id: int, user: dict | None = None) -> float:
    bal = 0.0
    for r in ledger_rows(sublet_id, user):
        if r["kind"] in ESCROW_IN:
            bal += r["amount"]
        elif r["kind"] in ESCROW_OUT:
            bal -= r["amount"]
    return round(bal, 2)


def _settlement(s: dict, user: dict | None) -> dict | None:
    st = db.loads(s.get("settlement"), None)
    if not st or (user is not None and not clock.visible(st.get("proposed_on"), user)):
        return None
    return st


def sublet_state(s: dict, user: dict) -> dict:
    """Where the sublet is on the user's simulated date, with the date of every step."""
    today = clock.today(user)
    start, end = parse_date(s["start_date"]), parse_date(s["end_date"])
    rows = ledger_rows(s["id"], user)
    deposit = next((r for r in rows if r["kind"] == "deposit_in"), None)
    st = _settlement(s, user)
    ret = db.one("SELECT inspected_on FROM inspections WHERE id = ?", (s["return_id"],)) if s["return_id"] else None
    returned_on = ret["inspected_on"] if ret and clock.visible(ret["inspected_on"], user) else None
    released = (st.get("released_at") if st and st.get("status") == "released"
                and clock.visible(st.get("released_at"), user) else None)
    steps = [
        {"key": "listed", "date": s.get("listed_on")},
        {"key": "matched", "date": s.get("matched_on") if s["subtenant_id"] and clock.visible(s.get("matched_on"), user) else None},
        {"key": "deposit", "date": deposit["ts"][:10] if deposit else None},
        {"key": "moved_in", "date": s["start_date"] if start and start <= today else None},
        {"key": "returned", "date": returned_on},
        {"key": "settled", "date": released[:10] if released else None},
    ]
    if released:
        status = "closed"
    elif st and st.get("status") == "disputed":
        status = "disputed"
    elif st:
        status = "settlement_proposed"
    elif end and today > end:
        status = "return_due"
    elif start and start <= today:
        status = "active"
    elif deposit:
        status = "funded"
    elif s["subtenant_id"] and steps[1]["date"]:
        status = "matched"
    else:
        status = "open"
    return {"status": status, "steps": steps, "settlement": st}


def _sublet_utilities(s: dict) -> dict:
    """Who pays what during the sublet: the signed sublease wins, else the split typed in at creation."""
    sub = sublease_for(s["id"])
    out: dict[str, str] = {}
    for u in ((sub or {}).get("card") or {}).get("utilities", []):
        payer = (u.get("paid_by") or "").lower()
        out[u["service"].lower()] = "subtenant" if payer in ("tenant", "shared") else "sublessor"
    return out or {k.lower(): v for k, v in (db.loads(s["utilities"], {}) or {}).items()}


def utility_shares(s: dict, user: dict | None = None) -> list[dict]:
    """The sublessor's bills that overlap the sublet, for services the subtenant pays, pro-rated by days.
    Only bills already issued on the simulated date; each share is due 10 days after the bill."""
    split = _sublet_utilities(s)
    start, end = parse_date(s["start_date"]), parse_date(s["end_date"])
    if not (start and end):
        return []
    paid = {r["ref"]: r for r in ledger_rows(s["id"], user) if r["kind"] == "utility" and r.get("ref")}
    out = []
    for b in db.q("SELECT * FROM bills WHERE user_id = ? AND kind = 'bill'", (s["owner_id"],)):
        if user is not None and not clock.visible(b.get("issued_on"), user):
            continue
        r = db.loads(b["result"], {}) or {}
        service = (r.get("service") or "").lower()
        who = next((v for k, v in split.items() if k in service or service in k), None)
        ps, pe, amt = parse_date(r.get("period_start")), parse_date(r.get("period_end")), r.get("amount_due")
        if who != "subtenant" or not (ps and pe and amt):
            continue
        overlap = (min(pe, end) - max(ps, start)).days + 1
        period = (pe - ps).days + 1
        if overlap <= 0 or period <= 0:
            continue
        issued = parse_date(b.get("issued_on"))
        ref = f"utility:{b['id']}"
        out.append({"bill_id": b["id"], "ref": ref, "service": r.get("service"), "provider": r.get("provider"),
                    "period": f"{ps} → {pe}", "amount": amt, "overlap_days": overlap, "period_days": period,
                    "subtenant_share": round(amt * overlap / period, 2),
                    "due": (issued + timedelta(days=10)).isoformat() if issued else None,
                    "paid_on": paid[ref]["ts"][:10] if ref in paid else None})
    return out


async def sublet_docs(user: dict, sublet_id: int, run_id: int) -> dict:
    s = db.one("SELECT * FROM sublets WHERE id = ?", (sublet_id,))
    lease = lease_for(s["owner_id"], s["lease_id"])
    facts = {"start_date": s["start_date"], "end_date": s["end_date"], "monthly_rent": s["monthly_rent"],
             "deposit": s["deposit"], "utilities": db.loads(s["utilities"], {}),
             "sublessor": "[PERSON_1]", "subtenant": "[PERSON_2]", "escrow": "Rentrail escrow (held until return inspection)"}
    end = parse_date(s["end_date"])
    if end:
        facts["subtenant_deposit_return_deadline"] = law.return_deadline(end, None).isoformat()
    prompt = ("Documents mode.\nSUBLET FACTS:\n" + db.dumps(facts) + "\n\n" + _card_brief(lease and lease["card"])
              + "\n\n" + law.as_prompt({"sublet", "return", "escrow", "interest", "deductions", "tenant_duties"}))
    ctx = Ctx(run_id=run_id, user_id=user["id"])
    out = (await call(agents.sheriff_docs(), run_id=run_id, user_id=user["id"], agent_name="sheriff",
                      purpose="Sublet documents", prompt=prompt, caller="chief_justice", deps=ctx)).output
    docs = out.model_dump(mode="json")
    names = _names(s)
    docs["consent_letter_en"] = privacy.unmask(docs["consent_letter_en"], names)
    docs["agreement_md_en"] = privacy.unmask(docs["agreement_md_en"], names)
    db.ex("UPDATE sublets SET docs = ?, docs_on = ? WHERE id = ?", (db.dumps(docs), clock.today(user).isoformat(), sublet_id))
    return docs


def _comparison_text(comparison: dict) -> str:
    return "\n".join(
        f"- [{it['later']['room']}] {it['later']['item']} {it['later']['damage_type']} at {it['later']['location']} "
        f"(Exhibit E{it['later']['evidence_id']}) => {it['status']}"
        + (f", same spot clean at hand-off in Exhibit E{it['earlier_evidence_id']}"
           if it.get("earlier_evidence_id") and not it.get("earlier") else "")
        + f". {it['reason_en']}" for it in comparison["items"]) or "No damage found at return."


def _evidence_ids(comparison: dict) -> set[int]:
    return ({it["later"]["evidence_id"] for it in comparison["items"]}
            | {it["earlier"]["evidence_id"] for it in comparison["items"] if it.get("earlier")}
            | {it["earlier_evidence_id"] for it in comparison["items"] if it.get("earlier_evidence_id")})


def _money_from_ruling(s: dict, ruling: Any, claims: dict[str, float], held: float) -> dict:
    approved = round(sum(min(i.approved_deduction, claims.get(i.item.strip().lower(), i.approved_deduction))
                         for i in ruling.items), 2)
    approved = min(approved, held)
    start, end = parse_date(s["start_date"]), parse_date(s["end_date"])
    interest = law.deposit_interest(s["deposit"] or 0, start, end) if start and end else 0.0
    pending = round(min(sum(i.hold_pending for i in ruling.items), held - approved), 2)
    return {"held": held, "interest": interest, "approved_deductions": approved, "pending": pending,
            "pending_items": [{"item": i.item, "amount": i.hold_pending, "note_en": i.note_en, "note_ko": i.note_ko}
                              for i in ruling.items if i.hold_pending > 0],
            "to_sublessor": approved, "to_subtenant": round(held - approved - pending + interest, 2),
            "deadline": law.return_deadline(end, None).isoformat() if end else None}


def _names(s: dict) -> dict[str, str]:
    owner = db.one("SELECT name FROM users WHERE id = ?", (s["owner_id"],))
    sub = db.one("SELECT name FROM users WHERE id = ?", (s["subtenant_id"],)) if s["subtenant_id"] else None
    return {"[PERSON_1]": owner["name"], "[PERSON_2]": sub["name"] if sub else "[Subtenant]"}


async def sublet_settle(user: dict, sublet_id: int, run_id: int) -> dict:
    s = db.one("SELECT * FROM sublets WHERE id = ?", (sublet_id,))
    h = db.one("SELECT * FROM inspections WHERE id = ?", (s["handoff_id"],)) if s["handoff_id"] else None
    r = db.one("SELECT * FROM inspections WHERE id = ?", (s["return_id"],)) if s["return_id"] else None
    if not (h and r) or not clock.visible(r["inspected_on"], user):
        raise ValueError("The return inspection has not happened yet on this date.")
    if not (h["result"] and r["result"]):
        raise ValueError("Run Detective Dan on both the hand-off and the return inspection first.")
    comparison = await compare(user, s["handoff_id"], s["return_id"], run_id)
    evid_ids = _evidence_ids(comparison)
    shares = [x for x in utility_shares(s, user) if not x["paid_on"]]
    held = escrow_balance(sublet_id, user)
    sub = sublease_for(sublet_id)
    facts = {"deposit_in_escrow": held, "sublet_start": s["start_date"], "sublet_end": s["end_date"],
             "unpaid_utility_shares_computed": shares, "today": clock.today(user).isoformat()}
    ctx = Ctx(run_id=run_id, user_id=user["id"], evidence_ids=evid_ids)
    claim = (await call(agents.sheriff_claim(), run_id=run_id, user_id=user["id"], agent_name="sheriff",
                        purpose="Escrow claim", caller="chief_justice", deps=ctx,
                        prompt="Claim mode.\nHAND-OFF vs RETURN COMPARISON:\n" + _comparison_text(comparison)
                        + "\n\nFACTS:\n" + db.dumps(facts) + "\n\nSUBLEASE " + _card_brief(sub and sub["card"])
                        + "\n\n" + law.as_prompt({"sublet", "return", "deductions", "tenant_duties"}))).output
    claim_json = claim.model_dump(mode="json")
    claims = {i.item.strip().lower(): i.amount for i in claim.items}
    for sh in shares:
        claims[f"utility share: {sh['service']}".lower()] = sh["subtenant_share"]
    ruling_prompt = ("Ruling mode - sublet escrow case. You are neutral between the sublessor [PERSON_1] and the "
                     "subtenant [PERSON_2]. Approve deductions only for proven new damage and the computed UNPAID utility "
                     "shares (name them 'Utility share: <service>'). Write letter_en as a settlement notice to both parties.\n"
                     "CLAIM:\n" + db.dumps(claim_json) + "\nUNPAID UTILITY SHARES (code, approve as computed):\n"
                     + db.dumps(shares) + "\nFACTS:\n" + db.dumps(facts) + "\n\nSUBLEASE " + _card_brief(sub and sub["card"])
                     + "\n\n" + law.as_prompt({"sublet", "return", "deductions"}))
    ctx2 = Ctx(run_id=run_id, user_id=user["id"], evidence_ids=evid_ids, max_claims=claims)
    ruling = (await call(agents.chief_ruling(), run_id=run_id, user_id=user["id"], agent_name="chief_justice",
                         purpose="Escrow ruling", prompt=ruling_prompt, caller="sheriff", deps=ctx2)).output
    settlement = {**_money_from_ruling(s, ruling, claims, held), "comparison": comparison, "claim": claim_json,
                  "claims": claims, "ruling": ruling.model_dump(mode="json"), "utility_shares": shares,
                  "status": "proposed", "accepted_by": [], "proposed_on": clock.today(user).isoformat(),
                  "letter_en": privacy.unmask(ruling.letter_en, _names(s)), "history": []}
    db.ex("UPDATE sublets SET settlement = ?, status = 'settlement_proposed' WHERE id = ?", (db.dumps(settlement), sublet_id))
    return settlement


async def sublet_appeal(user: dict, sublet_id: int, reason: str, run_id: int) -> dict:
    """The subtenant disputes the proposal: Counsel Dan argues for the subtenant, the Chief Justice rules again."""
    s = db.one("SELECT * FROM sublets WHERE id = ?", (sublet_id,))
    st = db.loads(s["settlement"], {})
    if not st or st.get("status") == "released":
        raise ValueError("There is no open proposal to appeal.")
    comparison = st["comparison"]
    evid_ids = _evidence_ids(comparison)
    claims = st.get("claims") or {i["item"].strip().lower(): i["approved_deduction"] + i.get("hold_pending", 0)
                                  for i in st["ruling"]["items"]}
    items = [{"item": i["item"], "amount": round(i["approved_deduction"] + i.get("hold_pending", 0), 2)}
             for i in st["ruling"]["items"] if i["approved_deduction"] + i.get("hold_pending", 0) > 0]
    sub = sublease_for(sublet_id)
    hits = guard.instruction_hits(reason)
    if hits:
        guard.log(user["id"], "instruction_text_flagged", {"document": "appeal reason", "lines": hits}, run_id)
    facts = {"deposit_in_escrow": st["held"], "sublet_end": s["end_date"], "return_deadline": st.get("deadline")}
    prompt = ("You act for the SUBTENANT [PERSON_2], who disputes the sublessor's escrow deductions.\n"
              "DEDUCTION ITEMS (the current proposal; use these items and amounts):\n" + db.dumps(items)
              + "\n\nHAND-OFF vs RETURN COMPARISON:\n" + _comparison_text(comparison)
              + "\n\nFACTS:\n" + db.dumps(facts) + "\n\nSUBLEASE " + _card_brief(sub and sub["card"])
              + "\n\n" + law.as_prompt() + "\n\n" + guard.fence("SUBTENANT'S REASON", reason[:1500]))
    ctx = Ctx(run_id=run_id, user_id=user["id"], evidence_ids=evid_ids, page_count=(sub or {}).get("page_count") or 0)
    brief = (await call(agents.counsel_brief(), run_id=run_id, user_id=user["id"], agent_name="counsel",
                        purpose="Appeal brief for the subtenant", prompt=prompt, caller="chief_justice", deps=ctx)).output
    ruling_prompt = ("Ruling mode - APPEAL in a sublet escrow case. Neutral between sublessor [PERSON_1] and subtenant "
                     "[PERSON_2]. Re-decide every item with the subtenant's appeal brief in mind; keep proven new damage and "
                     "computed utility shares unless the brief shows they are wrong. Write letter_en as the final notice.\n"
                     "PREVIOUS RULING:\n" + db.dumps(st["ruling"]) + "\nAPPEAL BRIEF (Counsel for the subtenant):\n"
                     + db.dumps(brief.model_dump(mode="json")) + "\n\n" + law.as_prompt({"sublet", "return", "deductions"}))
    ctx2 = Ctx(run_id=run_id, user_id=user["id"], evidence_ids=evid_ids, max_claims=claims)
    ruling = (await call(agents.chief_ruling(), run_id=run_id, user_id=user["id"], agent_name="chief_justice",
                         purpose="Appeal ruling", prompt=ruling_prompt, caller="counsel", deps=ctx2)).output
    history = st.get("history", []) + [{"ruling": st["ruling"], "to_subtenant": st["to_subtenant"], "on": st.get("proposed_on")}]
    st.update(_money_from_ruling(s, ruling, claims, st["held"]))
    st.update({"ruling": ruling.model_dump(mode="json"), "status": "proposed", "accepted_by": [], "history": history,
               "appeal": {"reason": reason[:1500], "brief": brief.model_dump(mode="json"), "on": clock.today(user).isoformat()},
               "letter_en": privacy.unmask(ruling.letter_en, _names(s)), "proposed_on": clock.today(user).isoformat()})
    db.ex("UPDATE sublets SET settlement = ?, status = 'settlement_proposed' WHERE id = ?", (db.dumps(st), sublet_id))
    return st


def sublet_release(sublet_id: int, user_id: int) -> dict:
    """Both sides accepted: pay out from escrow (simulated), dated on the accepting user's simulated day."""
    s = db.one("SELECT * FROM sublets WHERE id = ?", (sublet_id,))
    st = db.loads(s["settlement"], {})
    if st.get("status") == "released":
        return st
    if st["interest"]:
        ledger_add(sublet_id, "interest_credit", st["interest"], "Rentrail escrow bank", "escrow",
                   note="CT-47a-21-i interest at the 2026 rate (0.49%)", user_id=user_id)
    if st["to_sublessor"] > 0:
        ledger_add(sublet_id, "payout", st["to_sublessor"], "escrow", "sublessor", method="ach",
                   note="Approved deductions (Chief Justice ruling)", user_id=user_id)
    ledger_add(sublet_id, "refund", st["to_subtenant"], "escrow", "subtenant", method="original payment method",
               note="Deposit balance + interest", user_id=user_id)
    if st.get("pending"):
        ledger_add(sublet_id, "hold", st["pending"], "escrow", "escrow",
                   note="Kept in escrow until a repair invoice is uploaded", user_id=user_id)
    st["status"] = "released"
    st["released_at"] = clock.stamp(user_id)
    db.ex("UPDATE sublets SET settlement = ?, status = 'closed' WHERE id = ?", (db.dumps(st), sublet_id))
    return st


def sublet_invoice(sublet_id: int, amount: float, file_id: int | None, note: str, user_id: int) -> dict:
    """The sublessor shows a repair invoice: pay the documented part of the hold, return the rest."""
    s = db.one("SELECT * FROM sublets WHERE id = ?", (sublet_id,))
    st = db.loads(s["settlement"], {})
    pending = float(st.get("pending") or 0)
    if st.get("status") != "released" or pending <= 0:
        raise ValueError("Nothing is being held for an invoice.")
    pay = round(min(max(amount, 0), pending), 2)
    back = round(pending - pay, 2)
    if pay:
        ledger_add(sublet_id, "payout", pay, "escrow", "sublessor", method="ach", note=f"Repair invoice: {note[:80]}",
                   user_id=user_id)
    if back:
        ledger_add(sublet_id, "refund", back, "escrow", "subtenant", method="original payment method",
                   note="Unused part of the repair hold", user_id=user_id)
    st.update({"pending": 0, "invoice": {"amount": amount, "paid": pay, "returned": back, "file_id": file_id,
                                         "note": note[:200], "at": clock.stamp(user_id)}})
    st["to_sublessor"] = round(st["to_sublessor"] + pay, 2)
    st["to_subtenant"] = round(st["to_subtenant"] + back, 2)
    db.ex("UPDATE sublets SET settlement = ? WHERE id = ?", (db.dumps(st), sublet_id))
    return st


def sublet_reset(sublet_id: int) -> None:
    """Back to the moment the two sides were matched: no payments, no settlement (documents and records stay)."""
    s = db.one("SELECT * FROM sublets WHERE id = ?", (sublet_id,))
    db.ex("DELETE FROM ledger WHERE sublet_id = ?", (sublet_id,))
    db.ex("UPDATE sublets SET settlement = NULL, status = ? WHERE id = ?", ("matched" if s["subtenant_id"] else "open", sublet_id))


# ---------------------------------------------------------------------------
# Bills and insurance
# ---------------------------------------------------------------------------

async def read_bill(user: dict, bill_id: int, run_id: int) -> dict:
    bill = db.one("SELECT * FROM bills WHERE id = ? AND user_id = ?", (bill_id, user["id"]))
    doc = prepare_document(user, bill["file_id"], run_id, bill["kind"])
    lease = lease_for(user["id"])
    text = "\n".join(f"=== PAGE {i + 1} ===\n{p}" for i, p in enumerate(doc["pages"][:6]))
    ctx = Ctx(run_id=run_id, user_id=user["id"])
    if bill["kind"] == "policy":
        out = (await call(agents.treasurer_policy(), run_id=run_id, user_id=user["id"], agent_name="treasurer",
                          purpose="Insurance policy", caller="chief_justice", deps=ctx,
                          prompt="Insurance mode.\n" + _card_brief(lease and lease["card"]) + "\n\n" + guard.fence("POLICY", text))).output
        data = out.model_dump(mode="json")
        need = ((lease or {}).get("card") or {}).get("insurance_min_liability")
        data["lease_requirement"] = need
        data["requirement_met"] = (data.get("liability_limit") or 0) >= need if need else None
    else:
        out = (await call(agents.treasurer_bill(), run_id=run_id, user_id=user["id"], agent_name="treasurer",
                          purpose="Utility bill", caller="chief_justice", deps=ctx,
                          prompt=f"Bill mode. Today is {user_today(user)}.\n" + _card_brief(lease and lease["card"])
                          + "\n\n" + guard.fence("BILL", text))).output
        data = out.model_dump(mode="json")
    db.ex("UPDATE bills SET result = ?, run_id = ? WHERE id = ?", (db.dumps(data), run_id, bill_id))
    return data


# ---------------------------------------------------------------------------
# Calendar (pure code)
# ---------------------------------------------------------------------------

def _task(key, d: date | None, cat, en, ko, law_id=None, detail_en="", detail_ko="", page=None, amount=None):
    return {"key": key, "date": d.isoformat() if d else None, "category": cat, "title_en": en, "title_ko": ko,
            "law_id": law_id, "detail_en": detail_en, "detail_ko": detail_ko, "page": page,
            "amount": round(float(amount), 2) if amount else None}


def _next_rent(card: dict, today: date, start: date, end: date | None, pages: dict, sub: bool) -> dict | None:
    due_day = min(int(card.get("rent_due_day") or 1), 28)
    nxt = date(today.year, today.month, due_day)
    if nxt < today:
        nxt = date(today.year + (today.month == 12), today.month % 12 + 1, due_day)
    nxt = max(nxt, start)
    if end and nxt > end:
        return None
    return _task(f"rent_{nxt.isoformat()}", nxt, "rent", "Pay sublet rent" if sub else "Pay rent",
                 "서브렛 월세 납부" if sub else "월세 납부", page=pages.get("rent"), amount=card.get("monthly_rent"))


def calendar(user: dict) -> list[dict]:
    """Deadlines from the governing contract, CT law, visible bills and the sublet, as of the simulated date."""
    tasks: list[dict] = []
    today = user_today(user)
    mode = user.get("mode") or "tenant"
    lease = lease_for_user(user)
    card = (lease or {}).get("card") or {}
    is_sub = (lease or {}).get("kind") == "sublease"
    pages = {c["key"]: c.get("page") for c in card.get("clauses", [])}
    start, end = parse_date(card.get("lease_start")), parse_date(card.get("lease_end"))

    if start and card.get("monthly_rent"):
        t = _next_rent(card, today, start, end, pages, is_sub)
        if t:
            tasks.append(t)
    if start and not is_sub:
        hours = card.get("inventory_form_hours") or 48
        tasks.append(_task("inventory_form", start + timedelta(hours=hours), "move_in",
                           f"Return the Inventory & Condition Form ({hours} h after move-in)",
                           f"입주 상태 점검표 제출 (입주 후 {hours}시간)", "DOB-docs",
                           "Otherwise the unit may be treated as clean. Use Rentrail's move-in inspection.",
                           "제출하지 않으면 깨끗한 상태로 간주될 수 있습니다. Rentrail 입주 점검을 쓰세요.", pages.get("inventory_form")))
        tasks.append(_task("escrow_notice", start + timedelta(days=30), "deposit",
                           "Check you received the deposit escrow notice (bank name + amount)",
                           "보증금 에스크로 통지(은행명·금액)를 받았는지 확인", "CT-47a-21-h4"))
        anniv = start + timedelta(days=365)
        tasks.append(_task("interest_anniversary", anniv, "deposit", "Deposit interest is due on the tenancy anniversary",
                           "임대 1주년: 보증금 이자 지급(또는 월세 차감) 확인", "CT-47a-21-i"))
    if end and not is_sub:
        notice = card.get("move_out_notice_days")
        if notice:
            tasks.append(_task("move_out_notice", end - timedelta(days=int(notice)), "move_out",
                               f"Deadline to give written move-out notice ({notice} days before the end)",
                               f"퇴거 서면 통지 마감 (종료 {notice}일 전)", "DOB-notice",
                               "Send it in writing; certified mail with return receipt is recommended.",
                               "서면으로 보내고, 배달증명 우편을 권장합니다.", pages.get("move_out_notice")))
        tasks.append(_task("move_out_inspection", end, "move_out",
                           "Record the move-out inspection (same spots as move-in) and return keys",
                           "퇴거 점검 기록(입주 때와 같은 위치) + 열쇠 반납", "DOB-joint"))
        tasks.append(_task("forwarding_address", end, "move_out", "Give your forwarding address in writing",
                           "새 주소를 서면으로 통지", "CT-47a-21-d2",
                           "The 21-day clock (or 15 days after your address) starts from this.",
                           "21일(또는 주소 통지 후 15일) 반환 기한이 여기서 시작됩니다."))
        tasks.append(_task("deposit_deadline", law.return_deadline(end, end), "deposit",
                           "Landlord's deadline: deposit + interest or itemized statement",
                           "집주인 기한: 보증금+이자 반환 또는 공제 내역서", "CT-47a-21-d2",
                           "If missed, the landlord may owe twice the deposit.", "놓치면 보증금의 2배를 배상해야 할 수 있습니다.",
                           amount=card.get("security_deposit")))

    if mode != "subtenant":
        for b in db.q("SELECT * FROM bills WHERE user_id = ?", (user["id"],)):
            if not clock.visible(b.get("issued_on"), user):
                continue  # the bill has not arrived yet on this date
            r = db.loads(b["result"], {}) or {}
            if b["kind"] == "policy":
                pe = parse_date(r.get("period_end"))
                if pe:
                    tasks.append(_task(f"policy_{b['id']}", pe, "bills", "Renter's insurance renews / ends", "세입자 보험 갱신(만료)일"))
                continue
            due = parse_date(r.get("due_date"))
            if due:
                tasks.append(_task(f"bill_{b['id']}", due, "bills", f"Pay {r.get('provider') or 'bill'}",
                                   f"{r.get('provider') or '고지서'} 납부", amount=r.get("amount_due")))
            ce = parse_date(r.get("supplier_contract_end"))
            if ce:
                tasks.append(_task(f"supplier_{b['id']}", ce - timedelta(days=14), "bills",
                                   "Electricity supplier contract ends soon - compare rates", "전기 공급 계약 종료 임박 — 요금 비교"))

    for s in db.q("SELECT * FROM sublets WHERE owner_id = ? OR subtenant_id = ?", (user["id"], user["id"])):
        if not sublet_visible(s, user) or (mode == "tenant" and sublet_role(s, user["id"]) == "sublessor"):
            continue
        role = sublet_role(s, user["id"])
        ss, se = parse_date(s["start_date"]), parse_date(s["end_date"])
        if role == "subtenant" and not any(r["kind"] == "deposit_in" for r in ledger_rows(s["id"], user)):
            tasks.append(_task(f"sublet_{s['id']}_deposit", ss - timedelta(days=7) if ss else None, "sublet",
                               "Put the sublet deposit in Rentrail escrow", "서브렛 보증금을 에스크로에 입금", amount=s["deposit"]))
        if ss:
            tasks.append(_task(f"sublet_{s['id']}_handoff", ss, "sublet", "Sublet hand-off inspection (both sides)",
                               "서브렛 인계 점검 (양쪽 함께)"))
        if se:
            tasks.append(_task(f"sublet_{s['id']}_return", se, "sublet", "Sublet return inspection", "서브렛 반환 점검"))
            tasks.append(_task(f"sublet_{s['id']}_deadline", law.return_deadline(se, None), "sublet",
                               "Sublet deposit must be settled (a sublessor is a landlord under CT law)"
                               if role == "sublessor" else "Your sublet deposit should be returned by",
                               "서브렛 보증금 정산 기한 (CT 법상 서브렛을 내준 사람도 집주인)" if role == "sublessor"
                               else "서브렛 보증금 반환 기한", "CT-47a-21-a7", amount=s["deposit"]))
        for sh in utility_shares(s, user):
            if sh["paid_on"]:
                continue
            tasks.append(_task(f"share_{sh['bill_id']}", parse_date(sh["due"]), "bills",
                               f"Utility share: {sh['service']} ({sh['overlap_days']}/{sh['period_days']} days)"
                               + (" - pay the sublessor" if role == "subtenant" else " - due from the subtenant"),
                               f"공과금 분담: {sh['service']} ({sh['overlap_days']}/{sh['period_days']}일)"
                               + (" — 서브렛 내준 사람에게 납부" if role == "subtenant" else " — 서브렛 세입자에게 받을 금액"),
                               amount=sh["subtenant_share"]))

    done = {r["task_key"] for r in db.q("SELECT task_key FROM tasks_done WHERE user_id = ?", (user["id"],))}
    for t in tasks:
        t["done"] = t["key"] in done
        d = parse_date(t["date"])
        t["days_left"] = (d - today).days if d else None
    return sorted(tasks, key=lambda t: t["date"] or "9999")


# ---------------------------------------------------------------------------
# Move-out precheck: fix it yourself, hire someone, or let it be deducted?
# The Detective classifies each damage (before vs. after), Counsel picks a repair category and judges
# wear-and-tear / DIY suitability, and code attaches every dollar figure from repair_costs.json.
# ---------------------------------------------------------------------------

REPAIR_TABLE_PATH = Path(__file__).resolve().parent / "repair_costs.json"


def repair_table() -> dict:
    return json.loads(REPAIR_TABLE_PATH.read_text(encoding="utf-8"))


def _baseline_record(user: dict) -> dict | None:
    """Move-in record for a tenant; the sublet hand-off for a subtenant."""
    if (user.get("mode") or "tenant") == "subtenant":
        rows = db.q("SELECT i.* FROM inspections i JOIN sublets s ON s.id = i.sublet_id "
                    "WHERE s.subtenant_id = ? AND i.kind = 'sublet_handoff' ORDER BY i.inspected_on", (user["id"],))
    else:
        rows = db.q("SELECT * FROM inspections WHERE user_id = ? AND kind = 'move_in' AND sublet_id IS NULL "
                    "ORDER BY inspected_on, id", (user["id"],))
    rows = [r for r in rows if clock.visible(r["inspected_on"], user)]
    return rows[0] if rows else None


def precheck_records(user: dict) -> tuple[dict | None, dict | None]:
    """Baseline record and the latest analysed record after it (safety-test records are skipped)."""
    base = _baseline_record(user)
    if not base:
        return None, None
    rows = db.q("SELECT * FROM inspections WHERE (user_id = ? OR sublet_id IN "
                "(SELECT id FROM sublets WHERE owner_id = ? OR subtenant_id = ?)) AND id != ? "
                "ORDER BY inspected_on, id", (user["id"], user["id"], user["id"], base["id"]))
    later = [r for r in rows if clock.visible(r["inspected_on"], user) and r["result"]
             and r["inspected_on"] >= base["inspected_on"] and not (r["title"] or "").lower().startswith("safety test")]
    return base, (later[-1] if later else None)


def _action(status: str, pick: dict, cost: dict) -> tuple[str, float, float]:
    """Returns (action, expected charge if the tenant does nothing, cost of the recommended action)."""
    low, high = cost["charge"]
    charge = round((low + high) / 2, 2)
    if status == "pre_existing":
        return "covered", 0.0, 0.0
    if status == "wear_and_tear" or pick.get("normal_wear"):
        return "wear", 0.0, 0.0
    pro = round(sum(cost["pro"]) / 2, 2)
    if pick.get("diy_suitable") and cost.get("diy_cost") is not None and cost["difficulty"] in ("easy", "medium"):
        return "fix_yourself", charge, float(cost["diy_cost"])
    if pro < charge:
        return "hire_pro", charge, pro
    return "let_deduct", charge, charge


async def precheck(user: dict, earlier_id: int, later_id: int, run_id: int) -> dict:
    lease = lease_for_user(user)
    card = (lease or {}).get("card") or {}
    end = parse_date(card.get("lease_end"))
    today = user_today(user)
    officer_step(run_id, user["id"], "Screen the records for the move-out precheck", {
        "records": [earlier_id, later_id], "rule": "photos are evidence; prices come from Rentrail's repair table, not the AI"})
    comparison = await compare(user, earlier_id, later_id, run_id)
    later = db.one("SELECT * FROM inspections WHERE id = ?", (later_id,))
    l_find = (db.loads(later["result"], {}) or {}).get("findings", [])
    table = repair_table()
    out: dict[str, Any] = {"earlier_id": earlier_id, "later_id": later_id, "created_on": today.isoformat(),
                           "move_out_date": end and end.isoformat(), "days_to_move_out": (end - today).days if end else None,
                           "comparison_summary_en": comparison.get("summary_en"), "comparison_summary_ko": comparison.get("summary_ko"),
                           "table_note_en": table["note_en"], "table_note_ko": table["note_ko"], "items": []}
    if not l_find:
        out.update(summary_en="No damage in your latest record. Keep the photos and record the move-out walkthrough.",
                   summary_ko="최근 기록에 하자가 없습니다. 사진을 보관하고 퇴거 점검을 기록하세요.",
                   totals={"if_nothing": 0.0, "with_plan": 0.0, "saves": 0.0})
        db.insert("prechecks", user_id=user["id"], earlier_id=earlier_id, later_id=later_id, result=db.dumps(out),
                  run_id=run_id, created_on=today.isoformat())
        return out

    status_of = {it["move_out_index"]: it for it in comparison["items"]}
    # If the tenant sublet the place in between, damage that is not in the sublet hand-off record appeared
    # during the sublet: the sublessor can claim it from the sublet escrow (CT-47a-21-a7).
    handoffs = db.q("SELECT i.* FROM inspections i JOIN sublets s ON s.handoff_id = i.id WHERE s.owner_id = ? "
                    "AND i.inspected_on > ? AND i.inspected_on < ?", (user["id"], db.one(
                        "SELECT inspected_on FROM inspections WHERE id = ?", (earlier_id,))["inspected_on"], later["inspected_on"]))
    # Match by room + surface (floor / wall / ...), not by the damage word: the same floor gouge may be
    # called a "gouge" at hand-off and a "chip" at return.
    def spot(f: dict) -> tuple[str, str]:
        item = (f.get("item") or "").lower()
        if any(k in item for k in ("floor", "laminate", "plank", "carpet")):
            surface = "floor"
        else:
            surface = next((k for k in ("wall", "door", "window", "ceiling", "cabinet", "counter") if k in item), item)
        return (f.get("room") or "").strip().lower(), surface

    handoff_keys = {spot(f) for h in handoffs for f in (db.loads(h["result"], {}) or {}).get("findings", [])}
    table_text = "\n".join(f"- {k}: {v['en']}" for k, v in table["items"].items())
    lines = []
    for i, f in enumerate(l_find):
        c = status_of.get(i, {})
        lines.append(f"{i}: [{f['room']}] {f['item']} — {f['damage_type']} at {f['location']}, severity {f['severity']}. "
                     f"Detective: {c.get('status', 'unclear')} — {c.get('reason_en', '')}")
    prompt = (
        f"Precheck mode. Today is {today.isoformat()}; the lease ends {end.isoformat() if end else 'unknown'}.\n"
        f"EARLIER record {earlier_id} vs LATER record {later_id}. Refer to photos as 'Exhibit E<id>', never by index.\n\n"
        "LATER findings (index: finding):\n" + "\n".join(lines)
        + "\n\nREPAIR TABLE (choose one key per item):\n" + table_text + "\n\n" + _card_brief(card)
        + "\n\n" + law.as_prompt({"deductions", "tenant_duties", "move_out", "return"})
    )
    ctx = Ctx(run_id=run_id, user_id=user["id"], page_count=(lease or {}).get("page_count") or 0,
              extra={"n_later": len(l_find)})
    plan = (await call(agents.counsel_precheck(), run_id=run_id, user_id=user["id"], agent_name="counsel",
                       purpose="Move-out precheck: fix or pay", prompt=prompt, caller="chief_justice", deps=ctx)).output
    picks = {p.later_index: p.model_dump(mode="json") for p in plan.items}
    tot_nothing = tot_plan = 0.0
    for i, f in enumerate(l_find):
        c = status_of.get(i, {})
        pick = picks.get(i, {"repair_key": "other"})
        cost = table["items"].get(pick.get("repair_key"), table["items"]["other"])
        action, charge, plan_cost = _action(c.get("status", "unclear"), pick, cost)
        during_sublet = bool(handoffs) and action not in ("covered", "wear") and spot(f) not in handoff_keys
        tot_nothing += charge
        tot_plan += plan_cost
        out["items"].append({
            "during_sublet": during_sublet,
            "finding": f, "status": c.get("status", "unclear"), "reason_en": c.get("reason_en", ""), "reason_ko": c.get("reason_ko", ""),
            "earlier_evidence_id": (c.get("earlier") or {}).get("evidence_id") or c.get("earlier_evidence_id"),
            "repair_key": pick.get("repair_key"), "label_en": cost["en"], "label_ko": cost["ko"],
            "charge_range": cost["charge"], "pro_range": cost["pro"], "diy_cost": cost.get("diy_cost"),
            "diy_minutes": cost.get("diy_minutes"), "difficulty": cost["difficulty"],
            "action": action, "expected_charge": charge, "plan_cost": plan_cost, "saves": round(charge - plan_cost, 2),
            "steps_en": pick.get("steps_en", []), "steps_ko": pick.get("steps_ko", []),
            "tip_en": pick.get("tip_en", ""), "tip_ko": pick.get("tip_ko", ""),
            "lease_pages": pick.get("lease_pages", []), "law_ids": pick.get("law_ids", []),
        })
    out["totals"] = {"if_nothing": round(tot_nothing, 2), "with_plan": round(tot_plan, 2),
                     "saves": round(tot_nothing - tot_plan, 2),
                     "from_sublet_escrow": round(sum(i["plan_cost"] for i in out["items"] if i["during_sublet"]), 2)}
    out["summary_en"], out["summary_ko"] = plan.summary_en, plan.summary_ko
    db.insert("prechecks", user_id=user["id"], earlier_id=earlier_id, later_id=later_id, result=db.dumps(out),
              run_id=run_id, created_on=today.isoformat())
    return out


def latest_precheck(user: dict) -> dict | None:
    rows = db.q("SELECT * FROM prechecks WHERE user_id = ? ORDER BY created_on DESC, id DESC", (user["id"],))
    row = next((r for r in rows if clock.visible(r["created_on"], user)), None)
    if not row:
        return None
    row["result"] = db.loads(row["result"], None)
    return row


# ---------------------------------------------------------------------------
# Deposit Shield: how well protected the deposit is, as of the simulated date. Plain code, no AI.
# ---------------------------------------------------------------------------

SHIELD_ROOMS = ("Living room", "Bedroom", "Kitchen", "Bathroom")
SHIELD_LEVELS = [(90, "gold", "Gold shield", "황금 방패"), (70, "steel", "Steel shield", "강철 방패"),
                 (40, "wood", "Wooden shield", "나무 방패"), (0, "paper", "Paper shield", "종이 방패")]
ROOM_KO = {"Living room": "거실", "Bedroom": "침실", "Kitchen": "주방", "Bathroom": "욕실"}


def shield(user: dict) -> dict:
    today = user_today(user)
    sub = (user.get("mode") or "tenant") == "subtenant"
    lease = lease_for_user(user)
    card = (lease or {}).get("card") or {}
    start, end = parse_date(card.get("lease_start")), parse_date(card.get("lease_end"))
    base = _baseline_record(user)
    ev = evidence_for(base["id"]) if base else []
    photos = [e for e in ev if e["mime"].startswith("image/") and e.get("t_seconds") is None]
    frames = [e for e in ev if e.get("t_seconds") is not None]
    rooms = {(e.get("room") or "").strip().lower() for e in ev}
    covered = [r for r in SHIELD_ROOMS if r.lower() in rooms]
    missing_rooms = [r for r in SHIELD_ROOMS if r.lower() not in rooms]
    base_name = ("hand-off record", "인계 기록") if sub else ("move-in record", "입주 기록")
    checks: list[dict] = []

    def add(key, pts, earned, en, ko, fix_en="", fix_ko="", page="inspections", phase="now"):
        checks.append({"key": key, "points": pts, "earned": round(earned, 1), "done": earned >= pts - 0.01,
                       "title_en": en, "title_ko": ko, "fix_en": fix_en, "fix_ko": fix_ko, "page": page, "phase": phase})

    add("lease", 10, 10 if card else 0, "Lease read by Clerk Dan", "서기관 댄이 계약서 정리",
        "Upload your lease PDF.", "계약서 PDF를 올리세요.", "lease")
    add("photos", 15, 15 if photos else 0, f"Photos in your {base_name[0]}", f"{base_name[1]}에 사진",
        "Add close-up photos of anything already damaged.", "이미 있는 하자를 가까이서 찍어 올리세요.")
    add("video", 10, 10 if frames else 0, f"Walkthrough video in your {base_name[0]}", f"{base_name[1]}에 둘러보기 영상",
        "Film one slow loop through every room.", "모든 방을 천천히 한 바퀴 찍으세요.")
    add("rooms", 15, 15 * len(covered) / len(SHIELD_ROOMS), f"Key rooms covered ({len(covered)}/{len(SHIELD_ROOMS)})",
        f"주요 공간 기록 ({len(covered)}/{len(SHIELD_ROOMS)})",
        ("Missing: " + ", ".join(missing_rooms)) if missing_rooms else "",
        ("빠진 곳: " + ", ".join(ROOM_KO[r] for r in missing_rooms)) if missing_rooms else "")
    add("analysed", 10, 10 if base and base["result"] else 0, "Checked by Detective Dan", "형사 댄 점검 완료",
        "Press Run on the record.", "기록에서 점검 실행을 누르세요.")
    add("fingerprint", 10, 10 if ev and all(e.get("sha256") for e in ev) else 0, "Tamper-proof fingerprints (SHA-256)",
        "위변조 방지 지문 (SHA-256)", "Upload through Rentrail so each file is fingerprinted.", "Rentrail로 올리면 자동으로 지문이 남습니다.")
    if sub:
        s = db.one("SELECT * FROM sublets WHERE subtenant_id = ?", (user["id"],))
        paid = bool(s) and any(r["kind"] == "deposit_in" for r in ledger_rows(s["id"], user))
        add("escrow", 15, 15 if paid else 0, "Deposit held in Rentrail escrow", "보증금을 Rentrail 에스크로에 보관",
            "Pay the deposit into escrow, not to a person.", "보증금은 개인이 아니라 에스크로에 넣으세요.", "sublet")
    else:
        on_time = bool(base and start and parse_date(base["inspected_on"]) <= start + timedelta(days=2))
        done = on_time or bool(db.one("SELECT 1 FROM tasks_done WHERE user_id = ? AND task_key = 'inventory_form'", (user["id"],)))
        add("form48", 10, 10 if done else 0, "Recorded within 48 hours of move-in", "입주 48시간 안에 기록",
            "Late records are weaker evidence.", "늦은 기록은 증거력이 약합니다.")
        pol = next((db.loads(b["result"], {}) for b in db.q("SELECT * FROM bills WHERE user_id = ? AND kind = 'policy'", (user["id"],))
                    if b["result"] and clock.visible(b.get("issued_on"), user)), None)
        add("insurance", 5, 5 if pol and pol.get("requirement_met") else 0, "Renter's insurance meets the lease",
            "세입자 보험이 계약 요건 충족", "Upload your policy.", "보험 증권을 올리세요.", "bills")
    # Move-out phase (counts only within 30 days of the end, or after it)
    near_end = bool(end and (end - today).days <= 30)
    pc = latest_precheck(user)
    if not sub:
        add("precheck", 10, 10 if pc else 0, "Move-out precheck done (fix or pay)", "퇴거 전 진단 완료 (고칠까, 물어줄까)",
            "Run the precheck 2-4 weeks before you leave.", "떠나기 2~4주 전에 퇴거 전 진단을 받으세요.", "court",
            "now" if near_end else "later")
    if not sub:
        out_rec = any(r["kind"] == "move_out" and clock.visible(r["inspected_on"], user) for r in
                      db.q("SELECT kind, inspected_on FROM inspections WHERE user_id = ? AND sublet_id IS NULL", (user["id"],)))
        add("move_out", 10, 10 if out_rec else 0, "Move-out walkthrough recorded", "퇴거 점검 기록",
            "Film the same route as at move-in on your last day.", "마지막 날 입주 때와 같은 동선으로 찍으세요.",
            "inspections", "now" if (end and today >= end) else "later")
    active = [c for c in checks if c["phase"] == "now"]
    total = sum(c["points"] for c in active) or 1
    score = round(100 * sum(c["earned"] for c in active) / total)
    lvl = next(l for l in SHIELD_LEVELS if score >= l[0])
    return {"score": score, "level": lvl[1], "level_en": lvl[2], "level_ko": lvl[3], "checks": checks,
            "next": [c for c in active if not c["done"]][:2], "as_of": today.isoformat()}
