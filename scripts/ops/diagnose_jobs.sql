-- Operator script (Christopher). Not for Dennis.
-- Read-only diagnostics for the next time a job looks slow.
-- Column is job_type (not type). No statement in this file writes data.
--
-- Usage: paste one query at a time into psql against production.

SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;

-- Currently running jobs and their age.
-- Bad answer: a row older than ~30s (snapshot jobs finish in ~16s). A row
-- older than 300s is an orphan from a process restart; before the stale-job
-- sweep, that row sat running forever and the worker never claimed it.
SELECT
    id,
    job_type,
    status,
    started_at,
    now() - started_at AS running_for
FROM jobs
WHERE status = 'running'
ORDER BY started_at;

-- Queue time vs run time for the last 20 jobs, as two separate intervals.
-- Bad answer: queued_for of minutes while ran_for is tens of seconds (the
-- 2026-08-26 pattern: 787s waiting, then 19.7s of actual work). A large
-- ran_for means the job itself is slow (weclapp or the database), not the
-- worker.
SELECT
    id,
    job_type,
    status,
    created_at,
    started_at,
    finished_at,
    started_at - created_at AS queued_for,
    finished_at - started_at AS ran_for
FROM jobs
ORDER BY created_at DESC
LIMIT 20;

-- Any job whose lifetime overlapped a given window.
-- This is the query that was missing during the 2026-08-26 investigation:
-- a job waited 787s to be claimed after three Uvicorn restarts, and there
-- was no way to list every other job that was queued or running in that
-- window.
-- Bad answer: another job running (or stuck running) for the whole window,
-- or several jobs sharing it on a single worker thread.
-- Replace the two timestamps before running.
WITH params AS (
    SELECT
        TIMESTAMPTZ '2026-08-26 00:00:00+02' AS window_start,
        TIMESTAMPTZ '2026-08-26 23:59:59+02' AS window_end
)
SELECT
    j.id,
    j.job_type,
    j.status,
    j.created_at,
    j.started_at,
    j.finished_at,
    j.created_at AS lifetime_start,
    COALESCE(j.finished_at, now()) AS lifetime_end
FROM jobs j
CROSS JOIN params p
WHERE j.created_at < p.window_end
  AND COALESCE(j.finished_at, now()) > p.window_start
ORDER BY j.created_at;

-- App connections: state, wait_event_type, wait_event, state_change.
-- Filtered to application_name = 'prosema-tools' (set in app/db.py).
-- Bad answer: 'idle in transaction' with an old state_change (a session is
-- holding a lock); wait_event ClientRead or IO with a query that should have
-- finished; empty result means the app is not connected at all.
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    state_change,
    now() - state_change AS state_age,
    query
FROM pg_stat_activity
WHERE application_name = 'prosema-tools'
ORDER BY state_change;

-- Database size and per-table size for the snapshot tables, against the
-- 32 GiB ceiling (Flexible Server, autogrow off). When the disk fills the
-- database goes read-only and the app fails in a way that looks like a bug.
-- Bad answer: pct_of_32_gib heading toward 100. article_snapshot_rows
-- grows without bound: each pull inserts a new header plus a full copy of
-- every article; old rows are not pruned.
SELECT
    current_database() AS database,
    pg_size_pretty(pg_database_size(current_database())) AS size,
    pg_database_size(current_database()) AS bytes,
    (32::bigint * 1024 * 1024 * 1024) AS ceiling_bytes,
    round(
        100.0 * pg_database_size(current_database())
            / (32::bigint * 1024 * 1024 * 1024),
        1
    ) AS pct_of_32_gib;

SELECT
    c.relname AS table_name,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
    pg_size_pretty(pg_relation_size(c.oid)) AS heap,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes,
    round(
        100.0 * pg_total_relation_size(c.oid)
            / (32::bigint * 1024 * 1024 * 1024),
        2
    ) AS pct_of_32_gib
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN ('article_snapshots', 'article_snapshot_rows')
ORDER BY pg_total_relation_size(c.oid) DESC;
