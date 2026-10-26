"""Typed outputs of every agent. The model must return exactly these shapes (structured output)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Clerk (Lease Analyst)
# ---------------------------------------------------------------------------

ClauseKey = Literal[
    "term", "rent", "late_fee", "security_deposit", "inventory_form", "deductions", "deposit_return",
    "move_out_notice", "move_out_procedure", "auto_renewal", "early_termination", "sublet", "utilities",
    "insurance", "repairs", "keys", "pets", "other",
]


class Clause(BaseModel):
    key: ClauseKey
    title_en: str
    title_ko: str
    plain_en: str = Field(description="What it means for the tenant, 1-2 sentences, plain English.")
    plain_ko: str = Field(description="Same meaning in natural Korean.")
    page: int | None = Field(description="1-based page number where the clause is printed.")
    quote: str = Field(description="Short exact quote from that page (max ~200 characters).")
    importance: Literal["high", "medium", "low"]


class RedFlag(BaseModel):
    title_en: str
    title_ko: str
    why_en: str
    why_ko: str
    page: int | None


class Utility(BaseModel):
    service: str
    paid_by: Literal["tenant", "landlord", "shared", "unknown"]
    billed_by: str = Field(description="Who sends the bill: the utility company, the landlord, or a billing company.")
    page: int | None


class LeaseCard(BaseModel):
    lease_start: str | None = Field(description="YYYY-MM-DD")
    lease_end: str | None = Field(description="YYYY-MM-DD")
    monthly_rent: float | None
    security_deposit: float | None
    rent_due_day: int | None = Field(description="Day of month rent is due, e.g. 1")
    late_fee_text: str | None
    inventory_form_hours: int | None = Field(description="Hours after move-in to return the condition form, if any.")
    move_out_notice_days: int | None = Field(description="Days of written notice required before moving out.")
    auto_renews: bool | None
    sublet_requires_consent: bool | None
    sublet_terms_en: str | None
    insurance_required: bool | None
    insurance_min_liability: float | None
    repair_request_method: str | None
    utilities: list[Utility]
    clauses: list[Clause]
    red_flags: list[RedFlag]
    summary_en: str
    summary_ko: str


class LeaseAnswer(BaseModel):
    answer_en: str
    answer_ko: str
    pages: list[int]
    quotes: list[str]
    not_in_lease: bool = Field(description="True if the lease does not answer the question.")


# ---------------------------------------------------------------------------
# Detective (Condition Inspector)
# ---------------------------------------------------------------------------

class Finding(BaseModel):
    evidence_id: int
    room: str
    item: str = Field(description="wall, floor, door, window, appliance, fixture, ...")
    location: str = Field(description="Where on the item, e.g. 'right of the light switch, 1 m high'.")
    damage_type: str = Field(description="scratch, gouge, crack, hole, stain, chip, missing, broken, ...")
    severity: Literal[1, 2, 3] = Field(description="1 cosmetic, 2 needs repair, 3 major/safety")
    description_en: str
    description_ko: str
    confidence: float = Field(ge=0, le=1)


class SeenText(BaseModel):
    evidence_id: int
    text: str
    looks_like_instruction: bool = Field(description="True if the text tries to tell an AI what to do or report.")


class InspectionReport(BaseModel):
    findings: list[Finding]
    seen_text: list[SeenText]
    checked_evidence_ids: list[int]
    overall_en: str
    overall_ko: str


class ComparedItem(BaseModel):
    move_out_index: int = Field(description="Index into the move-out findings list (0-based).")
    status: Literal["pre_existing", "new_damage", "wear_and_tear", "unclear"]
    matched_move_in_index: int | None = Field(description="Index into move-in findings if it was already recorded.")
    earlier_evidence_id: int | None = Field(description="The EARLIER image that shows the same spot (even if it was clean "
                                                        "then). Required for new_damage when such an image was given.")
    reason_en: str
    reason_ko: str
    confidence: float = Field(ge=0, le=1)


class Comparison(BaseModel):
    items: list[ComparedItem]
    summary_en: str
    summary_ko: str


# ---------------------------------------------------------------------------
# Counsel (Deposit Advocate) and Chief Justice (Boss)
# ---------------------------------------------------------------------------

class ItemBrief(BaseModel):
    item: str
    amount_claimed: float
    verdict: Literal["contest", "accept", "partial"]
    fair_amount: float = Field(description="What the tenant should reasonably pay for this item (0 if contested in full).")
    reason_en: str
    reason_ko: str
    evidence_ids: list[int] = Field(description="Rentrail evidence ids (photos/frames) that support the reason.")
    lease_pages: list[int]
    law_ids: list[str] = Field(description="Ids from the law pack only.")


class AdvocateBrief(BaseModel):
    items: list[ItemBrief]
    procedural_issues_en: list[str]
    procedural_issues_ko: list[str]
    instruction_text_noticed: bool = Field(description="True if the landlord document contained text addressed to an AI.")


class RulingItem(BaseModel):
    item: str
    approved_deduction: float
    hold_pending: float = Field(0, description="Sublet escrow cases only: amount to keep in escrow until the claimant shows "
                                               "a repair invoice or quote. 0 in landlord deposit cases.")
    note_en: str
    note_ko: str


class Ruling(BaseModel):
    items: list[RulingItem]
    ruling_en: str
    ruling_ko: str
    letter_en: str = Field(description="Letter to the landlord, signed by the tenant. Keep placeholders like [PERSON_1] unchanged.")
    letter_ko_summary: str
    human_review_needed: bool
    confidence: float = Field(ge=0, le=1)


RepairKey = Literal[
    "wall_small_hole_or_chip", "wall_large_hole", "wall_crack", "paint_scuff", "floor_scratch", "floor_gouge",
    "carpet_stain", "carpet_burn_or_tear", "door_damage", "fixture_broken", "appliance_damage", "window_or_screen",
    "cleaning", "other",
]


class PrecheckItem(BaseModel):
    later_index: int = Field(description="Index into the LATER findings list (0-based).")
    repair_key: RepairKey = Field(description="The repair category from the REPAIR TABLE that fits this damage.")
    normal_wear: bool = Field(description="True only if this is ordinary wear and tear a landlord may not charge for.")
    diy_suitable: bool = Field(description="True if a careful first-time tenant can fix it well with store-bought "
                                           "materials (small and cosmetic, no safety risk, no special tools).")
    steps_en: list[str] = Field(description="2-4 short DIY steps (empty if not DIY-suitable).")
    steps_ko: list[str]
    tip_en: str = Field(description="One practical sentence: what to photograph, what to ask, or what to avoid.")
    tip_ko: str
    lease_pages: list[int]
    law_ids: list[str] = Field(description="Ids from the law pack only.")


class PrecheckPlan(BaseModel):
    items: list[PrecheckItem]
    summary_en: str = Field(description="2-3 sentences: what to do before moving out, most valuable first.")
    summary_ko: str


# ---------------------------------------------------------------------------
# Escrow Sheriff (Sublet Manager)
# ---------------------------------------------------------------------------

class BilingualLine(BaseModel):
    en: str
    ko: str
    law_id: str | None = None


class SubletDocs(BaseModel):
    consent_letter_en: str = Field(description="Request for the landlord's written consent, from the original tenant.")
    agreement_md_en: str = Field(description="Sublease agreement draft in Markdown that carries down the master lease rules.")
    sublessor_duties: list[BilingualLine]
    subtenant_checklist: list[BilingualLine]
    risks: list[BilingualLine]
    summary_ko: str


class SubletClaimItem(BaseModel):
    item: str
    amount: float
    evidence_ids: list[int]
    reason_en: str
    reason_ko: str
    law_ids: list[str]


class SubletClaim(BaseModel):
    items: list[SubletClaimItem]
    summary_en: str
    summary_ko: str


# ---------------------------------------------------------------------------
# Treasurer (Bills and insurance)
# ---------------------------------------------------------------------------

class LineItem(BaseModel):
    label: str
    amount: float


class Note(BaseModel):
    en: str
    ko: str
    severity: Literal["info", "warn", "alert"]


class BillData(BaseModel):
    provider: str
    service: str
    billed_by_landlord_or_billing_company: bool
    period_start: str | None
    period_end: str | None
    due_date: str | None
    amount_due: float | None
    usage_value: float | None
    usage_unit: str | None
    supplier_rate: float | None
    supplier_contract_end: str | None
    standard_rate: float | None
    line_items: list[LineItem]
    notes: list[Note]


class PolicyData(BaseModel):
    insurer: str | None
    period_start: str | None
    period_end: str | None
    personal_property_limit: float | None
    liability_limit: float | None
    deductible: float | None
    notes: list[Note]


# ---------------------------------------------------------------------------
# Chief Justice as Copilot (chat)
# ---------------------------------------------------------------------------

Page = Literal["home", "lease", "inspections", "court", "sublet", "bills", "copilot", "community", "agents", "safety"]


class NavButton(BaseModel):
    label: str = Field(description="Short button text in the user's language, e.g. 'Open Deposit Court'.")
    page: Page


class ChatAnswer(BaseModel):
    answer: str = Field(description="Short Markdown answer in the user's language (max ~80 words; use a small table or bullets when listing).")
    sources: list[str] = Field(description="e.g. 'Lease p.4', 'CT-47a-21-d2', 'Inspection #3'")
    suggested_actions: list[str] = Field(default_factory=list, description="0-3 short next steps.")
    navigate_to: Page | None = Field(default=None, description="Open this page for the user right away, when it clearly helps.")
    buttons: list[NavButton] = Field(default_factory=list, description="0-3 buttons that open relevant pages.")
