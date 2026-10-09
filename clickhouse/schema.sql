DROP DATABASE IF EXISTS guard;

CREATE DATABASE IF NOT EXISTS hive;

CREATE TABLE IF NOT EXISTS hive.agent_runs
(
    run_id            String,
    ts                DateTime64(3, 'UTC'),
    swarm_id          String,
    role              LowCardinality(String),
    model             LowCardinality(String),
    doc_id            String,
    source_id         String,
    latency_ms        UInt32,
    prompt_tokens     UInt32,
    completion_tokens UInt32,
    cost_usd          Float64,
    confidence        Float32,
    label             String,
    status            LowCardinality(String),
    injection_flag    UInt8,
    canary_tripped    UInt8,
    judge_verdict     LowCardinality(String),
    error             String,
    output            String
)
ENGINE = MergeTree
ORDER BY (swarm_id, ts);

CREATE TABLE IF NOT EXISTS hive.claims
(
    claim_id      String,
    run_id        String,
    doc_id        String,
    source_id     String,
    entity        String,
    claim_type    LowCardinality(String),
    text          String,
    value         String,
    confidence    Float32,
    status        LowCardinality(String),
    judge_verdict LowCardinality(String),
    judge_reason  String,
    senso_node_id String,
    created_at    DateTime64(3, 'UTC'),
    updated_at    DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY claim_id;

CREATE TABLE IF NOT EXISTS hive.injection_events
(
    event_id  String,
    ts        DateTime64(3, 'UTC'),
    swarm_id  String,
    run_id    String,
    doc_id    String,
    source_id String,
    detector  LowCardinality(String),
    pattern   String,
    snippet   String,
    severity  Float32
)
ENGINE = MergeTree
ORDER BY (swarm_id, ts);

CREATE TABLE IF NOT EXISTS hive.source_trust
(
    source_id  String,
    trust      Float32,
    updated_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY source_id;

CREATE TABLE IF NOT EXISTS hive.heartbeats
(
    ts                 DateTime64(3, 'UTC'),
    heartbeat_id       String,
    swarm_id           String,
    interval_s         UInt32,
    docs_collected     UInt32,
    docs_new           UInt32,
    runs               UInt32,
    claims_verified    UInt32,
    claims_quarantined UInt32,
    injections         UInt32,
    cost_usd           Float64,
    duration_ms        UInt32,
    status             LowCardinality(String)
)
ENGINE = MergeTree
ORDER BY ts;

CREATE TABLE IF NOT EXISTS hive.seen_docs
(
    url_hash   String,
    url        String,
    source_id  String,
    first_seen DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(first_seen)
ORDER BY url_hash;
