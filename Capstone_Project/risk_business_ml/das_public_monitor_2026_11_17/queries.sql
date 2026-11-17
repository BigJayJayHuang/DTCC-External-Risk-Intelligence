-- Read-only queries against data/das_monitor.sqlite3 or the imported project DB.
SELECT record_key AS finding_id,
       json_extract(payload,'$.publication_date') AS publication_date,
       json_extract(payload,'$.title') AS title,
       json_extract(payload,'$.review_status') AS review_status,
       json_extract(payload,'$.next_action') AS next_action,
       json_extract(payload,'$.risk_score') AS risk_score
FROM records WHERE dataset_id='das_monitor_findings'
ORDER BY publication_date, finding_id;

SELECT record_key,
       json_extract(payload,'$.deadline') AS deadline,
       json_extract(payload,'$.submission_status') AS submission_status
FROM records WHERE dataset_id='das_monitor_deadlines';

SELECT dataset_id,count(*) AS records FROM records
WHERE dataset_id LIKE 'das_monitor_%' GROUP BY dataset_id;
