-- Open data/synthetic_scenarios.sqlite3 in READ-ONLY mode.
-- All results below are conditional synthetic outcomes, not real business risk.
SELECT simulation_id,scenario_id,scenario_label_en,count(*) AS hypothetical_paths,
       avg(eod_pending_amount_usd_million) AS mean_pending_usd_million,
       avg(eod_net_debit_usd_million) AS mean_outstanding_debit_usd_million
FROM synthetic_dtc_runs GROUP BY simulation_id,scenario_id;

SELECT simulation_id,scenario_id,count(*) AS hypothetical_paths,
       avg(overdue_order_fraction) AS mean_overdue_fraction,
       avg(delayed_completed_delivery_count) AS late_completed_orders,
       avg(unfinished_delivery_count) AS unfinished_orders
FROM synthetic_epn_runs GROUP BY simulation_id,scenario_id;

SELECT simulation_id,scenario_id,count(*) AS hypothetical_paths,
       avg(peak_overdue_to_initial) AS mean_peak_overdue_fraction,
       avg(excess_unsettled_notional_days_usd_days) AS excess_gross_notional_usd_days
FROM synthetic_tba_runs GROUP BY simulation_id,scenario_id;
