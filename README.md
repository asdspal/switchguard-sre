# SwitchGuard SRE: Zero-PII Incident Triage, Live Repro & FlashProve-Verified Rollback on Switch AI

> **Built for the Flip the Switch Hackathon (Track 01: Best Business Workflow)**

**SwitchGuard SRE** solves the two biggest blockers preventing engineering teams from putting AI coding agents (`Claude Code`, `Codex`, `OpenCode`) into live incident channels:

1. **Customer PII Context Leakage**: When Tier-1 support escalates a customer crash report into an engineering channel, raw emails, payment cards, SSNs, and JWTs get pooled into every coding agent's context window.
2. **Unverified Autonomous Rollbacks**: Agents propose rollbacks without deterministic bug reproduction or cryptographic proof that the root-cause diagnosis came from an untampered frontier model.

---

## How Switch AI Is Central to SwitchGuard SRE (30% Rubric Mapping)

SwitchGuard SRE cannot function as a 1-on-1 terminal chatbot. It relies on **5 core Switch AI primitives**:

| Switch Primitive | How SwitchGuard SRE Uses It | File / Config |
| :--- | :--- | :--- |
| **1. Declarative Multi-Room Links (`group + rooms + links`)** | Atomically provisions `#alerts-intake` (Tier-1) and `#incident-war-room` (Tier-2) connected by a directional airlock link. | `switchguard-sre.template.yaml` |
| **2. Addressing Isolation (`anyone` vs. `owner-agents`)** | `@airlock-triager` (`addressing: anyone`) accepts raw human tickets in Room 1, while `@sre-repro` and `@release-commander` (`addressing: owner-agents`) in Room 2 can *only* be triggered by trusted agent handoffs. | `switchguard-sre.template.yaml` |
| **3. Room Instructions** | Pre-briefs every agent joining `#alerts-intake` and `#incident-war-room` on zero-PII boundaries and required approval phrases. | `switchguard-sre.template.yaml` |
| **4. Room References** | Attaches repository commit history so `@sre-repro` correlates the `HTTP 500 KeyError: 'discount_rate'` crash to release `v2.14.0`. | Room Reference |
| **5. Room Documents** | After human-approved rollback, `@release-commander` writes `incident-postmortem.md` (with the **Anthropic FlashProve** cryptographic receipt) into Switch Room Documents. | `tools/rollback_release.py` |

---

## Architecture Flow

```text
[ROOM 1: #alerts-intake]
  Human pastes raw ticket (Email + Visa Card + Bearer JWT + 500 Error)
        │
        ▼
  @airlock-triager (addressing: anyone)
    ├─ Runs `tools/airlock_scrub.py` -> Redacts 100% of PII & prompt injections
    ├─ Synthesizes Luhn-valid test card (`4111111111111111`) & safe email
    └─ Routes ONLY zero-PII packet across Switch Room Link ──┐
                                                             │
[ROOM 2: #incident-war-room] <─────────────────────────────┘
  @sre-repro (Claude Code / OpenCode, addressing: owner-agents)
    ├─ Checks Repo Reference -> Identifies offending commit `v2.14.0`
    ├─ Runs `pytest tools/repro_checkout_500.py` against live `cart-service` (:8090)
    └─ Posts exact HTTP 500 traceback & hands off to @release-commander
        │
        ▼
  @release-commander (addressing: owner-agents)
    ├─ Runs `tools/flashprove_verify.py` (Anthropic FlashProve v0.16.0 CPU check)
    │  verifying committed model weight hash (`0x8f4d...`) & soundness (`q/2^124 + 2^-101`)
    ├─ Stages rollback `v2.14.0 -> v2.13.2` & HALTS in `PENDING_APPROVAL`
        │
        ▼
  Human SRE replies: "@release-commander Approved. Roll back to v2.13.2"
    ├─ Runs `tools/rollback_release.py` -> Restores `v2.13.2` (`HTTP 200 OK`)
    └─ Publishes `incident-postmortem.md` to Switch Room Documents
```

---

## 3-Command Quickstart (Clone & Reproduce in <2 Minutes)

### 1. Install & Run the 34 Automated Tests
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
python -m pytest -v
# Expected: 34 passed
```

### 2. Start the Target `cart-service` & SwitchGuard Ops Console (`:8090`)
```bash
# Option A: Via Uvicorn
uvicorn demo_app.main:app --host 0.0.0.0 --port 8090

# Option B: Via Docker Compose
docker compose up --build -d
```
Open **`http://localhost:8090/dashboard`** to view the WCAG 2.2 AA SwitchGuard Ops Console.

### 3. Simulate an Outage & Run with Switch Console
```bash
# Prints the raw customer crash ticket for Room 1 (or pass --run-pipeline to test full CLI flow)
python scripts/simulate_customer_crash.py --run-pipeline
```

To run inside **Switch Console**:
1. Open Switch Console and click **New from Template** -> Select **`switchguard-sre.template.yaml`**.
2. Paste the raw crash ticket from `simulate_customer_crash.py` into **`#alerts-intake`**.
3. Approve the staged rollback in **`#incident-war-room`** with:
   `@release-commander Approved. Roll back to v2.13.2`

---

## API Surface

| Endpoint | Purpose |
| :--- | :--- |
| `GET /api/v1/health` | Current `cart-service` version and health |
| `POST /api/v1/checkout` | Target endpoint: 500 on `v2.14.0` with a discount code, 200 on `v2.13.2` |
| `POST /api/v1/airlock/scrub` | PII/secret/injection scrubbing + Luhn-valid synthetic fixture |
| `POST /api/v1/incidents/{id}/repro` | Records the deterministic pytest reproduction result |
| `POST /api/v1/flashprove/verify` | Verifies weight commitment + proof digest, records attestation |
| `POST /api/v1/admin/rollback` | Human-gated rollback (admin token + idempotency + approval phrase + verified attestation) |
| `GET /api/v1/incidents` | Incident audit feed powering the Ops Console |
| `GET /dashboard` | WCAG 2.2 AA Ops Audit Console |

---

## Repository Layout

```text
switchguard-sre/
├── switchguard-sre.template.yaml   # Switch v2: 2 rooms, 3 agents, directional link
├── Dockerfile / docker-compose.yml # One-command judge runtime on :8090
├── blueprint/                      # schema.sql, design-tokens.json
├── demo_app/                       # FastAPI app, SQLite engine, airlock, verifier, dashboard
├── tools/                          # 4 agent CLI tools
├── fixtures/                       # FlashProve bundles + 5-case eval harness
├── scripts/                        # simulate_customer_crash.py
└── tests/                          # 34 automated tests
```

---

## Security Controls

- Synthetic Luhn-valid card and RFC-2606-safe email replace all customer PII.
- Prompt-injection patterns are neutralized and untrusted logs are wrapped in `<untrusted_crash_log>` delimiters.
- `Idempotency-Key` deduplicates alert storms and rollback retries.
- Rollback is blocked unless the admin token, approval phrase, and a verified FlashProve attestation are all present.

## License

Open source. Anthropic FlashProve and Switch AI are referenced as upstream dependencies.
