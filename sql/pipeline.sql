CREATE OR REPLACE TABLE deduplicated AS
SELECT * EXCLUDE (rn) FROM (
    SELECT *, row_number() OVER (
        PARTITION BY event_id ORDER BY received_at DESC, source_row DESC
    ) AS rn FROM usage_events
) WHERE rn = 1;

CREATE OR REPLACE TABLE classified AS
SELECT e.*, c.plan,
       normalize_device(e.device_code) AS normalized_device,
       CASE
         WHEN c.customer_id IS NULL THEN 'unknown_customer'
         WHEN e.megabytes IS NULL THEN 'missing_volume'
         WHEN e.megabytes < 0 THEN 'negative_volume'
         WHEN normalize_device(e.device_code) IS NULL THEN 'invalid_device'
         ELSE NULL
       END AS rejection_reason
FROM deduplicated e
LEFT JOIN customers c USING (customer_id);

CREATE OR REPLACE TABLE rejected_events AS
SELECT * FROM classified WHERE rejection_reason IS NOT NULL;

CREATE OR REPLACE TABLE daily_usage AS
SELECT CAST(occurred_at AS DATE) AS usage_date, customer_id, plan,
       count(*) AS event_count, sum(megabytes) AS total_mb,
       sum(CASE WHEN extract(hour FROM occurred_at) BETWEEN 9 AND 17
                THEN megabytes ELSE 0 END) AS daytime_mb
FROM classified WHERE rejection_reason IS NULL
GROUP BY 1, 2, 3;
