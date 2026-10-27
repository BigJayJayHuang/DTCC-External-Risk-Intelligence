-- Simulation-only primary outcomes. Compare within a model, not across services.
SELECT model_id,scenario_id,primary_metric,primary_units,
       avg(primary_value) AS hypothetical_mean
FROM synthetic_ml_runs
GROUP BY simulation_id,model_id,scenario_id,primary_metric,primary_units;

-- VM cash flows and incremental margin calls are separate measures.
SELECT scenario_id,avg(vm_paid_usd_million) AS vm_paid,
       avg(margin_call_usd_million) AS margin_call
FROM synthetic_ml_runs WHERE model_id='ml_market_nscc'
GROUP BY simulation_id,scenario_id;

-- The required SLD call can stay unchanged while collection and the gap improve.
SELECT scenario_id,avg(sld_called_usd_million) AS called,
       avg(sld_collected_usd_million) AS collected,
       avg(remaining_liquidity_gap_usd_million) AS remaining_gap
FROM synthetic_ml_runs WHERE model_id='ml_sld'
GROUP BY simulation_id,scenario_id;

-- Late-completed and unfinished records must not be collapsed into one count.
SELECT model_id,scenario_id,avg(overdue_fraction) AS overdue_fraction,
       avg(completed_late_count) AS completed_late,
       avg(unfinished_count) AS unfinished
FROM synthetic_ops_runs GROUP BY simulation_id,model_id,scenario_id;

-- Gross represented debits differ from the bank's net-net balance.
SELECT model_id,scenario_id,avg(blocked_participant_debit_usd_million) AS blocked_gross_debit,
       avg(unsettled_bank_net_debit_usd_million) AS unsettled_bank_net_debit
FROM synthetic_df_runs WHERE model_id IN ('dtc_bank','nscc_bank')
GROUP BY simulation_id,model_id,scenario_id;
