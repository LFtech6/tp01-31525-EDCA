-- Sentinel-AI (EDCA) — schema PostgreSQL
-- Idempotente (IF NOT EXISTS / OR REPLACE): pode ser reexecutado sem erro nem perda de dados.
-- Datas/horas: timestamp sem fuso, em hora local Europe/Lisbon (o ETL converte offsets das fontes).
-- Variável psql obrigatória: ro_user (role só de leitura).

SET client_min_messages = warning;

-- =====================================================================
-- 1. Controlo de execuções (escrito pelo Job Pentaho e pela API /ops)
-- =====================================================================
CREATE TABLE IF NOT EXISTS etl_run (
    run_id          text PRIMARY KEY,
    job_name        text        NOT NULL,
    trigger_source  text        NOT NULL DEFAULT 'cli'
                    CHECK (trigger_source IN ('cli', 'dashboard', 'schedule')),
    status          text        NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    requested_at    timestamp   NOT NULL DEFAULT now(),
    started_at      timestamp,
    finished_at     timestamp,
    exit_code       integer,
    error_message   text,
    log_path        text
);
-- Garante no máximo uma execução ativa (controlo de concorrência ao nível da BD)
CREATE UNIQUE INDEX IF NOT EXISTS ux_etl_run_single_active
    ON etl_run ((true)) WHERE status IN ('PENDING', 'RUNNING');

CREATE TABLE IF NOT EXISTS etl_run_stage (
    run_id          text      NOT NULL REFERENCES etl_run (run_id) ON DELETE CASCADE,
    stage           text      NOT NULL
                    CHECK (stage IN ('EXTRACT', 'TRANSFORM', 'CORRELATE', 'RULES', 'AI', 'EVALUATE', 'EXPORT')),
    status          text      NOT NULL DEFAULT 'RUNNING'
                    CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED', 'SKIPPED')),
    started_at      timestamp NOT NULL DEFAULT now(),
    finished_at     timestamp,
    rows_processed  integer,
    message         text,
    PRIMARY KEY (run_id, stage)
);

-- =====================================================================
-- 2. Referência (YAML: edifícios/zonas/dispositivos; XML: utilizadores)
-- =====================================================================
CREATE TABLE IF NOT EXISTS building (
    building_id     text PRIMARY KEY CHECK (building_id ~ '^B[0-9]{2}$'),
    name            text NOT NULL,
    run_id          text,
    loaded_at       timestamp NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS zone (
    zone_id         text PRIMARY KEY CHECK (zone_id ~ '^Z[0-9]{2}$'),
    building_id     text NOT NULL REFERENCES building (building_id),
    name            text NOT NULL,
    floor           smallint,
    security_level  text NOT NULL CHECK (security_level IN ('PUBLIC', 'INTERNAL', 'RESTRICTED', 'CRITICAL')),
    open_time       time NOT NULL,
    close_time      time NOT NULL,
    open_weekends   boolean NOT NULL DEFAULT false,
    run_id          text,
    loaded_at       timestamp NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS device (
    device_id       text PRIMARY KEY,
    device_kind     text NOT NULL CHECK (device_kind IN ('DOOR', 'SENSOR', 'HOST')),
    zone_id         text NOT NULL REFERENCES zone (zone_id),
    device_type     text,          -- ex.: MOTION, DOOR_CONTACT, WORKSTATION, SERVER
    ip_address      text,          -- só para HOST
    run_id          text,
    loaded_at       timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_device_zone ON device (zone_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_device_ip ON device (ip_address) WHERE ip_address IS NOT NULL;

CREATE TABLE IF NOT EXISTS app_user (
    user_id         text PRIMARY KEY CHECK (user_id ~ '^U[0-9]{3}$'),
    full_name       text NOT NULL,
    username        text NOT NULL UNIQUE,     -- login digital (fonte syslog)
    email           text,
    department      text,
    role            text NOT NULL,
    schedule_start  time,
    schedule_end    time,
    active          boolean NOT NULL DEFAULT true,
    run_id          text,
    loaded_at       timestamp NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_zone_permission (
    user_id         text NOT NULL REFERENCES app_user (user_id) ON DELETE CASCADE,
    zone_id         text NOT NULL REFERENCES zone (zone_id),
    run_id          text,
    PRIMARY KEY (user_id, zone_id)
);

-- =====================================================================
-- 3. Qualidade de dados: registos rejeitados (não se perdem, ficam auditáveis)
-- =====================================================================
CREATE TABLE IF NOT EXISTS dq_rejection (
    rejection_id     bigserial PRIMARY KEY,
    run_id           text,
    source           text NOT NULL,      -- ACCESS_CSV, SENSOR_API, AUTH_SYSLOG, USERS_XML, ZONES_YAML
    source_record_id text,
    raw_record       text,
    reason_code      text NOT NULL,      -- ex.: MISSING_TIMESTAMP, BAD_ID_FORMAT, UNKNOWN_ZONE
    reason_detail    text,
    rejected_at      timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_dq_rejection_run ON dq_rejection (run_id, source);

-- =====================================================================
-- 4. Eventos normalizados (modelo unificado das 3 fontes de eventos)
-- =====================================================================
CREATE TABLE IF NOT EXISTS event (
    event_id             text PRIMARY KEY,             -- ID da fonte normalizado (ACC0001, SEN0001, AUTH0001)
    source               text NOT NULL CHECK (source IN ('ACCESS', 'SENSOR', 'AUTH')),
    event_ts             timestamp NOT NULL,
    event_type           text NOT NULL,                -- ACCESS_GRANTED, ACCESS_DENIED, MOTION, LOGIN_SUCCESS, LOGIN_FAILURE...
    zone_id              text NOT NULL REFERENCES zone (zone_id),
    device_id            text REFERENCES device (device_id),
    user_id              text REFERENCES app_user (user_id),
    raw_user_ref         text,                         -- valor original antes da normalização (rastreabilidade)
    src_ip               text,
    -- flags de enriquecimento (tr_enrich_events)
    is_off_hours         boolean,
    is_unauthorized_zone boolean,
    is_unknown_user      boolean,
    run_id               text,
    loaded_at            timestamp NOT NULL DEFAULT now(),
    updated_at           timestamp NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_event_zone_ts ON event (zone_id, event_ts);
CREATE INDEX IF NOT EXISTS ix_event_user ON event (user_id);
CREATE INDEX IF NOT EXISTS ix_event_source_ts ON event (source, event_ts);

-- =====================================================================
-- 5. Correlação: casos e respetivos eventos de origem (rastreabilidade)
-- =====================================================================
CREATE TABLE IF NOT EXISTS security_case (
    case_id              text PRIMARY KEY,             -- determinístico: CASE-<zona>-<inicio>
    zone_id              text NOT NULL REFERENCES zone (zone_id),
    start_ts             timestamp NOT NULL,
    end_ts               timestamp NOT NULL,
    event_count          integer NOT NULL,
    distinct_users       integer NOT NULL,
    denied_count         integer NOT NULL DEFAULT 0,
    motion_count         integer NOT NULL DEFAULT 0,
    auth_failure_count   integer NOT NULL DEFAULT 0,
    off_hours_count      integer NOT NULL DEFAULT 0,
    unauthorized_count   integer NOT NULL DEFAULT 0,
    unknown_user_count   integer NOT NULL DEFAULT 0,
    events_hash          text NOT NULL,                -- md5 dos event_id ordenados (cache da IA)
    run_id               text,
    created_at           timestamp NOT NULL DEFAULT now(),
    CHECK (end_ts >= start_ts)
);
CREATE INDEX IF NOT EXISTS ix_case_zone_start ON security_case (zone_id, start_ts);

CREATE TABLE IF NOT EXISTS case_event (
    case_id         text    NOT NULL REFERENCES security_case (case_id) ON DELETE CASCADE,
    event_id        text    NOT NULL REFERENCES event (event_id),
    seq             integer NOT NULL,
    PRIMARY KEY (case_id, event_id)
);
CREATE INDEX IF NOT EXISTS ix_case_event_event ON case_event (event_id);

-- =====================================================================
-- 6. Abordagem A: motor de regras determinístico
-- =====================================================================
CREATE TABLE IF NOT EXISTS rule_result (
    case_id         text PRIMARY KEY REFERENCES security_case (case_id) ON DELETE CASCADE,
    run_id          text,
    is_suspicious   boolean NOT NULL,
    risk_level      text NOT NULL CHECK (risk_level IN ('NONE', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    matched_rules   text,                              -- ex.: 'R1,R3'
    rule_score      integer NOT NULL,
    evaluated_at    timestamp NOT NULL DEFAULT now()
);

-- =====================================================================
-- 7. Abordagem B: análise por IA (Qwen3 via FastAPI/Ollama)
-- =====================================================================
CREATE TABLE IF NOT EXISTS ai_analysis (
    analysis_id         bigserial PRIMARY KEY,
    case_id             text NOT NULL REFERENCES security_case (case_id) ON DELETE CASCADE,
    run_id              text,
    events_hash         text NOT NULL,
    prompt_version      text NOT NULL,
    model_name          text,
    model_digest        text,
    status              text NOT NULL
                        CHECK (status IN ('OK', 'TIMEOUT', 'INVALID_OUTPUT', 'MODEL_ERROR', 'API_UNAVAILABLE')),
    is_suspicious       boolean,
    risk_level          text CHECK (risk_level IN ('NONE', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    incident_type       text,
    explanation         text,
    recommended_action  text,
    evidence_event_ids  text,                          -- lista separada por vírgulas, validada ⊆ case_event
    raw_response        jsonb,
    error_message       text,
    latency_ms          integer,
    analyzed_at         timestamp NOT NULL DEFAULT now(),
    CHECK (status <> 'OK' OR (is_suspicious IS NOT NULL AND risk_level IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_ai_case ON ai_analysis (case_id, analyzed_at DESC);
-- Cache: no máximo uma análise OK por composição de caso + prompt + modelo
CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_cache
    ON ai_analysis (events_hash, prompt_version, model_digest) WHERE status = 'OK';

-- =====================================================================
-- 8. Avaliação (etiquetas definidas à priori, independentes das regras)
-- =====================================================================
CREATE TABLE IF NOT EXISTS ground_truth (
    event_id            text PRIMARY KEY,
    scenario_id         text NOT NULL,
    expected_suspicious boolean NOT NULL,
    rationale           text
);

CREATE TABLE IF NOT EXISTS evaluation_metric (
    run_id          text NOT NULL,
    approach        text NOT NULL CHECK (approach IN ('RULES', 'AI')),
    n_cases         integer NOT NULL,
    tp integer NOT NULL, fp integer NOT NULL, tn integer NOT NULL, fn integer NOT NULL,
    precision_val   numeric(5,4),
    recall_val      numeric(5,4),
    f1_val          numeric(5,4),
    avg_latency_ms  numeric(10,1),
    computed_at     timestamp NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, approach)
);

-- =====================================================================
-- 9. Permissões do utilizador só de leitura (Node-RED / dashboard)
-- =====================================================================
SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', :'ro_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO %I', :'ro_user') \gexec
