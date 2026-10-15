import json

import anthropic
import httpx2

from app.ai.llm import AnthropicProvider, LLMError, ToolSpec


def provider_with(handler):
    p = AnthropicProvider()
    p.client = anthropic.Anthropic(api_key="k", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    return p


def test_request_shape_and_verbatim_transcript():
    seen = {}

    def handler(req):
        seen["body"], seen["beta"] = json.loads(req.content), req.headers.get("anthropic-beta")
        return httpx2.Response(200, json={
            "id": "m1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "stop_reason": "tool_use",
            "stop_sequence": None, "usage": {"input_tokens": 1200, "output_tokens": 40},
            "content": [{"type": "thinking", "thinking": "", "signature": "sig"},
                        {"type": "tool_use", "id": "tu1", "name": "check_availability",
                         "input": {"date": "2026-10-20", "time": None, "party_size": 2}}]})

    p = provider_with(handler)
    t = p.add_user([], "table for 2?")
    t, turn = p.complete(system_stable="STABLE", system_dynamic="NOW", transcript=t,
                         tools=[ToolSpec("check_availability", "d", {"date": {"type": "string"}, "time": {"type": ["string", "null"]},
                                                                     "party_size": {"type": "integer"}})], timeout=5, max_retries=0)
    b = seen["body"]
    assert b["model"] == "claude-opus-5-5" and b["output_config"] == {"effort": "low"} and b["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in seen["beta"]
    assert b["system"][0]["cache_control"] == {"type": "ephemeral"} and b["system"][1]["text"] == "NOW"
    tool = b["tools"][0]
    assert tool["strict"] is True and tool["input_schema"]["additionalProperties"] is False
    assert tool["input_schema"]["required"] == ["date", "time", "party_size"]
    assert "thinking" not in b and "tool_choice" not in b  # Opus 5.5: adaptive thinking by default, no forced tools
    assert turn.stop == "tool_use" and turn.tool_calls[0].input["party_size"] == 2 and turn.input_tokens == 1200
    assert t[-1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "sig"}  # replayed verbatim
    t = p.add_tool_results(t, [("tu1", '{"free_times": ["19:00"]}', False)])
    assert t[-1]["content"][0]["tool_use_id"] == "tu1"


def test_api_errors_become_llm_error():
    p = provider_with(lambda req: httpx2.Response(529, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}))
    try:
        p.complete(system_stable="s", system_dynamic="d", transcript=[{"role": "user", "content": "hi"}], tools=[], timeout=2, max_retries=0)
    except LLMError as e:
        assert "busy" in str(e) or "Overloaded" in str(e) or "529" in str(e)
    else:
        raise AssertionError("expected LLMError")
