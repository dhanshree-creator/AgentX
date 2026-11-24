"""Structured API lookup: exchange rates (open.er-api.com, no key required).

Designed so the same agent loop could later drive a weather or inventory API;
only this module's internals would change.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent.exceptions import ToolExecutionError

MAX_STALE_S = 24 * 3600  # warn if the provider's rate is older than this
MAX_RESPONSE_BYTES = 2_000_000


class ApiLookupArgs(BaseModel):
    """Strict schema for api_lookup."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    base: str = Field(pattern=r"^[A-Za-z]{3}$")
    target: str = Field(pattern=r"^[A-Za-z]{3}$")


def _ts_utc(epoch: float | None = None) -> str:
    if epoch is None:
        epoch = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _fmt_rate(d: Decimal) -> str:
    """Round to 6 decimal places deterministically."""
    return str(d.quantize(Decimal("0.000001")))


class ApiLookupTool:
    """Registered tool: fetch a real exchange rate, return source/target/rate/timestamps."""

    name = "api_lookup"
    description = (
        "Fetch the current exchange rate between two ISO-4217 3-letter currency "
        "codes (e.g. base=USD, target=INR) from a live exchange-rate API."
    )
    parameters = {
        "type": "object",
        "properties": {
            "base": {
                "type": "string",
                "pattern": "^[A-Za-z]{3}$",
                "description": "Base currency code, e.g. USD",
            },
            "target": {
                "type": "string",
                "pattern": "^[A-Za-z]{3}$",
                "description": "Target currency code, e.g. INR",
            },
        },
        "required": ["base", "target"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        endpoint: str = "https://open.er-api.com/v6/latest",
        timeout_s: float = 15.0,
        stale_after_s: int = MAX_STALE_S,
    ):
        self._endpoint = endpoint.rstrip("/")
        self._timeout = timeout_s
        self._stale_after_s = stale_after_s

    def schema(self) -> dict[str, Any]:
        return self.parameters

    def args_model(self) -> type[BaseModel]:
        return ApiLookupArgs

    async def run(self, raw: dict[str, Any]) -> dict[str, Any]:
        base = str(raw.get("base") or "").strip().upper()[:8]
        target = str(raw.get("target") or "").strip().upper()[:8]
        try:
            args = ApiLookupArgs.model_validate({"base": base, "target": target})
        except ValidationError:
            raise ToolExecutionError(
                "Invalid api_lookup arguments: base and target must be 3-letter ISO currency codes."
            ) from None

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._endpoint}/{args.base}")
        except httpx.TimeoutException:
            raise ToolExecutionError(
                f"Exchange-rate API timed out after {self._timeout}s."
            ) from None
        except httpx.HTTPError as exc:
            raise ToolExecutionError(
                f"Exchange-rate network error: {type(exc).__name__}."
            ) from None

        if resp.status_code == 404:
            raise ToolExecutionError(f"Exchange-rate API has no data for base {args.base!r}.")
        if not 200 <= resp.status_code < 300:
            raise ToolExecutionError(f"Exchange-rate API error (HTTP {resp.status_code}).")
        if len(resp.content) > MAX_RESPONSE_BYTES:
            raise ToolExecutionError("Exchange-rate API response too large.")

        try:
            body = resp.json()
        except Exception:
            raise ToolExecutionError("Exchange-rate API returned malformed JSON.") from None

        rates = body.get("rates") or {}
        if not isinstance(rates, dict):
            raise ToolExecutionError("Exchange-rate API response has no usable 'rates' object.")
        rate_raw = rates.get(args.target)
        if rate_raw is None:
            raise ToolExecutionError(
                f"No rate available for {args.base}->{args.target}. Do not guess."
            )
        try:
            rate_dec = Decimal(str(rate_raw))
        except (InvalidOperation, TypeError, ValueError):
            raise ToolExecutionError("Exchange-rate API returned a non-numeric rate.") from None
        if not rate_dec.is_finite() or rate_dec <= 0:
            raise ToolExecutionError("Exchange-rate API returned an invalid rate value.")

        fetched_at = _ts_utc()
        updated_epoch = body.get("time_last_update_unix")
        updated_at = None
        stale = False
        if isinstance(updated_epoch, (int, float)):
            updated_at = _ts_utc(float(updated_epoch))
            stale = (time.time() - float(updated_epoch)) > self._stale_after_s

        return {
            "base": args.base,
            "target": args.target,
            "rate": _fmt_rate(rate_dec),
            "rate_number": str(rate_dec),
            "source": "open.er-api.com",
            "retrieved_at_utc": fetched_at,
            "provider_updated_at_utc": updated_at,
            "data_age_note": (
                "WARNING: provider rate may be stale (>24h since last provider update)."
                if stale
                else "Rate fetched live just now; provider timestamp included when available."
            ),
            "fee_note": (
                "Exchange providers may levy their own spread/fees not modelled here; "
                "any fee applied comes only from explicit user instruction."
            ),
        }
