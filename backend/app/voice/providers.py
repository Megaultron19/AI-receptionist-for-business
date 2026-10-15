"""Telephony providers. A provider verifies webhook signatures, normalises request parameters and renders
call-control XML. The call flow (flow.py) never sees provider specifics, so adding Exotel or a real-time
streaming provider means adding a class here."""
import base64
import hashlib
import hmac
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode
from xml.sax.saxutils import escape, quoteattr

from ..config import get_settings

INDIAN_VOICE = "Polly.Aditi"


@dataclass
class CallEvent:
    call_id: str
    from_number: str
    to_number: str
    speech: str = ""
    digits: str = ""
    status: str = ""
    duration: int = 0
    dial_status: str = ""


class Provider:
    name = ""
    speech_param = ""

    def verify(self, url: str, params: dict[str, str], headers) -> bool:
        raise NotImplementedError

    def event(self, p: dict[str, str]) -> CallEvent:
        raise NotImplementedError

    def _say(self, text: str, lang: str) -> str:
        tag = "Say" if self.name == "twilio" else "Speak"
        voice = f" voice={quoteattr(INDIAN_VOICE)}" if lang in ("en-IN", "hi-IN") else ""
        return f"<{tag} language={quoteattr(lang)}{voice}>{escape(text)}</{tag}>"

    @staticmethod
    def xml(body: str) -> str:
        return f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'

    def ask(self, text: str, lang: str, action: str, hints: str = "") -> str:
        raise NotImplementedError

    def hangup(self, text: str, lang: str) -> str:
        return self.xml(f"{self._say(text, lang)}<Hangup/>")

    def transfer(self, text: str, lang: str, number: str, action: str) -> str:
        raise NotImplementedError


class Twilio(Provider):
    name, speech_param = "twilio", "SpeechResult"

    def verify(self, url, params, headers):
        token = get_settings().twilio_auth_token
        if not token:
            return False
        payload = url + "".join(k + params[k] for k in sorted(params))
        expected = base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()
        return hmac.compare_digest(expected, headers.get("X-Twilio-Signature", ""))

    def event(self, p):
        return CallEvent(p.get("CallSid", ""), p.get("From", ""), p.get("To", ""), p.get("SpeechResult", ""), p.get("Digits", ""),
                         p.get("CallStatus", ""), int(p.get("CallDuration") or 0), p.get("DialCallStatus", ""))

    def ask(self, text, lang, action, hints=""):
        a = escape(action)
        hint = f" hints={quoteattr(hints)}" if hints else ""
        return self.xml(f'<Gather input="speech dtmf" numDigits="1" speechTimeout="auto" timeout="6" language={quoteattr(lang)}'
                        f'{hint} action="{a}" method="POST">{self._say(text, lang)}</Gather><Redirect method="POST">{a}</Redirect>')

    def transfer(self, text, lang, number, action):
        return self.xml(f'{self._say(text, lang)}<Dial action="{escape(action)}" method="POST" timeout="25">{escape(number)}</Dial>')


class Plivo(Provider):
    name, speech_param = "plivo", "Speech"

    def verify(self, url, params, headers):
        token = get_settings().plivo_auth_token
        nonce = headers.get("X-Plivo-Signature-V3-Nonce", "")
        if not token or not nonce:
            return False
        expected = plivo_signature(token, url, params, nonce)
        return any(hmac.compare_digest(expected, s.strip()) for s in headers.get("X-Plivo-Signature-V3", "").split(","))

    def event(self, p):
        return CallEvent(p.get("CallUUID", ""), p.get("From", ""), p.get("To", ""), p.get("Speech", ""), p.get("Digits", ""),
                         p.get("CallStatus", ""), int(p.get("Duration") or p.get("BillDuration") or 0), p.get("DialStatus", ""))

    def ask(self, text, lang, action, hints=""):
        a = escape(action)
        hint = f" hints={quoteattr(hints)}" if hints else ""
        return self.xml(f'<GetInput inputType="speech dtmf" numDigits="1" language={quoteattr(lang)}{hint} action="{a}" method="POST" '
                        f'executionTimeout="20" digitEndTimeout="4" speechEndTimeout="auto">{self._say(text, lang)}</GetInput>'
                        f'<Redirect method="POST">{a}</Redirect>')

    def transfer(self, text, lang, number, action):
        return self.xml(f'{self._say(text, lang)}<Dial action="{escape(action)}" method="POST" timeout="25">'
                        f'<Number>{escape(number.lstrip("+"))}</Number></Dial>')


def plivo_signature(token: str, url: str, params: dict[str, str], nonce: str) -> str:
    """X-Plivo-Signature-V3 for POST callbacks (same algorithm as plivo.utils.signature_v3)."""
    base, _, query = url.partition("?")
    base += "?"
    if query:
        base += "&".join(f"{k}={v}" for k, v in sorted(parse_qsl(query, keep_blank_values=True))) + "."
    base += "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), f"{base}.{nonce}".encode(), hashlib.sha256).digest()).decode()


PROVIDERS: dict[str, Provider] = {"twilio": Twilio(), "plivo": Plivo()}


def action_url(provider: str, path: str, **params) -> str:
    q = f"?{urlencode(params)}" if params else ""
    return f"{get_settings().public_base_url.rstrip('/')}/voice/{provider}/{path}{q}"
