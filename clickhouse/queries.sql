CREATE OR REPLACE VIEW hive.runs_per_minute_by_model AS
SELECT
    toStartOfMinute(ts) AS minute,
    model,
    count() AS runs,
    countIf(status IN ('malformed', 'error')) AS failed,
    round(avg(latency_ms)) AS avg_latency_ms
FROM hive.agent_runs
WHERE ts > now() - INTERVAL 60 MINUTE
GROUP BY minute, model
ORDER BY minute, model;

CREATE OR REPLACE VIEW hive.confidence_histogram AS
SELECT
    role,
    least(floor(confidence * 10), 9) / 10 AS bucket,
    count() AS runs
FROM hive.agent_runs
GROUP BY role, bucket
ORDER BY role, bucket;

CREATE OR REPLACE VIEW hive.quarantine_queue AS
SELECT
    created_at,
    claim_id,
    source_id,
    entity,
    claim_type,
    text,
    confidence,
    status,
    judge_verdict,
    judge_reason
FROM hive.claims
WHERE status IN ('pending', 'quarantined')
  AND (confidence < 0.6 OR judge_verdict = 'disagree')
ORDER BY created_at DESC
LIMIT 100;

CREATE OR REPLACE VIEW hive.injection_recent AS
SELECT
    ts,
    swarm_id,
    source_id,
    detector,
    pattern,
    snippet,
    severity
FROM hive.injection_events
ORDER BY ts DESC
LIMIT 50;

CREATE OR REPLACE VIEW hive.misclassification_by_model AS
SELECT
    model,
    countIf(judge_verdict != 'na') AS judged,
    countIf(judge_verdict = 'disagree') AS disagreed,
    round(disagreed / nullIf(judged, 0), 3) AS disagree_rate
FROM hive.agent_runs
GROUP BY model
ORDER BY disagree_rate DESC;

CREATE OR REPLACE VIEW hive.cost_by_model AS
SELECT
    model,
    count() AS runs,
    sum(prompt_tokens) AS prompt_tokens,
    sum(completion_tokens) AS completion_tokens,
    round(sum(cost_usd), 4) AS cost_usd
FROM hive.agent_runs
GROUP BY model
ORDER BY cost_usd DESC;

CREATE OR REPLACE VIEW hive.source_trust_current AS
SELECT source_id, trust, updated_at
FROM hive.source_trust FINAL
ORDER BY trust ASC;
