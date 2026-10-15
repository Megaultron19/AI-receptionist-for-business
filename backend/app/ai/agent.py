"""One customer turn: append their message, let the model call tools until it answers, persist."""
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..config import get_settings
from ..conversations.models import Conversation
from ..core.events import alert, integration_result, usage
from ..customers.models import Customer
from ..restaurant.service import get_restaurant
from . import prompt, tools
from .llm import LLMError, get_provider

log = logging.getLogger(__name__)
MAX_ROUNDS = 8


@dataclass
class Reply:
    text: str
    flags: dict
    ok: bool


def respond(db: Session, convo: Conversation, customer: Customer, user_text: str, *, channel: str) -> Reply:
    s = get_settings()
    r = get_restaurant(db)
    voice = channel == "voice"
    timeout = s.voice_llm_timeout_seconds if voice else s.llm_timeout_seconds
    ctx = tools.ToolContext(db=db, customer=customer, convo=convo, channel=channel)
    try:
        provider = get_provider()
        transcript = provider.add_user(list(convo.transcript), user_text)
        stable, specs = prompt.stable_prompt(r, channel), tools.specs(channel)
        turn = None
        for _ in range(MAX_ROUNDS):
            transcript, turn = provider.complete(system_stable=stable, system_dynamic=prompt.dynamic_prompt(db, r, convo, customer),
                                                 transcript=transcript, tools=specs, timeout=timeout, max_retries=0 if voice else 2)
            usage(db, "llm_input_tokens", turn.input_tokens, turn.input_tokens * s.cost_llm_per_1k_input_tokens_paise // 1000,
                  model=turn.model, channel=channel)
            usage(db, "llm_output_tokens", turn.output_tokens, turn.output_tokens * s.cost_llm_per_1k_output_tokens_paise // 1000,
                  model=turn.model, channel=channel)
            if turn.stop != "tool_use" or not turn.tool_calls:
                break
            results = [(c.id, *tools.run(ctx, c.name, c.input)) for c in turn.tool_calls]
            transcript = provider.add_tool_results(transcript, results)
        else:
            raise LLMError("tool loop did not finish")
    except LLMError as e:
        log.warning("AI unavailable for conversation %s: %s", convo.id, e)
        integration_result("llm", False, str(e))
        alert(db, "ai_unavailable", f"The AI receptionist couldn't answer a {channel} customer ({customer.phone}): {e}",
              severity="error", ref=("conversation", convo.id))
        return Reply("", ctx.flags, ok=False)
    integration_result("llm", True)
    if turn.stop == "refusal":
        text = "Sorry, I can't help with that. Is there anything else about the restaurant I can help you with?"
    elif turn.stop == "max_tokens" and not turn.text:
        text = "Sorry, could you say that again more briefly?"
    else:
        text = turn.text or ("Is there anything else I can help you with?" if not voice else "Anything else?")
    if transcript[-1]["role"] == "user":
        transcript.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
    convo.transcript = transcript
    if any("ऀ" <= ch <= "ॿ" for ch in text):
        convo.language = "hi-IN"
    return Reply(text, ctx.flags, ok=True)
