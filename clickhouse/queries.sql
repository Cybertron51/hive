CREATE OR REPLACE VIEW hive.latest_swarm AS
SELECT
    swarm_id,
    min(ts) AS first_ts,
    max(ts) AS last_ts,
    count() AS runs
FROM hive.agent_runs
GROUP BY swarm_id
ORDER BY last_ts DESC
LIMIT 1;

CREATE OR REPLACE VIEW hive.runs_per_minute_by_model AS
SELECT
    swarm_id,
    toStartOfMinute(ts) AS minute,
    model,
    count() AS runs,
    countIf(status IN ('malformed', 'error')) AS failed,
    round(avg(latency_ms)) AS avg_latency_ms
FROM hive.agent_runs
WHERE ts > now() - INTERVAL 60 MINUTE
GROUP BY swarm_id, minute, model
ORDER BY minute, model;

CREATE OR REPLACE VIEW hive.confidence_histogram AS
SELECT
    swarm_id,
    role,
    least(floor(confidence * 10), 9) / 10 AS bucket,
    count() AS runs
FROM hive.agent_runs
GROUP BY swarm_id, role, bucket
ORDER BY role, bucket;

CREATE OR REPLACE VIEW hive.quarantine_queue AS
SELECT
    r.swarm_id AS swarm_id,
    c.created_at AS created_at,
    c.updated_at AS updated_at,
    c.claim_id AS claim_id,
    c.source_id AS source_id,
    c.entity AS entity,
    c.claim_type AS claim_type,
    c.text AS text,
    c.confidence AS confidence,
    c.status AS status,
    c.judge_verdict AS judge_verdict,
    c.judge_reason AS judge_reason
FROM hive.claims AS c FINAL
LEFT JOIN (SELECT run_id, any(swarm_id) AS swarm_id FROM hive.agent_runs GROUP BY run_id) AS r ON c.run_id = r.run_id
WHERE c.status IN ('pending', 'quarantined')
  AND (c.confidence < 0.6 OR c.judge_verdict = 'disagree')
ORDER BY c.created_at DESC
LIMIT 500;

CREATE OR REPLACE VIEW hive.claims_by_status AS
SELECT
    r.swarm_id AS swarm_id,
    c.status AS status,
    count() AS claims
FROM hive.claims AS c FINAL
LEFT JOIN (SELECT run_id, any(swarm_id) AS swarm_id FROM hive.agent_runs GROUP BY run_id) AS r ON c.run_id = r.run_id
GROUP BY swarm_id, status;

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
LIMIT 500;

CREATE OR REPLACE VIEW hive.injection_counts AS
SELECT swarm_id, count() AS injections
FROM hive.injection_events
GROUP BY swarm_id;

CREATE OR REPLACE VIEW hive.misclassification_by_model AS
SELECT
    swarm_id,
    model,
    countIf(judge_verdict != 'na') AS judged,
    countIf(judge_verdict = 'disagree') AS disagreed,
    round(disagreed / nullIf(judged, 0), 3) AS disagree_rate
FROM hive.agent_runs
GROUP BY swarm_id, model
ORDER BY disagree_rate DESC;

CREATE OR REPLACE VIEW hive.cost_by_model AS
SELECT
    swarm_id,
    model,
    count() AS runs,
    sum(prompt_tokens) AS prompt_tokens,
    sum(completion_tokens) AS completion_tokens,
    round(sum(cost_usd), 4) AS cost_usd
FROM hive.agent_runs
GROUP BY swarm_id, model
ORDER BY cost_usd DESC;

CREATE OR REPLACE VIEW hive.source_trust_current AS
SELECT source_id, trust, updated_at
FROM hive.source_trust FINAL
ORDER BY trust ASC;

CREATE OR REPLACE VIEW hive.runs_timeline AS
SELECT
    toStartOfInterval(toDateTime(ts), INTERVAL 10 SECOND) AS bucket,
    countIf(status = 'ok') AS ok,
    countIf(status = 'malformed') AS malformed,
    countIf(status = 'quarantined') AS quarantined,
    countIf(status = 'rerouted') AS rerouted,
    countIf(status = 'error') AS error
FROM hive.agent_runs
WHERE swarm_id = (SELECT swarm_id FROM hive.latest_swarm)
GROUP BY bucket
ORDER BY bucket WITH FILL STEP INTERVAL 10 SECOND;
