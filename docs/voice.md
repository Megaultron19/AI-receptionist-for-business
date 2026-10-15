# Phone calls

The call flow is provider-independent (`backend/app/voice/flow.py`); providers live in
`backend/app/voice/providers.py`. Two are included:

| Provider | Use for | Webhooks to configure |
|---|---|---|
| **Plivo** | Indian numbers (KYC required) | Application **Answer URL** `https://<DOMAIN>/voice/plivo/answer` (POST), **Hangup URL** `https://<DOMAIN>/voice/plivo/status` (POST) |
| **Twilio** | International numbers | Number → Voice → **A call comes in** `https://<DOMAIN>/voice/twilio/answer` (POST); **Call status changes** `https://<DOMAIN>/voice/twilio/status` (POST) |

Set `PLIVO_AUTH_ID`/`PLIVO_AUTH_TOKEN` or `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`. Every request is checked
against the provider signature (Plivo V3 / Twilio HMAC-SHA1) computed over `PUBLIC_BASE_URL` — it must be
exactly the public https URL the provider calls.

## How a call works
1. Greeting identifies the restaurant and that this is an AI assistant; "press 2 for Hindi".
2. Each turn uses the provider's speech recognition (speech or keypad; callers can interrupt the prompt).
3. The AI calls backend tools for availability, bookings, menu, orders and payments — it cannot invent them.
4. Payment links and confirmations go by WhatsApp **after the caller agrees**; without WhatsApp, Razorpay
   sends the payment link by SMS and bookings are confirmed verbally with the reference.
5. "Talk to a person" → transfer to the configured staff number; if nobody answers (or no number is set) a
   callback request appears in **Handoff & callbacks** and staff are alerted.
6. No speech twice → polite hang-up (outcome *abandoned*). AI timeout/outage → transfer or callback, plus
   an error alert. Unexpected errors never leave the caller in silence.
7. Status callback records duration and outcome (reservation / order / info / transferred / callback /
   abandoned / failed) in **Calls**, plus usage for cost estimates.

## Latency
Voice uses `ANTHROPIC_EFFORT=low` and a 9 s timeout (`VOICE_LLM_TIMEOUT_SECONDS`). Providers wait ~15 s
for a webhook response. Choose a server region close to India (e.g. Mumbai) to keep turns snappy.

## Limits and upgrade path
This uses the provider's turn-based speech gather (reliable, simple, supported by both providers). Fully
streaming, full-duplex voice (e.g. a Plivo/Twilio media stream + streaming STT/TTS) would feel more natural;
add it as another provider class without touching reservation or order logic.

Verify in each provider's sandbox before going live that the recognised-speech parameter arrives as
expected (`Speech` for Plivo GetInput, `SpeechResult` for Twilio Gather) — integration tests here simulate
both providers' requests but have not been run against their live APIs.
