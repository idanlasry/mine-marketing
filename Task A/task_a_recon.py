# %%
"""Task A / Step 0 — join keys and scope.

CH.1 dupes (raw) -> CH.2 scope -> CH.3 joins, CH.4 ids, CH.5 accounts, CH.6 attrition.
CH.1 reads raw tables on purpose; everything after CH.2 reads *_scoped only.
Run `Task A/load_bigquery.py` once to create the tables from data/.
"""

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)

PROJECT, DATASET = "first-proj001", "mine_marketing"
client = bigquery.Client(project=PROJECT)

# ? token is "$." not "$" so a regex anchor ($) inside a query survives
q = lambda sql: client.query(
    sql.replace("$.", f"`{PROJECT}.{DATASET}`.")
).to_dataframe()

q("""
SELECT table_name, COUNT(*) AS columns
FROM $.INFORMATION_SCHEMA.COLUMNS GROUP BY table_name ORDER BY table_name
""")
# * 5 raw tables + 4 scoped views. Column counts match the CSVs.


# =============================================================================
#  CH.1  DUPES — 72 (adset_id, date) keys appear twice. Identical? Clustered?
# =============================================================================

# %% CH.1a  how many, are the copies identical, where
q("""
WITH dup_key AS (
  SELECT adset_id, date FROM $.performance GROUP BY adset_id, date HAVING COUNT(*) > 1
),
dup_row AS (SELECT p.* FROM $.performance p JOIN dup_key USING (adset_id, date))
SELECT (SELECT COUNT(*) FROM $.performance)                             AS rows_total,
       (SELECT COUNT(*) FROM dup_key)                                   AS duplicate_keys,
       (SELECT COUNT(*) FROM dup_row) - (SELECT COUNT(*) FROM dup_key)  AS extra_rows,
       (SELECT COUNT(DISTINCT account_name) FROM dup_row)               AS accounts_affected,
       (SELECT STRING_AGG(DISTINCT account_name) FROM dup_row)          AS account,
       (SELECT STRING_AGG(DISTINCT CAST(date AS STRING)) FROM dup_row)  AS date,
       -- ? 2 rows -> 1 distinct JSON means no column value conflicts
       (SELECT COUNT(DISTINCT TO_JSON_STRING(t)) FROM dup_row t)
         = (SELECT COUNT(*) FROM dup_key)                               AS copies_are_identical,
       (SELECT ROUND(SUM(spend) / 2) FROM dup_row)                      AS spend_double_counted
""")
# * copies identical -> no tie-break needed. All 72 in ACC-03 on 2026-06-09.
# ! $226 double-counted = 100% of ACC-03's 06-09 spend, inside the window.

# %% CH.1b  is 06-09 a normal day for ACC-03?
q("""
SELECT date, COUNT(*) AS row_count, COUNT(DISTINCT adset_id) AS adsets, ROUND(SUM(spend)) AS spend
FROM $.performance WHERE account_name = 'ACC-03' GROUP BY date ORDER BY date
""")
# * every other day: rows == adsets. 06-09: 144 rows / 72 adsets = exactly 2x.
# * 72 fits the ramp (43,66,69,[72],124,138,138) -> one load ran twice.
# TODO DECISIONS.md: dedup rule = DISTINCT (lossless, applied in CH.2a).


# =============================================================================
#  CH.2  SCOPE — the only place rows are removed. Views, not per-query WHEREs,
#        so no two tables can disagree about the denominator.
# =============================================================================

# %% CH.2a  build
# * THE DEDUP: DISTINCT drops the 72 identical copies from CH.1. 4947 -> 4875.
q("CREATE OR REPLACE VIEW $.performance_scoped AS SELECT DISTINCT * FROM $.performance")

# * then filter the rest to adsets that appear in performance (17 of 1000 never spent — CH.8b)
for table in ["metadata", "rule_executions", "buyer_actions"]:
    q(f"""
    CREATE OR REPLACE VIEW $.{table}_scoped AS
    SELECT * FROM $.{table}
    WHERE adset_id IN (SELECT adset_id FROM $.performance_scoped)
    """)

# %% CH.2b  receipt
q("""
WITH before_after AS (
  SELECT 'performance' AS t, (SELECT COUNT(*) FROM $.performance) AS rows_before,
         (SELECT COUNT(*) FROM $.performance_scoped) AS rows_after,
         (SELECT COUNT(DISTINCT adset_id) FROM $.performance) AS adsets_before,
         (SELECT COUNT(DISTINCT adset_id) FROM $.performance_scoped) AS adsets_after
  UNION ALL
  SELECT 'metadata', (SELECT COUNT(*) FROM $.metadata),
         (SELECT COUNT(*) FROM $.metadata_scoped),
         (SELECT COUNT(DISTINCT adset_id) FROM $.metadata),
         (SELECT COUNT(DISTINCT adset_id) FROM $.metadata_scoped)
  UNION ALL
  SELECT 'rule_executions', (SELECT COUNT(*) FROM $.rule_executions),
         (SELECT COUNT(*) FROM $.rule_executions_scoped),
         (SELECT COUNT(DISTINCT adset_id) FROM $.rule_executions),
         (SELECT COUNT(DISTINCT adset_id) FROM $.rule_executions_scoped)
  UNION ALL
  SELECT 'buyer_actions', (SELECT COUNT(*) FROM $.buyer_actions),
         (SELECT COUNT(*) FROM $.buyer_actions_scoped),
         (SELECT COUNT(DISTINCT adset_id) FROM $.buyer_actions),
         (SELECT COUNT(DISTINCT adset_id) FROM $.buyer_actions_scoped)
)
SELECT t AS table_name, rows_before, rows_after, rows_before - rows_after AS rows_dropped,
       adsets_before, adsets_after
FROM before_after ORDER BY rows_before DESC
""")
# * performance 4947->4875: the 72 duplicate rows are gone.
# * total spend across all 6 accounts corrects from $9,138 to $8,912 (-$226).
# * metadata 7129->1000: catalogue; 6129 never spent. Now 1:1 with performance.
# ! buyer_actions 1001->715 but adsets 185->185 — dropped rows never named an adset.
# ! those 286 are object_type='campaign', and there is no campaign_id column.
# ? 1000 adsets = 1000 campaigns, so each maps to 1 adset — the file won't say which.
# TODO INVESTIGATION.md: "29% of buyer actions unattributable", or 715 looks wrong.


# =============================================================================
#  CH.3+  DESCRIBE — everything below reads *_scoped.
# =============================================================================

# %% CH.3  JOIN MAP — does every file's adset_id land in performance?
q("""
WITH every_file AS (
  SELECT 'daily_adset_performance' AS file, adset_id FROM $.performance_scoped
  UNION ALL SELECT 'rule_executions',         adset_id FROM $.rule_executions_scoped
  UNION ALL SELECT 'campaign_adset_metadata', adset_id FROM $.metadata_scoped
  UNION ALL SELECT 'buyer_actions',           adset_id FROM $.buyer_actions_scoped
),
perf_ids AS (SELECT DISTINCT adset_id FROM $.performance_scoped)
SELECT file,
       COUNT(*)                                          AS row_count,
       COUNTIF(adset_id IS NULL)                         AS blank_adset_id,
       COUNT(DISTINCT adset_id)                          AS adsets,
       COUNTIF(LENGTH(adset_id) = 14)                    AS id_len_14,
       COUNTIF(LENGTH(adset_id) = 18)                    AS id_len_18,
       COUNT(DISTINCT IF(adset_id IN (SELECT adset_id FROM perf_ids), adset_id, NULL))
                                                         AS in_performance,
       COUNT(DISTINCT IF(adset_id NOT IN (SELECT adset_id FROM perf_ids), adset_id, NULL))
                                                         AS unmatched
FROM every_file
GROUP BY file
ORDER BY row_count DESC
""")
# * unmatched = 0 and blank = 0 everywhere. Base is sound.
# ? rule_executions: 214 rows of len 14, ZERO of len 18. Not a quirk — see CH.5.

# %% CH.4  ID FORMAT — are the 14-digit ids truncated 18-digit ids?
q(r"""
WITH every_id AS (
  SELECT adset_id FROM $.performance_scoped     UNION DISTINCT
  SELECT adset_id FROM $.rule_executions_scoped UNION DISTINCT
  SELECT adset_id FROM $.metadata_scoped        UNION DISTINCT
  SELECT adset_id FROM $.buyer_actions_scoped
)
SELECT LOGICAL_AND(REGEXP_CONTAINS(adset_id, r'^\d+$'))  AS digits_only_unpadded,
       COUNTIF(LENGTH(adset_id) = 14)                    AS short_ids,
       -- ? a short id is a truncation only if some long id ENDS WITH it
       COUNTIF(LENGTH(adset_id) = 14 AND EXISTS (
         SELECT 1 FROM every_id AS wide
         WHERE LENGTH(wide.adset_id) = 18
           AND RIGHT(wide.adset_id, 14) = every_id.adset_id))  AS short_ids_inside_a_long
FROM every_id
WHERE adset_id IS NOT NULL
""")
# * 0 of 117 short ids sit inside a long one. Truncation would put it near 117.
# ! do NOT write normalize_adset_id() — padding/trimming fabricates collisions.

# %% CH.5  BY ACCOUNT — the headline
q("""
WITH adset_account AS (SELECT DISTINCT adset_id, account_name FROM $.performance_scoped),
account AS (
  SELECT account_name,
         COUNT(DISTINCT adset_id)                                    AS adsets,
         -- ? DISTINCT is the proof: a mixed account would render "14/18"
         STRING_AGG(DISTINCT CAST(LENGTH(adset_id) AS STRING), '/')  AS id_len,
         ROUND(SUM(spend))                                           AS spend,
         ROUND(SUM(spend) / SUM(SUM(spend)) OVER (), 3)              AS spend_share,
         ROUND(SUM(revenue))                                         AS revenue,
         ROUND(SUM(revenue) / NULLIF(SUM(spend), 0), 2)              AS roas,
         SUM(fb_conversions)                                         AS fb_conv,
         ROUND(SUM(estimated_conversions))                           AS est_conv
  FROM $.performance_scoped GROUP BY account_name
),
ruled AS (
  SELECT account_name, COUNT(*) AS rule_executions, COUNT(DISTINCT adset_id) AS adsets_ruled
  FROM $.rule_executions_scoped JOIN adset_account USING (adset_id) GROUP BY account_name
),
bought AS (
  SELECT account_name, COUNT(*) AS buyer_actions, COUNT(DISTINCT adset_id) AS adsets_bought
  FROM $.buyer_actions_scoped JOIN adset_account USING (adset_id) GROUP BY account_name
)
SELECT account_name, adsets, id_len, spend, spend_share, revenue, roas, fb_conv, est_conv,
       IFNULL(rule_executions, 0) AS rule_executions, IFNULL(adsets_ruled, 0)  AS adsets_ruled,
       IFNULL(buyer_actions, 0)   AS buyer_actions,   IFNULL(adsets_bought, 0) AS adsets_bought
FROM account LEFT JOIN ruled USING (account_name) LEFT JOIN bought USING (account_name)
ORDER BY account_name
""")
# * id_len is one value per account: ACC-04="14", the rest "18". An account marker.
# ! all 214 executions are ACC-04 (75 of 117 adsets), zero elsewhere = 29% of spend.
# ! so every Task A impact number is an ACC-04 number. Do not extrapolate.
# * ACC-04 is the BEST account (ROAS 1.19, biggest spender) — not the bleeding one.
# * ACC-05 is the bleeding one: ROAS 0.79, -$148 on $690, and no rules at all.
# ? 28 ACC-04 adsets touched by both a rule and a buyer — contested attribution.
# ? est_conv >= fb_conv on every row (0 exceptions); uplift bigger on fresh data.
# TODO Step 6: report BOTH conv ratios, or attribution lag reads as a performance gap.

# %% CH.6  ATTRITION — what survives a before/after comparison
q("""
WITH bounds AS (SELECT MIN(date) AS first_day, MAX(date) AS last_day FROM $.performance_scoped),
perf_ids AS (SELECT DISTINCT adset_id FROM $.performance_scoped)
SELECT (SELECT first_day FROM bounds) AS performance_from,
       (SELECT last_day  FROM bounds) AS performance_to,
       COUNT(*)                                                     AS executions_logged,
       COUNTIF(adset_id IS NULL)                                    AS drop_campaign_level,
       COUNTIF(adset_id NOT IN (SELECT adset_id FROM perf_ids))     AS drop_no_performance_row,
       COUNTIF(action_date >= (SELECT last_day FROM bounds))        AS drop_no_after_window,
       COUNTIF(adset_id IS NOT NULL
           AND adset_id IN (SELECT adset_id FROM perf_ids)
           AND action_date < (SELECT last_day FROM bounds))         AS usable
FROM $.rule_executions_scoped
""")
# * 214 -> 206 usable (96%). Only loss: 8 fired on 06-12, no after-window.

# %% CH.6b  WHEN they fired — how settled the revenue behind each action is
q("""
SELECT action_date, COUNT(*) AS executions, COUNT(DISTINCT adset_id) AS adsets,
       COUNT(DISTINCT rule_id) AS rules
FROM $.rule_executions_scoped GROUP BY action_date ORDER BY action_date
""")
# * 73% of actions (156/214) fired in the first 3 days, 06-06 to 06-08.
# * data ends 06-12, so those actions have 4-6 days of revenue behind them to judge by.
# ! 06-09 is odd in shape: 13 executions, 1 adset, 1 rule. Others span 4-22 adsets.
# * resolved in CH.7a: a retry loop on "No budget to change", not a wrong decision.


# =============================================================================
#  CH.7  QUALITY — outliers, suspicious values, null patterns
# =============================================================================

# %% CH.7a  EXECUTION FAILURES — when did actions not happen?
q("""
SELECT action_date,
       COUNTIF(response = 'SUCCESS')                                 AS success,
       COUNTIF(response LIKE '%OAuthException%')                     AS oauth_error,
       COUNTIF(response LIKE '%No budget to change%')                AS no_budget,
       STRING_AGG(DISTINCT IF(response != 'SUCCESS', rule_id, NULL)) AS failing_rules,
       MIN(IF(response LIKE '%OAuth%', action_time, NULL))           AS first_error,
       MAX(IF(response LIKE '%OAuth%', action_time, NULL))           AS last_error
FROM $.rule_executions_scoped GROUP BY action_date ORDER BY action_date
""")
# ! 06-08 03:30-16:30: Meta token invalidated -> 27 errors, 0 success that window.
# ! R09 (the "undo automation mistake" rule) fired 8x on an adset at ROI +1.01, 8/8 failed.
# * 06-09's 13 rows = R02 retrying every 30 min on "No budget to change".

# %% CH.7b  BUDGET COLUMNS — which one is the truth?
q("""
SELECT rule_id, action_name, COUNT(*) AS n,
       COUNTIF(new_budget > old_budget)                         AS new_gt_old,
       COUNTIF(ABS(current_budget_from_fb - new_budget) < 0.01) AS fb_eq_new,
       ROUND(AVG(SAFE_DIVIDE(set_budget, new_budget)), 3)       AS set_over_new
FROM $.rule_executions_scoped
WHERE action_name LIKE 'Decrease%' AND response = 'SUCCESS'
GROUP BY rule_id, action_name ORDER BY rule_id
""")
# * set/new = 0.80 / 0.60 / 0.85 = each rule's cut: new_budget is the PRE-action budget.
# ! "Decrease" rows with new > old = old_budget is one step stale (a buyer moved it between).
# ! trust set_budget (target) + current_budget_from_fb (live). Not old/new.

# %% CH.7c  NULLS — blank revenue means no spend, not delay
q("""
SELECT date,
       COUNTIF(spend > 0)                     AS spend_rows,
       COUNTIF(spend > 0 AND revenue IS NULL) AS spend_rev_null,
       COUNTIF(spend = 0)                     AS zero_rows,
       COUNTIF(spend = 0 AND revenue IS NULL) AS zero_rev_null,
       COUNTIF(spend = 0 AND revenue > 0)     AS zero_spend_rev_pos
FROM $.performance_scoped GROUP BY date ORDER BY date
""")
# ! spend_rev_null = 0 every day, 06-12 included. Revenue delay is NOT visible as blanks.
# * rule_executions nulls are structural too: last_3_days_* <=> total_days < 3,
# * current_budget_from_fb <=> response != SUCCESS, today_rpc <=> today ROI = -1.
# * found another way — CH.7d (end-of-day totals) and CH.7e (rule snapshots).

# %% CH.7d  DELAY, END-OF-DAY — do the last days look short on conversions/revenue?
q("""
SELECT date,
       ROUND(SUM(spend))                                                      AS spend,
       ROUND(SAFE_DIVIDE(SUM(revenue), SUM(spend)), 3)                        AS roas,
       SUM(fb_conversions)                                                    AS fb_conv,
       ROUND(SUM(estimated_conversions))                                      AS est_conv,
       ROUND(SAFE_DIVIDE(SUM(estimated_conversions), SUM(fb_conversions)), 3) AS est_over_fb,
       ROUND(SAFE_DIVIDE(SUM(revenue), SUM(estimated_conversions)), 3)        AS rev_per_est,
       COUNTIF(spend = 0 AND fb_conversions > 0)                              AS late_fb_conv_rows,
       COUNTIF(spend = 0 AND revenue > 0)                                     AS late_rev_rows,
       COUNTIF(spend > 0 AND fb_conversions > 0 AND revenue = 0)              AS conv_no_rev_rows
FROM $.performance_scoped GROUP BY date ORDER BY date
""")
# * no end-of-week hole: 06-12 ROAS 1.06, rev/conv 0.45 — in line with the week.
# * est/fb steady ~1.045 every day -> FB is not lagging the internal model day-to-day.
# ! 06-11 is the odd day: est/fb 1.10, rev/conv 0.54, all accounts -> looks like a catch-up.
# * zero-spend rows with conversions: 2-6 a day, spread evenly -> not a lag pile-up.
# ! 06-06: 10 rows with conversions but $0 revenue — the most of any day.
# ? the file is a settled snapshot; the delay has to be seen at decision time -> CH.7e.

# %% CH.7e1  DELAY, AFTER THE DAY — engine's 3-day view vs final revenue
# ? last_3_days_* is what the engine saw. Spend has no delay, so it tells us the window;
# ? ROI then tells us whether revenue for those days had already fully arrived.
q("""
WITH w AS (
  SELECT rx.action_time, rx.adset_id,
         rx.last_3_days_spend_at_action AS seen_spend, rx.last_3_days_roi_at_action AS seen_roi,
         SUM(IF(CAST(p.date AS DATE) BETWEEN DATE_SUB(CAST(rx.action_date AS DATE), INTERVAL 3 DAY)
                                         AND DATE_SUB(CAST(rx.action_date AS DATE), INTERVAL 1 DAY), p.spend, 0))   AS final_spend,
         SUM(IF(CAST(p.date AS DATE) BETWEEN DATE_SUB(CAST(rx.action_date AS DATE), INTERVAL 3 DAY)
                                         AND DATE_SUB(CAST(rx.action_date AS DATE), INTERVAL 1 DAY), p.revenue, 0)) AS final_rev,
         COUNT(DISTINCT IF(CAST(p.date AS DATE) BETWEEN DATE_SUB(CAST(rx.action_date AS DATE), INTERVAL 3 DAY)
                                                    AND DATE_SUB(CAST(rx.action_date AS DATE), INTERVAL 1 DAY), p.date, NULL)) AS days_in_data
  FROM $.rule_executions_scoped rx JOIN $.performance_scoped p USING (adset_id)
  WHERE rx.last_3_days_spend_at_action IS NOT NULL
  GROUP BY 1, 2, 3, 4
)
SELECT COUNT(*)                                                               AS rows_tested,
       COUNT(DISTINCT adset_id)                                               AS adsets,
       COUNTIF(ABS(SAFE_DIVIDE(seen_spend, final_spend) - 1) < 0.02)          AS spend_matches_prev_3_days,
       COUNTIF(final_spend >= 1)                                              AS rows_spend_over_1usd,
       COUNTIF(final_spend >= 1
           AND ABS(seen_roi - SAFE_DIVIDE(final_rev - final_spend, final_spend)) <= 0.015) AS roi_matches_final,
       STRING_AGG(IF(final_spend >= 1
           AND ABS(seen_roi - SAFE_DIVIDE(final_rev - final_spend, final_spend)) > 0.015,
           CONCAT(action_time, ' seen ', CAST(seen_roi AS STRING), ' final ',
                  CAST(ROUND(SAFE_DIVIDE(final_rev - final_spend, final_spend), 2) AS STRING)), NULL)) AS misses
FROM w WHERE days_in_data = 3
""")
# * spend matches the 3 days BEFORE action_date on 31/31 -> last_3_days_* = d-3..d-1, today excluded.
# * ROI matches final on 27/29 (2 rows dropped: $0.03 spend, rounding noise).
# * so revenue for a finished day is complete by the next day — no multi-day backfill.
# ! both misses fired 22:30-23:30 UTC, logged on the next date: the "previous day" was
# ! still arriving (06-11 seen 0.05, final 0.39). Rollover decisions read unsettled revenue.
# ! last_3_days_revenue_at_action is 2-5x performance revenue and grows intraday — a different
# ! measure, not usable. Small sample: 31 rows, 8 adsets (the rest had < 3 days of history).

# %% CH.7e2  DELAY, INSIDE THE DAY — revenue seen at action vs the day's final
# ? revenue at action = spend_at_action * (1 + today_roi_at_action).
q("""
WITH p AS (SELECT adset_id, date, SUM(spend) AS spend, SUM(revenue) AS revenue
           FROM $.performance_scoped GROUP BY 1, 2),
b AS (
  SELECT CASE WHEN EXTRACT(HOUR FROM TIMESTAMP(rx.action_time)) < 7  THEN '1) 00-06 UTC'
              WHEN EXTRACT(HOUR FROM TIMESTAMP(rx.action_time)) < 13 THEN '2) 07-12 UTC'
              WHEN EXTRACT(HOUR FROM TIMESTAMP(rx.action_time)) < 21 THEN '3) 13-20 UTC'
              ELSE '4) 21-23 UTC (next reporting date)' END AS time_band,
         rx.spend_at_action, rx.spend_at_action * (1 + rx.today_roi_at_action) AS rev_at_action,
         p.spend AS final_spend, p.revenue AS final_rev
  FROM $.rule_executions_scoped rx
  JOIN p ON p.adset_id = rx.adset_id AND CAST(p.date AS DATE) = CAST(rx.action_date AS DATE)
  WHERE rx.today_roi_at_action IS NOT NULL AND p.spend > 0
)
SELECT time_band, COUNT(*) AS executions,
       ROUND(SAFE_DIVIDE(SUM(spend_at_action), SUM(final_spend)), 2) AS spend_share_seen,
       ROUND(SAFE_DIVIDE(SUM(rev_at_action), SUM(final_rev)), 2)     AS revenue_share_seen,
       ROUND(SAFE_DIVIDE(SUM(rev_at_action), SUM(spend_at_action)), 2) AS roas_at_action,
       ROUND(SAFE_DIVIDE(SUM(final_rev), SUM(final_spend)), 2)       AS roas_final
FROM b GROUP BY 1 ORDER BY 1
""")
# ! revenue arrives behind spend inside the day. ROAS at action vs final:
# ! 00-06 UTC 0.85 vs 1.09 | 07-12 UTC 0.54 vs 0.68 | 21-23 UTC 0.24 vs 1.16.
# * 13-20 UTC (117 of 214 firings): 0.74 vs 0.73 — by then revenue has caught up.
# ! 21-23 UTC: 85% of the day's spend seen but only 18% of its revenue -> worst read.
# * THE DELAY: intraday, closes by ~13 UTC or the next day. Early and rollover firings judge
# * ROI on missing revenue -> look worse than they are. Flag these in rule analysis.
# ? FB conversion delay can't be tested here: rule_executions has no conversion columns.


# =============================================================================
#  CH.8  VALIDATE THE CLEANING — did the views remove exactly what we meant?
# =============================================================================

# %% CH.8a  KEYS & IDS — dedup worked, no hidden id problems, nothing lost downstream
q(r"""
SELECT 'performance' AS t, COUNTIF(adset_id != TRIM(adset_id)) AS id_whitespace,
       COUNTIF(NOT REGEXP_CONTAINS(adset_id, r'^[0-9]+$')) AS id_non_digit, COUNTIF(adset_id IS NULL) AS id_null,
       (SELECT COUNT(*) FROM $.performance_scoped) AS scoped_rows,
       (SELECT COUNT(DISTINCT CONCAT(adset_id, '|', CAST(date AS STRING))) FROM $.performance_scoped) AS scoped_keys
FROM $.performance
UNION ALL SELECT 'metadata', COUNTIF(adset_id != TRIM(adset_id)), COUNTIF(NOT REGEXP_CONTAINS(adset_id, r'^[0-9]+$')),
       COUNTIF(adset_id IS NULL), (SELECT COUNT(*) FROM $.metadata_scoped), (SELECT COUNT(DISTINCT adset_id) FROM $.metadata_scoped)
FROM $.metadata
UNION ALL SELECT 'rule_executions', COUNTIF(adset_id != TRIM(adset_id)), COUNTIF(NOT REGEXP_CONTAINS(adset_id, r'^[0-9]+$')),
       COUNTIF(adset_id IS NULL), (SELECT COUNT(*) FROM $.rule_executions_scoped), (SELECT COUNT(DISTINCT TO_JSON_STRING(r)) FROM $.rule_executions r)
FROM $.rule_executions
UNION ALL SELECT 'buyer_actions', COUNTIF(adset_id != TRIM(adset_id)), COUNTIF(NOT REGEXP_CONTAINS(adset_id, r'^[0-9]+$')),
       COUNTIF(adset_id IS NULL), (SELECT COUNT(*) FROM $.buyer_actions_scoped), NULL
FROM $.buyer_actions
""")
# ? scoped_keys: performance = distinct (adset,date); metadata = distinct adsets; rule_executions = distinct raw rows.

# %% CH.8b  WHAT THE SCOPE FILTER DROPPED — only what we meant to?
q("""
SELECT 'buyer_actions' AS t, object_type AS detail, COUNT(*) AS dropped_rows
FROM $.buyer_actions
WHERE adset_id IS NULL OR adset_id NOT IN (SELECT adset_id FROM $.performance_scoped)
GROUP BY object_type
UNION ALL
SELECT 'metadata', CONCAT(account_name, ' id_len ', CAST(id_len AS STRING)), COUNT(*)
FROM (SELECT account_name, LENGTH(adset_id) AS id_len FROM $.metadata
      WHERE adset_id NOT IN (SELECT adset_id FROM $.performance_scoped))
GROUP BY account_name, id_len
UNION ALL
SELECT 'performance', 'adsets with zero spend all week', COUNT(*)
FROM (SELECT adset_id FROM $.performance_scoped GROUP BY adset_id HAVING SUM(spend) = 0)
ORDER BY t, detail
""")

# %% CH.8c  METRIC SANITY — do the numbers agree with each other?
q("""
SELECT COUNTIF(spend < 0 OR revenue < 0 OR clicks < 0 OR fb_conversions < 0)                 AS negatives,
       COUNTIF(ABS(profit - (revenue - spend)) > 0.01)                                      AS profit_mismatch,
       COUNTIF(spend > 0 AND ABS(roi - SAFE_DIVIDE(revenue - spend, spend)) > 0.01)         AS roi_mismatch,
       COUNTIF(clicks > impressions)                                                        AS clicks_gt_impressions,
       COUNTIF(fb_conversions > clicks)                                                     AS fb_conv_gt_clicks,
       COUNT(DISTINCT IF(fb_conversions > clicks, account_name, NULL))                      AS fb_conv_gt_clicks_accounts
FROM $.performance_scoped
""")

# %% CH.8d  OUTLIER — how big is adset 31302925337341 inside ACC-04?
q("""
WITH a AS (SELECT adset_id, SUM(spend) AS spend, SUM(revenue) AS revenue, COUNTIF(spend > 0) AS spend_days
           FROM $.performance_scoped WHERE account_name = 'ACC-04' GROUP BY adset_id)
SELECT ROUND(MAX(IF(adset_id = '31302925337341', spend, NULL)))                         AS adset_spend,
       ROUND(MAX(IF(adset_id = '31302925337341', SAFE_DIVIDE(revenue, spend), NULL)), 2) AS adset_roas,
       MAX(IF(adset_id = '31302925337341', spend_days, NULL))                           AS adset_spend_days,
       ROUND(SUM(spend))                                                                AS acc04_spend,
       ROUND(SAFE_DIVIDE(MAX(IF(adset_id = '31302925337341', spend, NULL)), SUM(spend)), 2) AS share_of_acc04,
       ROUND(APPROX_QUANTILES(spend, 100)[OFFSET(50)], 1)                               AS median_adset_spend,
       ROUND(MAX(IF(adset_id != '31302925337341', spend, NULL)))                        AS next_biggest_adset
FROM a
""")
