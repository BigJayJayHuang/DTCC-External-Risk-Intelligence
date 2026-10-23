-- Reviewed public research import, 2026-10-21. Open the database read-only.
-- Source dates differ; ingestion date is not the observation/publication date.

-- OFR coverage and missingness. Native unit_magnitude is retained in each payload.
SELECT json_extract(payload,'$.mnemonic') AS series,
       min(measurement_date) AS first_date,max(measurement_date) AS last_date,
       count(*) AS rows,
       sum(json_extract(payload,'$.value') IS NULL) AS missing_rows,
       json_extract(payload,'$.units') AS units,
       json_extract(payload,'$.unit_magnitude') AS magnitude
FROM records WHERE dataset_id='ofr_repo_observations' GROUP BY series;

-- Quarter-specific fund transactions, not gross processing volume.
SELECT json_extract(payload,'$.series_id') AS series,
       json_extract(payload,'$.quarter') AS quarter,
       json_extract(payload,'$.value') AS value_million_usd,
       json_extract(payload,'$.vintage_publication_date') AS release_date
FROM records WHERE dataset_id='fund_flow_quarterly' ORDER BY series,quarter;

-- Treasury supply aligned to issue month. Announced supply is not actual award.
SELECT substr(json_extract(payload,'$.issue_date'),1,7) AS issue_month,
       sum(json_extract(payload,'$.offered_amount_usd')) AS offered_usd,
       count(*) AS completed_auctions
FROM records WHERE dataset_id='treasury_auctions' GROUP BY issue_month ORDER BY issue_month;

-- Compare raw PQD scales and explicitly reconciled outcomes; do not coalesce null to 0.
SELECT json_extract(payload,'$.entity') AS entity,
       json_extract(payload,'$.quarter') AS quarter,
       json_extract(payload,'$.unsettled_notional_usd_as_reported') AS original_unsettled,
       json_extract(payload,'$.unsettled_notional_usd_reconciled') AS chosen_unsettled,
       json_extract(payload,'$.cleared_notional_usd_as_reported') AS original_cleared,
       json_extract(payload,'$.cleared_notional_usd_reconciled') AS chosen_cleared
FROM records WHERE dataset_id='chain_pqd_observations' ORDER BY entity,quarter;

-- Shared source/business links are routing metadata, not evidence of actual impact.
SELECT s.source_id,s.name,b.business_line,s.enabled,s.last_status
FROM sources s JOIN source_business b USING(source_id)
WHERE s.kind='reviewed_research_batch' ORDER BY s.source_id,b.business_line;
