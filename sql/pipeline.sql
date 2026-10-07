CREATE OR REPLACE TABLE deduplicated AS
SELECT * EXCLUDE (rn) FROM (
    SELECT *, row_number() OVER (
        PARTITION BY event_id, CASE WHEN event_id IS NULL OR trim(event_id) = '' THEN source_row END ORDER BY received_at DESC, source_row DESC
    ) AS rn FROM usage_events
) WHERE rn = 1;

-- Reduce temporal matches to one row per deduplicated input before joining.
-- COUNT(history_id), not COUNT(*), makes unmatched LEFT JOIN rows count as zero.
CREATE OR REPLACE TABLE plan_matches AS
SELECT e.source_row, count(h.history_id) AS match_count,
       CASE WHEN count(h.history_id) = 1 THEN max(h.plan) END AS plan
FROM deduplicated e
LEFT JOIN plan_history h
  ON e.customer_id = h.customer_id
 AND e.occurred_at >= h.valid_from
 AND (h.valid_to IS NULL OR e.occurred_at < h.valid_to)
GROUP BY e.source_row;

CREATE OR REPLACE TABLE classified AS
SELECT e.*, m.plan, m.match_count AS plan_match_count,
       normalize_device(e.device_code) AS normalized_device,
       CASE
         WHEN e.event_id IS NULL OR trim(e.event_id) = '' THEN 'missing_event_id'
         WHEN e.occurred_at IS NULL OR e.received_at IS NULL THEN 'missing_timestamp'
         WHEN c.customer_id IS NULL THEN 'unknown_customer'
         WHEN m.match_count = 0 THEN 'no_matching_plan'
         WHEN m.match_count > 1 THEN 'ambiguous_plan'
         WHEN e.megabytes IS NULL THEN 'missing_volume'
         WHEN e.megabytes < 0 THEN 'negative_volume'
         WHEN normalize_device(e.device_code) IS NULL THEN 'invalid_device'
         ELSE NULL
       END AS rejection_reason
FROM deduplicated e
LEFT JOIN customers c USING (customer_id)
LEFT JOIN plan_matches m USING (source_row);

CREATE OR REPLACE TABLE rejected_events AS
SELECT * FROM classified WHERE rejection_reason IS NOT NULL;

CREATE OR REPLACE TABLE daily_usage AS
SELECT CAST(occurred_at AS DATE) AS usage_date, customer_id, plan,
       count(*) AS event_count, sum(megabytes) AS total_mb,
       sum(CASE WHEN extract(hour FROM occurred_at) BETWEEN 9 AND 17
                THEN megabytes ELSE 0 END) AS daytime_mb
FROM classified WHERE rejection_reason IS NULL
GROUP BY 1, 2, 3;
