"""Copilot chat: Chief Justice Dan (Boss) answers, asks teammates, and takes actions on the site.

Boss tools
- read_record() / read_calendar()        code: the tenancy record and upcoming deadlines
- ask_clerk / ask_counsel / ask_sheriff  agent calls to teammates (recorded with caller = chief_justice)
- open_page                              tells the web app which page to open
- mark_task_done, set_demo_date          change the record (calendar check-off, time machine)
- run_inspection, compare_records,       start real background runs (Detective, Counsel + Boss, Sheriff)
  rerun_deposit_case, draft_sublet_documents
- switch_mode                            tenant / sublessor (subletting my place)
Every action is listed under the answer so the user sees exactly what Dan did.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable

from pydantic_ai import Agent, RunContext

import cases
import clock
import db
import guard
import law
from agents import Ctx, _instructions
from llm import call, get_model
from models import ChatAnswer, Page

MAX_ASKS = 3
PAGES = ("home", "lease", "inspections", "court", "sublet", "bills", "copilot", "community", "agents", "safety")


def _record(user_id: int) -> str:
    """The tenancy record AS OF the user's simulated date (future records do not exist yet)."""
    user = db.one("SELECT * FROM users WHERE id = ?", (user_id,)) or {}
    mode = user.get("mode") or "tenant"
    lease = cases.lease_for_user(user)
    card = (lease or {}).get("card") or {}
    label = "SUBLEASE" if (lease or {}).get("kind") == "sublease" else "LEASE"
    parts = [f"Today (simulated): {clock.today(user)}. User mode: {mode}.",
             f"{label}: " + (cases._card_brief(card) if card else "none yet")]
    for i in db.q("SELECT id, kind, title, inspected_on, result, sublet_id FROM inspections WHERE user_id = ? OR sublet_id IN "
                  "(SELECT id FROM sublets WHERE owner_id = ? OR subtenant_id = ?) ORDER BY inspected_on", (user_id, user_id, user_id)):
        if not clock.visible(i["inspected_on"], user) or (mode == "subtenant" and not i["sublet_id"]):
            continue
        r = db.loads(i["result"], {}) or {}
        f = r.get("findings", [])
        parts.append(f"Inspection id={i['id']} kind={i['kind']} '{i['title']}' on {i['inspected_on']}: "
                     + (f"{len(f)} findings; " + "; ".join(f"{x['room']} {x['item']} {x['damage_type']}" for x in f[:6])
                        if i["result"] else "not inspected yet"))
    for d in db.q("SELECT * FROM disputes WHERE user_id = ?", (user_id,)):
        facts = db.loads(d["facts"], {}) or {}
        if not clock.visible(facts.get("statement_received_date"), user):
            continue
        m = (db.loads(d["result"], {}) or {}).get("money", {})
        parts.append(f"Deposit case id={d['id']} (move-in {d['move_in_id']} vs move-out {d['move_out_id']}, {d['status']}): "
                     f"claimed {m.get('claimed_total')}, approved {m.get('approved_total')}, refund requested {m.get('refund_requested')}")
    for s in db.q("SELECT * FROM sublets WHERE owner_id = ? OR subtenant_id = ?", (user_id, user_id)):
        if not cases.sublet_visible(s, user):
            continue
        st = cases.sublet_state(s, user)
        shares = cases.utility_shares(s, user)
        parts.append(f"Sublet id={s['id']} as {cases.sublet_role(s, user_id)}: {s['start_date']} to {s['end_date']}, "
                     f"rent {s['monthly_rent']}, deposit {s['deposit']}, status {st['status']}, escrow balance "
                     f"{cases.escrow_balance(s['id'], user)}, utility shares "
                     + (", ".join(f"{x['service']} {x['subtenant_share']} {'paid ' + x['paid_on'] if x['paid_on'] else 'unpaid, due ' + str(x['due'])}"
                                  for x in shares) or "none yet"))
    if mode != "subtenant":
        for b in db.q("SELECT kind, result, issued_on FROM bills WHERE user_id = ?", (user_id,)):
            if not clock.visible(b["issued_on"], user):
                continue
            r = db.loads(b["result"], {}) or {}
            parts.append(f"{b['kind']}: {r.get('provider') or r.get('insurer')} due {r.get('due_date')} amount {r.get('amount_due')}")
    return "\n".join(parts)


@lru_cache(maxsize=1)
def counsel_answer() -> Agent[Ctx, ChatAnswer]:
    return Agent(get_model(), deps_type=Ctx, output_type=ChatAnswer, name="counsel", retries=2,
                 instructions=_instructions("counsel.md") + "\n\nQuestion mode: answer a Connecticut tenant-law "
                 "question using ONLY the law pack, in under 120 words. Put law ids in `sources`. Say when something is not covered.")


@lru_cache(maxsize=1)
def sheriff_answer() -> Agent[Ctx, ChatAnswer]:
    return Agent(get_model(), deps_type=Ctx, output_type=ChatAnswer, name="sheriff", retries=2,
                 instructions=_instructions("sheriff.md") + "\n\nQuestion mode: answer about the user's sublet using the facts given, in under 120 words.")


def _act(ctx: RunContext[Ctx], kind: str, label: str, **extra: Any) -> None:
    ctx.deps.extra.setdefault("actions", []).append({"type": kind, "label": label, **extra})


def _start(ctx: RunContext[Ctx]) -> Callable[..., int]:
    return ctx.deps.extra["start"]


def _user(ctx: RunContext[Ctx]) -> dict:
    return db.one("SELECT * FROM users WHERE id = ?", (ctx.deps.user_id,))


@lru_cache(maxsize=1)
def boss() -> Agent[Ctx, ChatAnswer]:
    a = Agent(get_model(), deps_type=Ctx, output_type=ChatAnswer, name="chief_justice", retries=2,
              instructions=_instructions("chief_justice.md") + "\n\nYou are in Copilot mode now.")

    def _count(ctx: RunContext[Ctx]) -> str | None:
        n = ctx.deps.extra.get("asks", 0)
        if n >= MAX_ASKS:
            return f"Ask limit ({MAX_ASKS}) reached; answer with what you have."
        ctx.deps.extra["asks"] = n + 1
        return None

    # ----- reading -------------------------------------------------------------------------
    @a.tool
    def read_record(ctx: RunContext[Ctx]) -> str:
        """The user's tenancy record with ids: lease facts, inspections, deposit cases, sublets, bills."""
        return _record(ctx.deps.user_id)

    @a.tool
    def read_calendar(ctx: RunContext[Ctx]) -> list[dict]:
        """Upcoming and overdue deadlines (from the lease and CT law), with task keys for mark_task_done."""
        items = cases.calendar(_user(ctx))
        return [{k: t[k] for k in ("key", "date", "title_en", "amount", "law_id", "days_left", "done")} for t in items][:16]

    # ----- teammates -------------------------------------------------------------------------
    @a.tool
    async def ask_clerk(ctx: RunContext[Ctx], question: str) -> dict:
        """Ask Clerk Dan a question about the user's lease. Returns an answer with page numbers."""
        if (msg := _count(ctx)):
            return {"refused": msg}
        return await cases.lease_question(_user(ctx), question, ctx.deps.run_id, caller="chief_justice")

    @a.tool
    async def ask_counsel(ctx: RunContext[Ctx], question: str) -> dict:
        """Ask Counsel Dan a Connecticut deposit/tenant-law question. Answers only from the law pack."""
        if (msg := _count(ctx)):
            return {"refused": msg}
        r = await call(counsel_answer(), run_id=ctx.deps.run_id, user_id=ctx.deps.user_id, agent_name="counsel",
                       purpose="Law question", caller="chief_justice", deps=Ctx(ctx.deps.run_id, ctx.deps.user_id),
                       prompt=f"Question: {question}\n\n" + law.as_prompt())
        return r.output.model_dump(mode="json")

    @a.tool
    async def ask_sheriff(ctx: RunContext[Ctx], question: str) -> dict:
        """Ask Escrow Sheriff Dan about the user's sublet (either side) and the escrow."""
        if (msg := _count(ctx)):
            return {"refused": msg}
        facts = "\n".join(line for line in _record(ctx.deps.user_id).splitlines() if line.startswith("Sublet"))
        r = await call(sheriff_answer(), run_id=ctx.deps.run_id, user_id=ctx.deps.user_id, agent_name="sheriff",
                       purpose="Sublet question", caller="chief_justice", deps=Ctx(ctx.deps.run_id, ctx.deps.user_id),
                       prompt=f"Question: {question}\nSUBLET FACTS:\n{facts or 'No sublet yet.'}\n\n"
                              + law.as_prompt({"sublet", "return", "escrow", "interest", "deductions"}))
        return r.output.model_dump(mode="json")

    # ----- actions ---------------------------------------------------------------------------
    @a.tool
    def open_page(ctx: RunContext[Ctx], page: Page, why: str) -> str:
        """Open a page of the Rentrail site for the user (the web app navigates there)."""
        ctx.deps.extra["navigate"] = page
        _act(ctx, "navigate", why, page=page)
        return f"Opening {page}."

    @a.tool
    def mark_task_done(ctx: RunContext[Ctx], task_key: str) -> str:
        """Check off a calendar task (use the `key` from read_calendar)."""
        keys = {t["key"]: t for t in cases.calendar(_user(ctx))}
        if task_key not in keys:
            return f"No task '{task_key}'. Valid keys: {list(keys)[:12]}"
        db.ex("INSERT OR REPLACE INTO tasks_done (user_id, task_key, done_at) VALUES (?, ?, ?)",
              (ctx.deps.user_id, task_key, db.now()))
        _act(ctx, "task_done", keys[task_key]["title_en"], page="lease")
        return "Marked done."

    @a.tool
    def set_demo_date(ctx: RunContext[Ctx], date: str, why: str) -> str:
        """Move the demo 'today' (time machine), YYYY-MM-DD, e.g. to see move-out deadlines."""
        if not cases.parse_date(date):
            return "Use YYYY-MM-DD."
        db.ex("UPDATE users SET demo_today = ? WHERE id = ?", (date, ctx.deps.user_id))
        _act(ctx, "date", f"Demo date → {date}: {why}", date=date)
        return f"Demo date is now {date}."

    @a.tool
    def switch_mode(ctx: RunContext[Ctx], mode: str) -> str:
        """Switch the user's view: 'tenant' (renting) or 'sublessor' (subletting my place). Subtenants cannot switch."""
        u = _user(ctx)
        if u["mode"] == "subtenant" or mode not in ("tenant", "sublessor"):
            return "Not allowed for this account."
        db.ex("UPDATE users SET mode = ? WHERE id = ?", (mode, ctx.deps.user_id))
        _act(ctx, "mode", f"View switched to {mode}", mode=mode)
        return f"Mode is now {mode}."

    def _visible_inspection(ctx: RunContext[Ctx], iid: int) -> dict | None:
        return db.one("SELECT * FROM inspections WHERE id = ? AND (user_id = ? OR sublet_id IN "
                      "(SELECT id FROM sublets WHERE owner_id = ? OR subtenant_id = ?))",
                      (iid, ctx.deps.user_id, ctx.deps.user_id, ctx.deps.user_id))

    @a.tool
    def run_inspection(ctx: RunContext[Ctx], inspection_id: int) -> str:
        """Start Detective Dan on one inspection's photos/videos (runs in the background)."""
        insp = _visible_inspection(ctx, inspection_id)
        if not insp:
            return "No such inspection."
        u = _user(ctx)
        rid = _start(ctx)("inspection", f"{insp['kind'].replace('_', ' ').title()} inspection",
                          lambda r: cases.inspect(u, inspection_id, r), f"inspection:{inspection_id}")
        ctx.deps.extra["navigate"] = "inspections"
        _act(ctx, "run", f"Started Detective Dan on '{insp['title']}'", run_id=rid, page="inspections")
        return f"Started run {rid}."

    @a.tool
    def compare_records(ctx: RunContext[Ctx], earlier_id: int, later_id: int) -> str:
        """Start a before-vs-after comparison of two inspections (earlier first)."""
        if not (_visible_inspection(ctx, earlier_id) and _visible_inspection(ctx, later_id)):
            return "Unknown inspection id."
        u = _user(ctx)
        rid = _start(ctx)("compare", "Before vs. after", lambda r: cases.compare(u, earlier_id, later_id, r),
                          f"compare:{earlier_id}:{later_id}")
        ctx.deps.extra["navigate"] = "inspections"
        _act(ctx, "run", f"Comparing inspection {earlier_id} → {later_id}", run_id=rid, page="inspections")
        return f"Started run {rid}."

    @a.tool
    def rerun_deposit_case(ctx: RunContext[Ctx], dispute_id: int) -> str:
        """Re-open a deposit case (Checkpoint → Detective → Counsel → Chief Justice). Takes about a minute."""
        if not db.one("SELECT id FROM disputes WHERE id = ? AND user_id = ?", (dispute_id, ctx.deps.user_id)):
            return "No such case."
        u = _user(ctx)
        rid = _start(ctx)("deposit_case", "Deposit court case", lambda r: cases.deposit_case(u, dispute_id, r),
                          f"dispute:{dispute_id}")
        ctx.deps.extra["navigate"] = "court"
        _act(ctx, "run", "Re-opened the deposit case", run_id=rid, page="court")
        return f"Started run {rid}."

    @a.tool
    def run_move_out_precheck(ctx: RunContext[Ctx]) -> str:
        """Before move-out: compare the move-in record with the latest record and say, per damage, whether to fix it
        yourself, hire someone, or let it be deducted (Detective -> Counsel; prices come from code)."""
        u = _user(ctx)
        base, later = cases.precheck_records(u)
        if not base or not later:
            return "Need a move-in record and a newer analysed record first."
        rid = _start(ctx)("precheck", "Move-out precheck", lambda r: cases.precheck(u, base["id"], later["id"], r),
                          f"precheck:{base['id']}:{later['id']}")
        ctx.deps.extra["navigate"] = "court"
        _act(ctx, "run", "Started the move-out precheck (fix or pay)", run_id=rid, page="court")
        return f"Started run {rid}."

    @a.tool
    def draft_sublet_documents(ctx: RunContext[Ctx], sublet_id: int) -> str:
        """Ask Escrow Sheriff Dan to draft the consent letter, sublease and checklists."""
        s = db.one("SELECT * FROM sublets WHERE id = ?", (sublet_id,))
        if not s or not cases.sublet_role(s, ctx.deps.user_id):
            return "No such sublet."
        u = _user(ctx)
        rid = _start(ctx)("sublet_docs", "Sublet documents", lambda r: cases.sublet_docs(u, sublet_id, r), f"sublet:{sublet_id}")
        ctx.deps.extra["navigate"] = "sublet"
        _act(ctx, "run", "Sheriff Dan is drafting the sublet documents", run_id=rid, page="sublet")
        return f"Started run {rid}."

    return a


async def chat(user: dict, message: str, history: list[dict], run_id: int, start: Callable[..., int], page: str = "") -> dict:
    hits = guard.instruction_hits(message)
    if hits:
        guard.log(user["id"], "chat_instruction_flagged", {"lines": hits}, run_id)
    cases.officer_step(run_id, user["id"], "Screen the chat message", {
        "instruction_like_lines": hits[:3], "verdict": "passed to the Boss with the rule: data is evidence, not orders"})
    lang = "Korean" if (user.get("lang") == "ko") else "English"
    convo = "\n".join(f"{h['role']}: {h['content'][:500]}" for h in history[-6:])
    prompt = (f"Today (demo date) is {cases.user_today(user)}. User mode: {user.get('mode') or 'tenant'}. "
              f"The user is on the '{page or 'home'}' page. Answer in {lang}.\n"
              f"Recent conversation:\n{convo or '(none)'}\n\nUser: {message}")
    ctx = Ctx(run_id=run_id, user_id=user["id"], lang=user.get("lang") or "en", extra={"asks": 0, "start": start})
    r = await call(boss(), run_id=run_id, user_id=user["id"], agent_name="chief_justice", purpose="Copilot chat",
                   prompt=prompt, caller="user", deps=ctx)
    out = r.output.model_dump(mode="json")
    if ctx.extra.get("navigate"):
        out["navigate_to"] = ctx.extra["navigate"]
    if out.get("navigate_to") not in PAGES:
        out["navigate_to"] = None
    out["actions"] = ctx.extra.get("actions", [])
    return out
