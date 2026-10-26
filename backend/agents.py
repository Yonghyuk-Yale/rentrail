"""The bulldog bench: who each agent is, what it returns, and the checks on its answers.

Six AI agents (all gpt-6-luna). In front of all of them stands the Checkpoint (guard.py): not an agent,
an always-on inspection gate in plain code that every input passes before any AI reads it.
Every agent gets the shared team rules + its own role prompt (prompts/*.md).
Output validators reject answers that cite evidence, pages, or laws that do not exist; the model
then gets one or two chances to fix its answer (ModelRetry).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext

import law
from config import PROMPTS_DIR
from llm import get_model
from models import (
    AdvocateBrief, BillData, ChatAnswer, Comparison, InspectionReport, LeaseAnswer, LeaseCard, PolicyData,
    PrecheckPlan, Ruling, SubletClaim, SubletDocs,
)

ROSTER = [
    {"id": "chief_justice", "name": "Chief Justice Dan", "name_ko": "대법관 댄", "costume": "judge", "color": "#4f46e5",
     "role_en": "Boss: plans the team's work, makes final rulings, answers in Copilot chat",
     "role_ko": "보스: 팀의 일을 나누고, 최종 판결을 내리고, 코파일럿 대화에 답합니다", "llm": True},
    {"id": "clerk", "name": "Clerk Dan", "name_ko": "서기관 댄", "costume": "clerk", "color": "#3b82f6",
     "role_en": "Lease Analyst: turns the lease into a Lease Card with page citations",
     "role_ko": "계약서 분석: 계약서를 쪽수가 달린 계약서 카드로 정리합니다", "llm": True},
    {"id": "detective", "name": "Detective Dan", "name_ko": "형사 댄", "costume": "detective", "color": "#f97316",
     "role_en": "Condition Inspector: finds damage in photos and video frames, compares before vs. after",
     "role_ko": "상태 점검: 사진과 영상 장면에서 하자를 찾고 전후를 비교합니다", "llm": True},
    {"id": "counsel", "name": "Counsel Dan", "name_ko": "변호사 댄", "costume": "lawyer", "color": "#a855f7",
     "role_en": "Deposit Advocate: reviews each deduction against evidence, lease, and CT law",
     "role_ko": "보증금 변호: 공제 항목을 증거·계약서·CT 법과 대조합니다", "llm": True},
    {"id": "sheriff", "name": "Escrow Sheriff Dan", "name_ko": "보안관 댄", "costume": "sheriff", "color": "#eab308",
     "role_en": "Sublet Manager: consent letter, sublease draft, escrow claims for both sides",
     "role_ko": "서브렛 관리: 동의 레터, 서브렛 계약서, 양쪽을 위한 에스크로 정산", "llm": True},
    {"id": "treasurer", "name": "Treasurer Dan", "name_ko": "회계관 댄", "costume": "treasurer", "color": "#22c55e",
     "role_en": "Bills & insurance: reads bills and policies, checks them against the lease",
     "role_ko": "고지서·보험: 고지서와 보험 증권을 읽고 계약서와 대조합니다", "llm": True},
    # Not an agent: the always-on inspection gate. Kept in the roster (id "officer") so run traces can show it.
    {"id": "officer", "name": "Checkpoint", "name_ko": "검문소", "costume": "gate", "color": "#00356b",
     "role_en": "Inspection gate (plain code, no AI): every input passes here first - hidden-text and injection "
                "screening, GPS/face/personal-data filters, token limits. The Boss cannot call or skip it.",
     "role_ko": "검문소 (AI 없는 코드): 모든 입력이 먼저 지나가는 관문 — 숨은 글씨·인젝션 차단, GPS·얼굴·개인정보 필터, "
                "토큰 한도. 보스가 부르거나 건너뛸 수 없습니다.", "llm": False},
]
NAMES = {r["id"]: r["name"] for r in ROSTER}


@dataclass
class Ctx:
    """What tools and validators can see during one agent call."""

    run_id: int
    user_id: int
    lang: str = "en"
    evidence_ids: set[int] = field(default_factory=set)
    page_count: int = 0
    max_claims: dict[str, float] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


def _instructions(prompt_file: str) -> str:
    shared = (PROMPTS_DIR / "shared_rules.md").read_text(encoding="utf-8")
    own = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
    return shared + "\n\n---\n\n" + own


def _check_pages(ctx: RunContext[Ctx], pages: list[int | None]) -> None:
    bad = [p for p in pages if p is not None and ctx.deps.page_count and not (1 <= p <= ctx.deps.page_count)]
    if bad:
        raise ModelRetry(f"Page numbers {bad} do not exist; the lease has {ctx.deps.page_count} pages.")


def _check_evidence(ctx: RunContext[Ctx], ids: list[int]) -> None:
    bad = sorted({i for i in ids if i not in ctx.deps.evidence_ids})
    if bad and ctx.deps.evidence_ids:
        raise ModelRetry(f"Evidence ids {bad} do not exist. Valid ids: {sorted(ctx.deps.evidence_ids)}.")


def _check_law(ids: list[str]) -> None:
    valid = law.excerpt_ids()
    bad = sorted({i for i in ids if i not in valid})
    if bad:
        raise ModelRetry(f"Law ids {bad} are not in the law pack. Use only: {sorted(valid)}.")


def _make(name: str, prompt_file: str, output_type: Any, retries: int = 2) -> Agent[Ctx, Any]:
    agent = Agent(get_model(), deps_type=Ctx, output_type=output_type, name=name, retries=retries,
                  instructions=_instructions(prompt_file))
    return agent


# ---------------------------------------------------------------------------
# Clerk
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def clerk_card() -> Agent[Ctx, LeaseCard]:
    a = _make("clerk", "clerk.md", LeaseCard)

    @a.output_validator
    def _v(ctx: RunContext[Ctx], out: LeaseCard) -> LeaseCard:
        _check_pages(ctx, [c.page for c in out.clauses] + [r.page for r in out.red_flags] + [u.page for u in out.utilities])
        if not out.clauses:
            raise ModelRetry("List the important clauses with page numbers.")
        return out
    return a


@lru_cache(maxsize=1)
def clerk_answer() -> Agent[Ctx, LeaseAnswer]:
    a = _make("clerk", "clerk.md", LeaseAnswer)

    @a.output_validator
    def _v(ctx: RunContext[Ctx], out: LeaseAnswer) -> LeaseAnswer:
        _check_pages(ctx, out.pages)
        return out
    return a


# ---------------------------------------------------------------------------
# Detective
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def detective_inspect() -> Agent[Ctx, InspectionReport]:
    a = _make("detective", "detective.md", InspectionReport)

    @a.output_validator
    def _v(ctx: RunContext[Ctx], out: InspectionReport) -> InspectionReport:
        _check_evidence(ctx, [f.evidence_id for f in out.findings] + [t.evidence_id for t in out.seen_text])
        return out
    return a


@lru_cache(maxsize=1)
def detective_compare() -> Agent[Ctx, Comparison]:
    a = _make("detective", "detective.md", Comparison)

    @a.output_validator
    def _v(ctx: RunContext[Ctx], out: Comparison) -> Comparison:
        n_out = ctx.deps.extra.get("n_later", 0)
        n_in = ctx.deps.extra.get("n_earlier", 0)
        seen = set()
        for it in out.items:
            if not (0 <= it.move_out_index < n_out):
                raise ModelRetry(f"move_out_index {it.move_out_index} is out of range 0..{n_out - 1}.")
            if it.matched_move_in_index is not None and not (0 <= it.matched_move_in_index < n_in):
                raise ModelRetry(f"matched_move_in_index {it.matched_move_in_index} is out of range 0..{n_in - 1}.")
            allowed = ctx.deps.extra.get("earlier_ids", set())
            if it.earlier_evidence_id is not None and allowed and it.earlier_evidence_id not in allowed:
                raise ModelRetry(f"earlier_evidence_id {it.earlier_evidence_id} is not an EARLIER image. Use one of {sorted(allowed)}.")
            seen.add(it.move_out_index)
        missing = sorted(set(range(n_out)) - seen)
        if missing:
            raise ModelRetry(f"Classify every later finding; missing indexes {missing}.")
        return out
    return a


# ---------------------------------------------------------------------------
# Counsel and Chief Justice
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def counsel_brief() -> Agent[Ctx, AdvocateBrief]:
    a = _make("counsel", "counsel.md", AdvocateBrief)

    @a.output_validator
    def _v(ctx: RunContext[Ctx], out: AdvocateBrief) -> AdvocateBrief:
        for it in out.items:
            _check_evidence(ctx, it.evidence_ids)
            _check_pages(ctx, it.lease_pages)
            _check_law(it.law_ids)
            if it.fair_amount < 0 or it.fair_amount > it.amount_claimed + 0.01:
                raise ModelRetry(f"fair_amount for '{it.item}' must be between 0 and the claimed {it.amount_claimed}.")
        return out
    return a


@lru_cache(maxsize=1)
def counsel_precheck() -> Agent[Ctx, PrecheckPlan]:
    a = _make("counsel", "counsel.md", PrecheckPlan)

    @a.output_validator
    def _v(ctx: RunContext[Ctx], out: PrecheckPlan) -> PrecheckPlan:
        n = ctx.deps.extra.get("n_later", 0)
        seen = set()
        for it in out.items:
            if not 0 <= it.later_index < n:
                raise ModelRetry(f"later_index {it.later_index} is out of range 0..{n - 1}.")
            seen.add(it.later_index)
            _check_pages(ctx, it.lease_pages)
            _check_law(it.law_ids)
            if it.diy_suitable and not it.steps_en:
                raise ModelRetry(f"Give DIY steps for later_index {it.later_index}, or set diy_suitable false.")
        missing = sorted(set(range(n)) - seen)
        if missing:
            raise ModelRetry(f"Plan every later finding; missing indexes {missing}.")
        return out
    return a


@lru_cache(maxsize=1)
def chief_ruling() -> Agent[Ctx, Ruling]:
    a = _make("chief_justice", "chief_justice.md", Ruling)

    @a.output_validator
    def _v(ctx: RunContext[Ctx], out: Ruling) -> Ruling:
        for it in out.items:
            cap = ctx.deps.max_claims.get(it.item.strip().lower())
            if it.approved_deduction < 0:
                raise ModelRetry("approved_deduction cannot be negative.")
            if it.hold_pending < 0:
                raise ModelRetry("hold_pending cannot be negative.")
            if cap is not None and it.approved_deduction + it.hold_pending > cap + 0.01:
                raise ModelRetry(f"'{it.item}': approved + held ({it.approved_deduction + it.hold_pending}) is above the claimed {cap}.")
        return out
    return a


# ---------------------------------------------------------------------------
# Sheriff and Treasurer
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def sheriff_docs() -> Agent[Ctx, SubletDocs]:
    a = _make("sheriff", "sheriff.md", SubletDocs)

    @a.output_validator
    def _v(ctx: RunContext[Ctx], out: SubletDocs) -> SubletDocs:
        _check_law([x.law_id for x in out.sublessor_duties + out.subtenant_checklist + out.risks if x.law_id])
        return out
    return a


@lru_cache(maxsize=1)
def sheriff_claim() -> Agent[Ctx, SubletClaim]:
    a = _make("sheriff", "sheriff.md", SubletClaim)

    @a.output_validator
    def _v(ctx: RunContext[Ctx], out: SubletClaim) -> SubletClaim:
        for it in out.items:
            _check_evidence(ctx, it.evidence_ids)
            _check_law(it.law_ids)
            if it.amount < 0:
                raise ModelRetry("Amounts cannot be negative.")
        return out
    return a


@lru_cache(maxsize=1)
def treasurer_bill() -> Agent[Ctx, BillData]:
    return _make("treasurer", "treasurer.md", BillData)


@lru_cache(maxsize=1)
def treasurer_policy() -> Agent[Ctx, PolicyData]:
    return _make("treasurer", "treasurer.md", PolicyData)


# ---------------------------------------------------------------------------
# Copilot (Chief Justice with tools) — built in copilot.py so tools can import cases
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def chief_chat() -> Agent[Ctx, ChatAnswer]:
    return _make("chief_justice", "chief_justice.md", ChatAnswer)
