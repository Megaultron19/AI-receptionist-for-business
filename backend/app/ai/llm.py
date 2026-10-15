"""Provider-independent LLM interface with structured tool calling.

The agent loop (agent.py) only sees ToolCall / Turn objects. Each provider owns its transcript format
(stored opaquely on the conversation) so provider-specific details — e.g. Claude's thinking blocks that
must be replayed verbatim — never leak into business code. Add a provider by implementing LLMProvider
and registering it in PROVIDERS.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..config import get_settings

log = logging.getLogger(__name__)


class LLMError(Exception):
    """Provider unavailable, timed out or misconfigured. Callers must fall back to a human path."""


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall]
    stop: str  # end | tool_use | refusal | max_tokens
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON-schema properties
    required: list[str] = field(default_factory=list)


class LLMProvider(Protocol):
    name: str

    def add_user(self, transcript: list[dict], text: str) -> list[dict]: ...

    def complete(self, *, system_stable: str, system_dynamic: str, transcript: list[dict], tools: list[ToolSpec],
                 timeout: float, max_retries: int) -> tuple[list[dict], Turn]: ...

    def add_tool_results(self, transcript: list[dict], results: list[tuple[str, str, bool]]) -> list[dict]: ...


class AnthropicProvider:
    """Claude via the official Anthropic SDK (Messages API, manual tool loop)."""
    name = "anthropic"
    # Models that accept the server-side refusal fallback in its "default" form.
    FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")

    def __init__(self):
        import anthropic
        s = get_settings()
        if not s.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=s.anthropic_api_key)
        self.model, self.effort = s.anthropic_model, s.anthropic_effort

    def add_user(self, transcript, text):
        return [*transcript, {"role": "user", "content": text}]

    def add_tool_results(self, transcript, results):
        return [*transcript, {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": cid, "content": content, **({"is_error": True} if err else {})}
            for cid, content, err in results]}]

    def complete(self, *, system_stable, system_dynamic, transcript, tools, timeout, max_retries):
        system = [{"type": "text", "text": system_stable, "cache_control": {"type": "ephemeral"}},
                  {"type": "text", "text": system_dynamic}]
        tool_defs = [{"name": t.name, "description": t.description, "strict": True,
                      "input_schema": {"type": "object", "properties": t.parameters,
                                       "required": t.required or list(t.parameters), "additionalProperties": False}}
                     for t in tools]
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if self.model in self.FALLBACK_MODELS else {}
        try:
            resp = self.client.with_options(timeout=timeout, max_retries=max_retries).beta.messages.create(
                model=self.model, max_tokens=4000, system=system, tools=tool_defs, messages=transcript,
                output_config={"effort": self.effort}, **extra)
        except self._anthropic.APIError as e:
            raise LLMError(f"{type(e).__name__}: {e}") from e
        # Keep every block verbatim (thinking included) so the transcript stays append-only and valid.
        transcript = [*transcript, {"role": "assistant", "content": [b.model_dump(mode="json", exclude_none=True) for b in resp.content]}]
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in resp.content if b.type == "tool_use"]
        text = " ".join(b.text for b in resp.content if b.type == "text").strip()
        stop = {"tool_use": "tool_use", "refusal": "refusal", "max_tokens": "max_tokens"}.get(resp.stop_reason, "end")
        return transcript, Turn(text, calls, stop, resp.usage.input_tokens, resp.usage.output_tokens, resp.model)


PROVIDERS = {"anthropic": AnthropicProvider}
_cache: dict[str, LLMProvider] = {}


def get_provider() -> LLMProvider:
    name = get_settings().llm_provider
    if name not in _cache:
        if name not in PROVIDERS:
            raise LLMError(f"unknown LLM provider {name!r}")
        _cache[name] = PROVIDERS[name]()
    return _cache[name]
