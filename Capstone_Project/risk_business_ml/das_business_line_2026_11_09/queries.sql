-- Run against an uncompressed DAS package or the project database.
SELECT dataset_id, count(*) AS rows FROM records WHERE dataset_id LIKE 'das_%' GROUP BY dataset_id;
SELECT record_key AS card_id, json_extract(payload,'$.name_en') AS chain,
       json_extract(payload,'$.proposed_internal_buffer_metric') AS internal_buffer,
       json_extract(payload,'$.real_v_available') AS real_v_available
FROM records WHERE dataset_id='das_chain_candidates';
SELECT record_key, json_extract(payload,'$.statement_en') AS public_fact,
       json_extract(payload,'$.limitation') AS limitation
FROM records WHERE dataset_id='das_public_facts';
-- Missing internal V is NULL, never zero or automatically simulated.
SELECT count(*) AS unavailable_positions
FROM records WHERE dataset_id='das_v_availability'
AND json_extract(payload,'$.V_score') IS NULL;
