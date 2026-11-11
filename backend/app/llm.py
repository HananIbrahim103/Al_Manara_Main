"""One gateway for every LLM call (OpenRouter, OpenAI-compatible).

Cheap models make mistakes, so every call:
  - asks for JSON and validates it against a Pydantic schema,
  - retries with the validation error fed back to the model,
  - is recorded in agent_runs: input, output, model, tokens, cost, time, attempts, errors.

LLM_MODE=mock (or no API key) skips the network and uses the caller's deterministic fallback,
so the whole system can be run and tested without spending anything.
"""
import asyncio
import json
import random
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.db import SessionLocal
from app.models import AgentRun

T = TypeVar("T", bound=BaseModel)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMFailure(Exception):
    """The model did not return valid output after every retry. Already recorded in agent_runs."""


def is_mock() -> bool:
    settings = get_settings()
    return settings.llm_mode.lower() == "mock" or not settings.openrouter_api_key


async def record_run(**fields: Any) -> None:
    """Write an agent_runs row in its own transaction, so the record survives a failed request."""
    async with SessionLocal() as session:
        session.add(AgentRun(**fields))
        await session.commit()


# Rate limits and brief provider outages: wait and try again instead of failing the test case at once.
_RETRY_STATUS = (429, 502, 503, 504)
RATE_LIMIT_ATTEMPTS = 4
MAX_WAIT_SECONDS = 20.0
_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def _shared_client() -> httpx.AsyncClient:
    """One HTTP client (one connection pool) for every call made on the running event loop."""
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client.is_closed or _client_loop is not loop:
        _client, _client_loop = httpx.AsyncClient(limits=httpx.Limits(max_connections=20)), loop
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed and _client_loop is asyncio.get_running_loop():
        await _client.aclose()
    _client = None


def _wait_seconds(response: httpx.Response, attempt: int) -> float:
    """The provider's Retry-After if it gives one, otherwise 1s, 2s, 4s..., with a little jitter; never longer than the cap."""
    try:
        wait = float(response.headers.get("retry-after", ""))
    except ValueError:
        wait = 2.0 ** attempt
    return min(max(wait, 0.0), MAX_WAIT_SECONDS) + random.uniform(0, 0.25)


async def chat(model: str, messages: list[dict], *, json_mode: bool = False, temperature: float = 0.0,
               max_tokens: int = 2000, timeout: float = 60.0) -> dict:
    """Raw OpenRouter call. Returns {content, prompt_tokens, completion_tokens, cost_usd}."""
    settings = get_settings()
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature,
                            "max_tokens": max_tokens, "usage": {"include": True}}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    client = _shared_client()
    for attempt in range(RATE_LIMIT_ATTEMPTS):
        response = await client.post(
            f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json=body, timeout=timeout,
        )
        if response.status_code not in _RETRY_STATUS or attempt == RATE_LIMIT_ATTEMPTS - 1:
            break
        await asyncio.sleep(_wait_seconds(response, attempt))
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(str(payload["error"]))
    usage = payload.get("usage") or {}
    return {
        "content": payload["choices"][0]["message"].get("content") or "",
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "cost_usd": float(usage.get("cost") or 0.0),
    }


async def call_json(
    *, agent: str, step: str, system: str, user: str, schema: type[T], mock: Callable[[], T],
    assessment_id: int | None = None, model: str | None = None, max_attempts: int = 3,
    log_input: dict | None = None,
) -> T:
    """Ask for JSON matching `schema`. Raises LLMFailure when every attempt fails."""
    started = time.perf_counter()
    log_input = log_input or {"system": system[:4000], "user": user[:12000]}

    if is_mock():
        result = mock()
        await record_run(agent=agent, step=step, assessment_id=assessment_id, input=log_input,
                         output=result.model_dump(), llm_model="mock", attempts=1,
                         duration_ms=int((time.perf_counter() - started) * 1000))
        return result

    model = model or get_settings().agent_model
    messages = [
        {"role": "system", "content": system + "\n\nReply with one JSON object only. JSON schema:\n"
                                      + json.dumps(schema.model_json_schema())},
        {"role": "user", "content": user},
    ]
    errors: list[str] = []
    tokens_in = tokens_out = 0
    cost = 0.0
    for attempt in range(1, max_attempts + 1):
        try:
            reply = await chat(model, messages, json_mode=True)
        except (httpx.HTTPError, RuntimeError, KeyError, IndexError) as exc:
            errors.append(f"attempt {attempt}: call failed: {exc!r}")
            continue
        tokens_in += reply["prompt_tokens"]
        tokens_out += reply["completion_tokens"]
        cost += reply["cost_usd"]
        try:
            result = schema.model_validate(json.loads(_FENCE.sub("", reply["content"].strip())))
        except (json.JSONDecodeError, ValidationError) as exc:
            errors.append(f"attempt {attempt}: invalid output: {str(exc)[:500]}")
            messages += [{"role": "assistant", "content": reply["content"]},
                         {"role": "user", "content": f"That was not valid. Error: {str(exc)[:800]}\nReply again with one corrected JSON object only."}]
            continue
        await record_run(agent=agent, step=step, assessment_id=assessment_id, input=log_input,
                         output=result.model_dump(), llm_model=model, prompt_tokens=tokens_in,
                         completion_tokens=tokens_out, cost_usd=cost, attempts=attempt,
                         error="; ".join(errors) or None,
                         duration_ms=int((time.perf_counter() - started) * 1000))
        return result

    await record_run(agent=agent, step=step, assessment_id=assessment_id, input=log_input, output={},
                     llm_model=model, prompt_tokens=tokens_in, completion_tokens=tokens_out, cost_usd=cost,
                     attempts=max_attempts, status="failed", error="; ".join(errors),
                     duration_ms=int((time.perf_counter() - started) * 1000))
    raise LLMFailure(f"{agent}/{step}: no valid output after {max_attempts} attempts")
