# Building a Zero-PII, Cryptographically Verified Incident Responder on Switch AI

*How I wired a two-room multi-agent workflow that scrubs customer data, reproduces the bug for real, verifies the model that diagnosed it, and refuses to roll back production without a human "yes".*

---

## The problem: AI agents in the incident channel are a liability

Every on-call engineer has lived this loop: a customer crash report lands in support, a Tier-1 rep pastes it into an engineering channel, and suddenly five AI coding agents have the customer's email, card number, and session token in their context windows. Then an agent proposes "just roll back" with no deterministic proof the bug is real and no evidence that the diagnosis came from the model you think it did.

SwitchGuard SRE is a proof of concept that fixes both problems with one declarative Switch AI template and four small CLI tools. It is deliberately boring where it matters: deterministic regex for PII, real pytest for reproduction, SHA-256 commitments for model integrity, and a hard human gate for the destructive action.

## The two-room design

The entire workflow is declared in `switchguard-sre.template.yaml`:

- **Room 1, `#alerts-intake`**: a single agent, `@airlock-triager`, with `addressing: anyone`. Humans can paste raw tickets here.
- **Room 2, `#incident-war-room`**: `@sre-repro` and `@release-commander`, both with `addressing: owner-agents`. External users cannot trigger shell-running agents directly.
- **One directional link** from Room 1 to Room 2. Only the sanitized payload crosses it.

That addressing split is the security boundary. The agent that reads untrusted text cannot run shell tools. The agents that run shell tools cannot be addressed by untrusted users.

## Step 1: The PII Airlock

`tools/airlock_scrub.py` calls `POST /api/v1/airlock/scrub`. The scrubber runs in a strict order so patterns cannot clobber each other:

1. Bearer / JWT / OpenAI-style secrets
2. 13-16 digit payment cards
3. SSNs
4. Emails
5. Prompt-injection phrases (`ignore previous instructions`, `system prompt`, `drop table`, `rm -rf /`, `developer mode`)

Every redaction is counted and stored with a SHA-256 hash of the raw payload, never the payload itself. The tool then synthesizes a fixture that can safely exercise the same code path:

```json
{
  "customer_email": "synth-user-89a@example.invalid",
  "card_number": "4111111111111111",
  "amount_cents": 4999,
  "discount_code": "SWITCH20"
}
```

`4111111111111111` passes the Luhn checksum, so the target service's validation path is real. The promo code is extracted from the raw report so the reproduction hits the same branch that crashed.

## Step 2: Reproduce for real

`tools/repro_checkout_500.py` is a pytest file the agent runs as-is:

```bash
python -m pytest tools/repro_checkout_500.py -v --tb=short
```

It posts the synthetic fixture to `POST /api/v1/checkout`. On the buggy `v2.14.0` build the endpoint performs an unguarded lookup for `discount_rate` and returns HTTP 500. On `v2.13.2` it returns 200. The script records the exit code and traceback against the incident, so the evidence is auditable rather than a chat message.

## Step 3: Verify the model, not just the words

This is the part most agent demos skip. `tools/flashprove_verify.py` verifies a proof bundle:

- The `model_name` must be in the approved commitment allowlist.
- The `weight_commitment_hash` must match the committed fingerprint.
- The `proof_sha256` must equal `SHA-256(weight_commitment_hash + ":" + diagnostic_claim)`.

A tampered bundle is still recorded, with `is_verified = 0` and a failure reason, before the API returns HTTP 422. That gives auditors an immutable tamper log instead of a silent 500.

Verify the valid bundle:

```bash
python tools/flashprove_verify.py \
  --incident-id inc_123 \
  --bundle fixtures/flashprove/valid_maverick_400b.json
```

A tampered bundle exits with code 2 and moves the incident to `BLOCKED_TAMPERED`.

## Step 4: Human-gated rollback

`POST /api/v1/admin/rollback` requires all of the following:

- `X-Admin-Token`
- `Idempotency-Key`
- `approved_by_human` set to a real handle
- `approval_chat_message` containing exactly `Approved. Roll back to v2.13.2`
- an `attestation_id` that resolves to `is_verified = 1`

`tools/rollback_release.py` then flips `runtime_config.active_version` to `v2.13.2`, re-runs the checkout probe to confirm HTTP 200, writes `postmortems/incident-postmortem.md`, and marks the incident `POSTMORTEM_PUBLISHED`.

## The Ops Console

`GET /dashboard` is a server-rendered HTML page with CSS variables from `design-tokens.json`. It shows the live version banner, PII scrubbed totals, FlashProve status, and the incident timeline. Every foreground/background pair is checked against WCAG 2.2 AA in the test suite, so the accessibility claim is computed, not asserted.

## What I would do next

- Real Anthropic FlashProve `cp_verify` binary integration behind the same `FLASHPROVE_BIN_PATH` toggle.
- Per-account rate limits instead of the current single global idempotency key.
- Room References wired to a real GitHub App so the blame step is automatic.

## Try it

```bash
git clone <repo>
cd switchguard-sre
python -m venv .venv && source .venv/bin/activate
pip install -e .
python -m pytest -v          # 34 passed
python scripts/simulate_customer_crash.py --run-pipeline
```

The simulator prints the raw crash ticket for Room 1 and, with `--run-pipeline`, walks the entire scrub -> repro -> verify -> rollback -> postmortem loop locally.

`#HowISwitch` — Switch AI made the room topology the security boundary, which is exactly what an incident tool needs.
