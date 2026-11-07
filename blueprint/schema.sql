-- SwitchGuard SRE — Database Schema (SQLite 3 WAL / PostgreSQL Compatible)
-- Traceability: Serves R-002, R-003, R-005, R-006, R-008, R-009, R-010, R-011, R-012, R-015, R-018

PRAGMA foreign_keys = ON;

-- 1. Singleton Runtime Configuration for Target cart-service (R-005, R-011)
CREATE TABLE IF NOT EXISTS runtime_config (
    config_id INTEGER PRIMARY KEY CHECK (config_id = 1),
    service_name VARCHAR(64) NOT NULL DEFAULT 'cart-service',
    active_version VARCHAR(32) NOT NULL DEFAULT 'v2.14.0' CHECK (active_version IN ('v2.13.2', 'v2.14.0')),
    fault_mode_enabled INTEGER NOT NULL DEFAULT 1 CHECK (fault_mode_enabled IN (0, 1)),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Incident State Machine (R-004, R-006, R-010, R-012, R-018)
CREATE TABLE IF NOT EXISTS incidents (
    incident_id VARCHAR(36) PRIMARY KEY,
    external_ticket_ref VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'OPEN' CHECK (
        status IN (
            'OPEN',
            'AIRLOCK_SCRUBBED',
            'REPRODUCED',
            'FLASHPROVE_VERIFIED',
            'PENDING_APPROVAL',
            'ROLLED_BACK',
            'POSTMORTEM_PUBLISHED',
            'BLOCKED_TAMPERED'
        )
    ),
    suspect_commit VARCHAR(64) NOT NULL DEFAULT 'v2.14.0',
    repro_exit_code INTEGER,
    repro_traceback TEXT,
    postmortem_doc_name VARCHAR(128),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_incidents_status_created ON incidents (status, created_at DESC);

-- 3. PII Airlock Redaction Vault & Synthetic Fixtures (R-002, R-003, R-014, R-015, R-018)
CREATE TABLE IF NOT EXISTS airlock_redactions (
    redaction_id VARCHAR(36) PRIMARY KEY,
    incident_id VARCHAR(36) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    idempotency_key VARCHAR(64) NOT NULL UNIQUE,
    raw_payload_sha256 CHAR(64) NOT NULL,
    emails_redacted INTEGER NOT NULL DEFAULT 0 CHECK (emails_redacted >= 0),
    cards_redacted INTEGER NOT NULL DEFAULT 0 CHECK (cards_redacted >= 0),
    secrets_redacted INTEGER NOT NULL DEFAULT 0 CHECK (secrets_redacted >= 0),
    injections_neutralized INTEGER NOT NULL DEFAULT 0 CHECK (injections_neutralized >= 0),
    sanitized_message TEXT NOT NULL,
    synthetic_fixture_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_airlock_incident_id ON airlock_redactions (incident_id);
CREATE INDEX IF NOT EXISTS idx_airlock_expires_at ON airlock_redactions (expires_at);

-- 4. Anthropic FlashProve Cryptographic Inference Attestations (R-008, R-009, R-018)
CREATE TABLE IF NOT EXISTS flashprove_attestations (
    attestation_id VARCHAR(36) PRIMARY KEY,
    incident_id VARCHAR(36) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    model_name VARCHAR(128) NOT NULL,
    weight_commitment_hash CHAR(64) NOT NULL,
    proof_sha256 CHAR(64) NOT NULL,
    token_count INTEGER NOT NULL CHECK (token_count > 0 AND token_count <= 1024),
    verifier_engine VARCHAR(64) NOT NULL DEFAULT 'cp_verify_v0.16.0',
    verify_duration_ms INTEGER NOT NULL CHECK (verify_duration_ms >= 0),
    soundness_bound VARCHAR(64) NOT NULL DEFAULT 'q/2^124 + 2^-101',
    is_verified INTEGER NOT NULL CHECK (is_verified IN (0, 1)),
    failure_reason TEXT,
    verified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_flashprove_incident_verified ON flashprove_attestations (incident_id, is_verified);

-- 5. Human-Gated Rollback Audit Log (R-010, R-011, R-015, R-018)
CREATE TABLE IF NOT EXISTS rollback_audit_log (
    rollback_id VARCHAR(36) PRIMARY KEY,
    incident_id VARCHAR(36) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    attestation_id VARCHAR(36) NOT NULL REFERENCES flashprove_attestations(attestation_id),
    idempotency_key VARCHAR(64) NOT NULL UNIQUE,
    from_version VARCHAR(32) NOT NULL,
    to_version VARCHAR(32) NOT NULL,
    approved_by_human VARCHAR(64) NOT NULL,
    approval_chat_message TEXT NOT NULL,
    post_rollback_http_status INTEGER NOT NULL,
    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rollback_incident_id ON rollback_audit_log (incident_id);

-- Initial Seed Data: Boot cart-service in buggy v2.14.0 state for immediate demo reproduction (R-005)
INSERT OR IGNORE INTO runtime_config (config_id, service_name, active_version, fault_mode_enabled)
VALUES (1, 'cart-service', 'v2.14.0', 1);
