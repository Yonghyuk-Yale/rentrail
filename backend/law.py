"""Jurisdiction packs. Agents may only cite excerpt ids that exist in the active pack.

Adding a state = adding law/<STATE>.json with the same shape. Only Connecticut ships today.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache

from config import LAW_DIR


@lru_cache(maxsize=8)
def pack(state: str = "CT") -> dict:
    return json.loads((LAW_DIR / f"{state.lower()}.json").read_text(encoding="utf-8"))


def excerpt_ids(state: str = "CT") -> set[str]:
    return {e["id"] for e in pack(state)["excerpts"]}


def excerpt(eid: str, state: str = "CT") -> dict | None:
    return next((e for e in pack(state)["excerpts"] if e["id"] == eid), None)


def as_prompt(topics: set[str] | None = None, state: str = "CT") -> str:
    lines = [f"LAW PACK {pack(state)['name']} (v{pack(state)['version']}). Cite ONLY these ids."]
    for e in pack(state)["excerpts"]:
        if topics is None or e["topic"] in topics:
            lines.append(f"[{e['id']}] {e['cite']} — {e['title']}: {e['text']}")
    return "\n".join(lines)


def interest_rate(year: int, state: str = "CT") -> float:
    rates = pack(state)["deposit_rules"]["interest_rate_by_year"]
    return rates.get(str(year)) or rates[max(rates)]


def deposit_interest(amount: float, start: date, end: date, state: str = "CT") -> float:
    """Simple pro-rated interest at the published rate (good enough for a settlement preview)."""
    days = max(0, (end - start).days)
    return round(amount * interest_rate(start.year, state) * days / 365, 2)


def return_deadline(termination: date, forwarding_address_on: date | None, state: str = "CT") -> date:
    rules = pack(state)["deposit_rules"]
    a = termination + timedelta(days=rules["return_days_after_termination"])
    if forwarding_address_on is None:
        return a
    return max(a, forwarding_address_on + timedelta(days=rules["return_days_after_forwarding_address"]))
