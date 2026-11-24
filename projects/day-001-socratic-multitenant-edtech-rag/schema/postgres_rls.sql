-- Production Multi-Tenant Schema for 50+ Schools / 100,000+ Students
-- Enforces hard tenant boundaries at the PostgreSQL database engine layer via Row-Level Security (RLS).
-- Paired with serverless scale-to-zero Postgres (e.g., Neon / Aurora Serverless v2) + pgvector.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 1. Tenants (Schools)
CREATE TABLE schools (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    curriculum      TEXT NOT NULL,
    active_days_yr  INT  NOT NULL DEFAULT 200,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. School Roster (Teachers & Students — Bulk CSV Onboarded)
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id       UUID NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    external_id     TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('admin', 'teacher', 'student')),
    grade_level     TEXT NOT NULL,
    class_section   TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    email           TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (school_id, external_id),
    UNIQUE (school_id, email)
);
CREATE INDEX idx_users_school_role ON users (school_id, role, grade_level);

-- 3. Ingested Curriculum Textbooks
CREATE TABLE textbooks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id       UUID NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    subject         TEXT NOT NULL,
    grade_level     TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (school_id, checksum_sha256)
);

-- 4. Hierarchical Knowledge Chunks (Prose, Tables, Equations, Diagrams)
CREATE TABLE knowledge_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id       UUID NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    textbook_id     UUID NOT NULL REFERENCES textbooks(id) ON DELETE CASCADE,
    chapter_title   TEXT NOT NULL,
    section_title   TEXT NOT NULL,
    page_number     INT  NOT NULL DEFAULT 1,
    block_type      TEXT NOT NULL CHECK (block_type IN ('prose', 'table', 'equation', 'diagram')),
    parent_context  TEXT NOT NULL,
    content         TEXT NOT NULL,
    tsv             TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', parent_context || ' ' || content)) STORED,
    embedding       VECTOR(1536) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chunks_school_scope ON knowledge_chunks (school_id, textbook_id, block_type);
CREATE INDEX idx_chunks_fts ON knowledge_chunks USING GIN (tsv);
CREATE INDEX idx_chunks_vec ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

-- 5. Content-Addressed Vision Extraction Cache (Deduplicates Expensive VLM Calls)
CREATE TABLE vision_extractions (
    school_id       UUID NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    image_sha256    TEXT NOT NULL,
    model_used      TEXT NOT NULL,
    structured_json JSONB NOT NULL,
    tokens_spent    INT  NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (school_id, image_sha256)
);

-- 6. Socratic Session Telemetry & Audit Log (PII-Redacted Prompts Only)
CREATE TABLE tutoring_turns (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id           UUID NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    session_id          UUID NOT NULL,
    student_ref         TEXT NOT NULL, -- Pseudonymized student token (FERPA/COPPA)
    attempt_number      INT  NOT NULL,
    hint_level          INT  NOT NULL CHECK (hint_level BETWEEN 1 AND 3),
    model_tier          TEXT NOT NULL CHECK (model_tier IN ('text-fast', 'text-reasoning', 'vision-vlm', 'vision-cache+text-fast')),
    vision_cache_hit    BOOLEAN NOT NULL DEFAULT false,
    estimated_cost_usd  NUMERIC(10, 6) NOT NULL DEFAULT 0,
    redacted_prompt     TEXT NOT NULL,
    socratic_response   TEXT NOT NULL,
    citations_json      JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_turns_school_session ON tutoring_turns (school_id, session_id, created_at);

-- ============================================================================
-- STRICT ROW-LEVEL SECURITY (RLS) — ZERO CROSS-TENANT LEAKAGE
-- Application middleware executes: SET LOCAL app.current_school_id = '<uuid>';
-- inside every transaction before querying any tenant table.
-- ============================================================================
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_users ON users
    USING (school_id = current_setting('app.current_school_id', true)::uuid)
    WITH CHECK (school_id = current_setting('app.current_school_id', true)::uuid);

ALTER TABLE textbooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE textbooks FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_textbooks ON textbooks
    USING (school_id = current_setting('app.current_school_id', true)::uuid)
    WITH CHECK (school_id = current_setting('app.current_school_id', true)::uuid);

ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_chunks FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_chunks ON knowledge_chunks
    USING (school_id = current_setting('app.current_school_id', true)::uuid)
    WITH CHECK (school_id = current_setting('app.current_school_id', true)::uuid);

ALTER TABLE vision_extractions ENABLE ROW LEVEL SECURITY;
ALTER TABLE vision_extractions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_vision ON vision_extractions
    USING (school_id = current_setting('app.current_school_id', true)::uuid)
    WITH CHECK (school_id = current_setting('app.current_school_id', true)::uuid);

ALTER TABLE tutoring_turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE tutoring_turns FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_turns ON tutoring_turns
    USING (school_id = current_setting('app.current_school_id', true)::uuid)
    WITH CHECK (school_id = current_setting('app.current_school_id', true)::uuid);
