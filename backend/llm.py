"""The model, the token meter, and the run recorder every agent goes through.

A *run* is one user task (analyse a lease, inspect a move-in, settle a sublet ...).
A run contains *agent calls*; each call is one PydanticAI agent run. For every call we store
who called whom, what was asked (masked preview), what came back, the exact token counts the
gateway reported (input, cached input, output), and the dollar cost. The Agent Room page and the
report's Tokenomics section read straight from these rows.
"""

from __future__ import annotations

import asyncio
import time
from functools import lru_cache
from typing import Any, Sequence

from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

import db
import guard
from config import MODEL_NAME, PORTKEY_BASE_URL, REQUEST_TIMEOUT, RUN_REQUEST_LIMIT, api_key
import os

# gpt-6-luna list prices, USD per 1M tokens (OpenAI pricing page, retrieved 2026-10-06, as used in
# Lecture 11). input_tokens already include cached tokens.
PRICE = {"input": 0.10, "cached_input": 0.01, "output": 0.50}
LONG_CONTEXT_TOKENS = 272_000
PRICE_LONG = {"input": 0.20, "cached_input": 0.02, "output": 0.75}


CALL_DEADLINE = 300.0  # seconds for one agent call, retries included


class ModelUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_model() -> OpenAIResponsesModel:
    configured = os.getenv("PORTKEY_MODEL") or MODEL_NAME
    if configured != MODEL_NAME:
        raise ModelUnavailable(f"PORTKEY_MODEL must be {MODEL_NAME} on the course key.")
    key = api_key()
    if not key:
        raise ModelUnavailable("PORTKEY_API_KEY was not found in .env (repo folder or the folder above it).")
    client = AsyncOpenAI(api_key=key, base_url=PORTKEY_BASE_URL,
                         default_headers={"x-portkey-api-key": key}, timeout=REQUEST_TIMEOUT)
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def cost_usd(input_tokens: int, cached: int, output_tokens: int) -> float:
    p = PRICE_LONG if input_tokens > LONG_CONTEXT_TOKENS else PRICE
    cached = min(cached, input_tokens)
    return ((input_tokens - cached) * p["input"] + cached * p["cached_input"] + output_tokens * p["output"]) / 1e6


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def start_run(user_id: int, kind: str, title: str, ref: str | None = None) -> int:
    return db.insert("runs", user_id=user_id, kind=kind, title=title, status="running",
                     started_at=db.now(), ref=ref)


def finish_run(run_id: int, error: str | None = None) -> None:
    db.ex("UPDATE runs SET status = ?, finished_at = ?, error = ? WHERE id = ?",
          ("failed" if error else "done", db.now(), error, run_id))


def _preview(parts: Sequence[Any] | str, limit: int = 1800) -> str:
    if isinstance(parts, str):
        text = parts
    else:
        chunks = []
        for p in parts:
            if isinstance(p, str):
                chunks.append(p)
            else:
                chunks.append(f"[image {getattr(p, 'identifier', '') or ''}]".replace(" ]", "]"))
        text = "\n".join(chunks)
    return text if len(text) <= limit else text[:limit] + f"\n… (+{len(text) - limit:,} chars)"


async def call(agent: Agent, *, run_id: int, user_id: int, agent_name: str, purpose: str,
               prompt: Sequence[Any] | str, caller: str = "user", deps: Any = None,
               message_history: list | None = None) -> Any:
    """Run one agent call under the budget guard and record it."""
    guard.check_budget(user_id, run_id)
    seq_row = db.one("SELECT COALESCE(MAX(seq), 0) + 1 AS s FROM agent_calls WHERE run_id = ?", (run_id,))
    call_id = db.insert("agent_calls", run_id=run_id, seq=seq_row["s"], agent=agent_name, caller=caller,
                        purpose=purpose, input_preview=_preview(prompt), status="running", created_at=db.now())
    started = time.perf_counter()
    limits = UsageLimits(request_limit=RUN_REQUEST_LIMIT, total_tokens_limit=guard.remaining_run_tokens(run_id))
    try:
        # A hard deadline for the whole call (all retries included), so a stalled gateway connection
        # fails the run with a clear error instead of leaving the page spinning.
        result = await asyncio.wait_for(
            agent.run(prompt, deps=deps, usage_limits=limits, message_history=message_history), CALL_DEADLINE)
    except Exception as exc:
        db.ex("UPDATE agent_calls SET status = ?, output = ?, ms = ? WHERE id = ?",
              ("failed", db.dumps({"error": f"{type(exc).__name__}: {str(exc)[:300]}"}),
               int((time.perf_counter() - started) * 1000), call_id))
        if "UsageLimitExceeded" in type(exc).__name__:
            guard.log(user_id, "budget_block", {"scope": "agent_call", "agent": agent_name, "detail": str(exc)[:200]}, run_id)
        raise
    usage = result.usage() if callable(result.usage) else result.usage
    tin, tcache, tout = usage.input_tokens or 0, usage.cache_read_tokens or 0, usage.output_tokens or 0
    cost = cost_usd(tin, tcache, tout)
    output = result.output
    out_json = output.model_dump(mode="json") if hasattr(output, "model_dump") else output
    db.ex("UPDATE agent_calls SET status = 'done', output = ?, input_tokens = ?, cached_tokens = ?, "
          "output_tokens = ?, requests = ?, cost_usd = ?, ms = ? WHERE id = ?",
          (db.dumps(out_json), tin, tcache, tout, usage.requests, cost,
           int((time.perf_counter() - started) * 1000), call_id))
    db.ex("UPDATE runs SET input_tokens = input_tokens + ?, cached_tokens = cached_tokens + ?, "
          "output_tokens = output_tokens + ?, cost_usd = cost_usd + ? WHERE id = ?",
          (tin, tcache, tout, cost, run_id))
    return result


def run_summary(run_id: int) -> dict | None:
    run = db.one("SELECT * FROM runs WHERE id = ?", (run_id,))
    if not run:
        return None
    calls = db.q("SELECT * FROM agent_calls WHERE run_id = ? ORDER BY seq", (run_id,))
    for c in calls:
        c["output"] = db.loads(c["output"], c["output"])
    run["calls"] = calls
    run["total_tokens"] = (run["input_tokens"] or 0) + (run["output_tokens"] or 0)
    return run
