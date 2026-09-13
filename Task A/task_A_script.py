# %%
"""Task A — how much money did rule-driven actions save or burn?

Reads the clean *_scoped views only (built in task_a_recon.py CH.2).
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

# %% LOAD — the clean views exist and hold what recon left
q("""
SELECT 'performance_scoped' AS view, COUNT(*) AS row_count, COUNT(DISTINCT adset_id) AS adsets FROM $.performance_scoped
UNION ALL SELECT 'rule_executions_scoped', COUNT(*), COUNT(DISTINCT adset_id) FROM $.rule_executions_scoped
UNION ALL SELECT 'metadata_scoped',        COUNT(*), COUNT(DISTINCT adset_id) FROM $.metadata_scoped
UNION ALL SELECT 'buyer_actions_scoped',   COUNT(*), COUNT(DISTINCT adset_id) FROM $.buyer_actions_scoped
UNION ALL SELECT 'auto_rules',             COUNT(*), NULL                     FROM $.auto_rules
""")
# * performance 4875 rows / 1000 adsets, rule_executions 214 / 75, metadata 1000 / 1000,
# * buyer_actions 715 / 185, auto_rules 12. Matches recon CH.2b.


# =============================================================================
#  SEGMENTS — drill down on the numbers before judging rules
# =============================================================================

# %% SEG.1  BY ACCOUNT — where do rules fire, and where is the money?
q("""
WITH acc AS (SELECT DISTINCT adset_id, account_name FROM $.performance_scoped),
rx AS (
  SELECT acc.account_name, COUNT(*) AS rule_firings, COUNTIF(r.response = 'SUCCESS') AS rule_success,
         COUNT(DISTINCT IF(r.response = 'SUCCESS', r.adset_id, NULL)) AS adsets_acted
  FROM $.rule_executions_scoped r JOIN acc USING (adset_id) GROUP BY 1
)
SELECT p.account_name,
       COUNT(DISTINCT p.adset_id)                              AS adsets,
       COUNT(DISTINCT IF(p.spend > 0, p.adset_id, NULL))       AS adsets_spent,
       ROUND(SUM(p.spend))                                     AS spend,
       ROUND(SUM(p.revenue) - SUM(p.spend))                    AS profit,
       ROUND(SAFE_DIVIDE(SUM(p.revenue), SUM(p.spend)) - 1, 3) AS roi,
       ANY_VALUE(COALESCE(rx.rule_firings, 0))                 AS rule_firings,
       ANY_VALUE(COALESCE(rx.rule_success, 0))                 AS rule_success,
       ANY_VALUE(COALESCE(rx.adsets_acted, 0))                 AS adsets_acted
FROM $.performance_scoped p LEFT JOIN rx USING (account_name)
GROUP BY 1 ORDER BY 1
""")

# %% SEG.2  ACC-04 BY DAY — activity vs winners/losers
# ? active = spend > 0 · acted = SUCCESS firing · win / lose = day profit > 0 / < 0
# ? rule days keyed on action_date (reporting date), not UTC action_time
q("""
WITH p AS (
  SELECT CAST(date AS DATE) AS date,
         COUNTIF(spend > 0)                         AS active_adsets,
         COUNTIF(spend > 0 AND revenue - spend > 0) AS winning_adsets,
         COUNTIF(spend > 0 AND revenue - spend < 0) AS losing_adsets,
         ROUND(SUM(spend))                          AS spend,
         ROUND(SUM(revenue) - SUM(spend))           AS profit,
         ROUND(SAFE_DIVIDE(SUM(revenue), SUM(spend)) - 1, 3) AS roi
  FROM $.performance_scoped WHERE account_name = 'ACC-04' GROUP BY 1
),
r AS (
  SELECT CAST(action_date AS DATE) AS date,
         COUNT(*)                                                   AS rule_firings,
         COUNTIF(response = 'SUCCESS')                              AS rule_success,
         COUNTIF(response != 'SUCCESS')                             AS rule_failed,
         COUNT(DISTINCT IF(response = 'SUCCESS', adset_id, NULL))   AS adsets_acted
  FROM $.rule_executions_scoped GROUP BY 1
)
SELECT p.date, p.active_adsets, COALESCE(r.adsets_acted, 0) AS adsets_acted,
       COALESCE(r.rule_firings, 0) AS rule_firings, COALESCE(r.rule_success, 0) AS rule_success,
       COALESCE(r.rule_failed, 0) AS rule_failed,
       p.winning_adsets, p.losing_adsets, p.spend, p.profit, p.roi
FROM p LEFT JOIN r USING (date) ORDER BY p.date
""")


# =============================================================================
#  RULES — what each rule did, and who it hit
# =============================================================================

# %% RULE.1  RULE VIEW — firings, and were the acted adsets losers or winners?
# ? decision = rule x adset x action_date; repeats = firings - decisions.
# ? loser / winner split on SUCCESS decisions only (failed runs changed nothing):
# ?   at action  = today_roi_at_action of the first SUCCESS firing  (< 0 loser, >= 0 winner)
# ?   end of day = that adset-day's final profit in performance      (< 0 loser, >= 0 winner)
# ?   spend_eod / profit_eod = full action-day totals of the acted adsets (before + after the action)
q("""
WITH rx AS (
  SELECT rule_id, adset_id, CAST(action_date AS DATE) AS date, action_time, response, today_roi_at_action,
         ROW_NUMBER() OVER (PARTITION BY rule_id, adset_id, action_date, response = 'SUCCESS'
                            ORDER BY action_time) AS nth
  FROM $.rule_executions_scoped
),
fired AS (
  SELECT rule_id, COUNT(DISTINCT adset_id) AS unique_adsets, COUNT(*) AS firings,
         COUNTIF(response = 'SUCCESS') AS successes, COUNTIF(response != 'SUCCESS') AS fails,
         COUNT(*) - COUNT(DISTINCT CONCAT(adset_id, CAST(date AS STRING))) AS repeats
  FROM rx GROUP BY rule_id
),
dec AS (
  SELECT rx.rule_id, rx.today_roi_at_action AS roi_at_action,
         p.spend, p.revenue, p.revenue - p.spend AS eod_profit
  FROM rx JOIN $.performance_scoped p
    ON p.adset_id = rx.adset_id AND CAST(p.date AS DATE) = rx.date
  WHERE rx.response = 'SUCCESS' AND rx.nth = 1
),
split AS (
  SELECT rule_id, COUNT(*) AS success_decisions,
         COUNTIF(roi_at_action < 0)  AS losers_at_action,
         COUNTIF(roi_at_action >= 0) AS winners_at_action,
         COUNTIF(eod_profit < 0)     AS losers_eod,
         COUNTIF(eod_profit >= 0)    AS winners_eod,
         COUNTIF(roi_at_action < 0 AND eod_profit >= 0) AS loser_turned_winner,
         ROUND(SUM(spend))                                   AS spend_eod,
         ROUND(SUM(eod_profit))                              AS profit_eod,
         ROUND(SAFE_DIVIDE(SUM(revenue), SUM(spend)) - 1, 3) AS roi_eod
  FROM dec GROUP BY rule_id
)
SELECT r.rule_id, r.action, r.rule_name AS definition,
       f.unique_adsets, f.firings, f.successes, f.fails, f.repeats,
       s.success_decisions, s.losers_at_action, s.winners_at_action,
       s.losers_eod, s.winners_eod, s.loser_turned_winner, s.spend_eod, s.profit_eod, s.roi_eod
FROM $.auto_rules r
LEFT JOIN fired f USING (rule_id) LEFT JOIN split s USING (rule_id)
ORDER BY r.rule_id
""")

# %% RULE.2  COST OF CUTTING WINNERS — flippers only (loser at action, winner at end of day)
# ? decision = rule x adset x action_date, SUCCESS firings only.
# ? budget removed:
# ?   Turn OFF   = live budget at first firing x share of day left (1 - spend_at_action / live budget)
# ?   Decrease   = live budget at first firing - last set_budget that day; counts only if the
# ?                day's spend reached >= 95% of that last set budget (the cap bit), else $0
# ? missed income = budget removed x end-of-day ROI x 0.9  (0.9: extra budget earns less than average)
# ! upper bound on the cost side only — savings on losers that stayed losers are not here.
q("""
WITH rx AS (
  SELECT rule_id, action_name, adset_id, CAST(action_date AS DATE) AS date, action_time,
         spend_at_action, today_roi_at_action, current_budget_from_fb, set_budget
  FROM $.rule_executions_scoped WHERE response = 'SUCCESS'
),
d AS (
  SELECT rule_id, adset_id, date, ANY_VALUE(action_name) AS action,
         ARRAY_AGG(STRUCT(action_time, today_roi_at_action AS roi, current_budget_from_fb AS live,
                          spend_at_action AS spent) ORDER BY action_time LIMIT 1)[OFFSET(0)] AS first,
         ARRAY_AGG(set_budget IGNORE NULLS ORDER BY action_time DESC LIMIT 1)[SAFE_OFFSET(0)] AS last_set
  FROM rx GROUP BY 1, 2, 3
),
j AS (
  SELECT d.*, p.spend AS day_spend, p.revenue - p.spend AS day_profit,
         SAFE_DIVIDE(p.revenue - p.spend, p.spend) AS eod_roi,
         GREATEST(0, 1 - SAFE_DIVIDE(d.first.spent, d.first.live)) AS share_day_left
  FROM d JOIN $.performance_scoped p ON p.adset_id = d.adset_id AND CAST(p.date AS DATE) = d.date
),
f AS (
  SELECT *,
         IF(action = 'Turn OFF', first.live * share_day_left, first.live - last_set) AS budget_removed,
         IF(action = 'Turn OFF', NULL, day_spend >= 0.95 * last_set)                AS cap_bit
  FROM j WHERE first.roi < 0 AND day_profit >= 0
)
SELECT rule_id, action, adset_id, date, first.action_time AS first_firing,
       first.roi AS roi_at_action, ROUND(eod_roi, 3) AS roi_eod,
       ROUND(day_spend, 2) AS day_spend, ROUND(first.live, 2) AS live_budget, ROUND(last_set, 2) AS last_set_budget,
       ROUND(share_day_left, 2) AS share_day_left, cap_bit, ROUND(budget_removed, 2) AS budget_removed,
       ROUND(IF(action = 'Turn OFF' OR cap_bit, budget_removed, 0) * eod_roi * 0.9, 2) AS missed_income
FROM f ORDER BY missed_income DESC
""")

# %% RULE.3  SAVINGS FROM CUTTING LOSERS — loser at action AND loser at end of day
# ? same decisions and budget removed as RULE.2 (first SUCCESS firing of rule x adset x action_date):
# ?   Turn OFF = live budget x share of day left · Decrease = live - last set_budget, only if cap bit (>= 95%)
# ? saving = budget removed x -(end-of-day ROI). No 0.9: a loser's extra budget is not extra income,
# ?   it likely loses at least its average -> x1.0 is the conservative choice.
# ? day-1 turn-offs x 0.65: outside ACC-04, day-1 adsets with budget <= $5 (all R04 budgets) spend 65%
# ?   of their budget; older adsets spend all of it (x 1.0). Cuts need no factor: the cap-bit check covers it.
# ? excluded: winner at action (1 R10 decision), and flippers (RULE.2).
q("""
WITH rx AS (
  SELECT rule_id, action_name, adset_id, CAST(action_date AS DATE) AS date, action_time,
         spend_at_action, today_roi_at_action, current_budget_from_fb, set_budget
  FROM $.rule_executions_scoped WHERE response = 'SUCCESS'
),
d AS (
  SELECT rule_id, adset_id, date, ANY_VALUE(action_name) AS action,
         ARRAY_AGG(STRUCT(action_time, today_roi_at_action AS roi, current_budget_from_fb AS live,
                          spend_at_action AS spent) ORDER BY action_time LIMIT 1)[OFFSET(0)] AS first,
         ARRAY_AGG(set_budget IGNORE NULLS ORDER BY action_time DESC LIMIT 1)[SAFE_OFFSET(0)] AS last_set
  FROM rx GROUP BY 1, 2, 3
),
j AS (
  SELECT d.*, p.spend AS day_spend, p.revenue - p.spend AS day_profit,
         SAFE_DIVIDE(p.revenue - p.spend, p.spend) AS eod_roi, p.spend_day_no,
         GREATEST(0, 1 - SAFE_DIVIDE(d.first.spent, d.first.live)) AS share_day_left
  FROM d JOIN $.performance_scoped p ON p.adset_id = d.adset_id AND CAST(p.date AS DATE) = d.date
),
f AS (
  SELECT *,
         IF(action = 'Turn OFF', first.live * share_day_left * IF(spend_day_no = 1, 0.65, 1),
            first.live - last_set)                                             AS budget_removed,
         IF(action = 'Turn OFF', TRUE, day_spend >= 0.95 * last_set)                AS counts
  FROM j WHERE first.roi < 0 AND day_profit < 0
)
SELECT rule_id, ANY_VALUE(action) AS action, COUNT(*) AS decisions, COUNTIF(spend_day_no = 1) AS day1,
       COUNTIF(counts) AS decisions_counted,
       ROUND(SUM(day_spend), 2) AS day_spend,
       ROUND(SAFE_DIVIDE(SUM(day_spend + day_profit), SUM(day_spend)) - 1, 3) AS roi_eod,
       ROUND(SUM(IF(counts, budget_removed, 0)), 2) AS budget_removed,
       ROUND(SUM(IF(counts, budget_removed, 0) * -eod_roi), 2) AS saving
FROM f GROUP BY rule_id ORDER BY saving DESC
""")


# =============================================================================
#  RULE BY RULE — one rule at a time: check what it hit, decide how to value it,
#  give it an outcome. The action-day totals above (RULE.2 / RULE.3) are not the
#  final value: turn-offs mostly cost or save on the days AFTER the action.
# =============================================================================

# %% RBR  DECISIONS OF ONE RULE — engine view at fire time vs the day's close
RULE = "R01"
# ? one row per decision (rule x adset x action_date), first SUCCESS firing.
# ? revenue at fire = spend_at_action x (1 + today_roi_at_action).
q(f"""
WITH d AS (
  SELECT adset_id, CAST(action_date AS DATE) AS date,
         ARRAY_AGG(STRUCT(action_time, last_3_days_roi_at_action AS roi_3d, today_roi_at_action AS roi,
                          spend_at_action AS spent) ORDER BY action_time LIMIT 1)[OFFSET(0)].*
  FROM $.rule_executions_scoped WHERE rule_id = '{RULE}' AND response = 'SUCCESS'
  GROUP BY 1, 2
)
SELECT d.adset_id, d.date, d.action_time AS fired_utc,
       d.roi_3d                                                  AS roi_3d_at_fire,
       d.roi                                                     AS roi_at_fire,
       ROUND(SAFE_DIVIDE(p.revenue - p.spend, p.spend), 3)       AS roi_at_close,
       ROUND(d.spent, 2)                                         AS spent_at_fire,
       ROUND(p.spend, 2)                                         AS spent_at_close,
       ROUND(d.spent * (1 + d.roi), 2)                           AS revenue_at_fire,
       ROUND(p.revenue, 2)                                       AS revenue_at_close
FROM d JOIN $.performance_scoped p ON p.adset_id = d.adset_id AND CAST(p.date AS DATE) = d.date
ORDER BY d.action_time
""")
# * R01 (Turn OFF | Total Days >= 5): 4 firings, 4 success, 0 fail, 3 adsets / 3 decisions.
# *   31167350331032  06-11 02:00  3d -58%  fire -100%  close -100%  spent 0.71 -> 0.93   right: dying
# *   31191755212537  06-11 23:30  3d  +5%  fire  -47%  close  +30%  spent 8.38 -> 9.45   wrong: revenue
# *                   4.44 at fire -> 12.28 at close ($7.84 arrived after the turn-off). Delay.
# *   31626016833981  06-12 16:30  3d -11%  fire  -15%  close  -15%  spent 20.28 -> 20.22 reasonable
# *   total: ROI at fire -26%, at close -4% (break-even), spent $29.37 -> $30.60.
# ! fired on only 3 of 65 age-5+ adset-days, all on 06-11/06-12 — likely switched on ~06-11.
# ! definition identical in auto_rules / rule_name / condition_name: no hidden condition logged.
# ! 2 of 3 decisions on 06-12 (last data day): no after-window to value them.

# %% RBR.2  MET THE CONDITION BUT THE RULE DID NOT FIRE — ACC-04 adset-days, accumulated ROI
CONDITION = "p.spend_day_no >= 5"  # R01 as named: Total Days >= 5
# ? adset-days in ACC-04 with spend that meet the condition on end-of-day numbers.
# ? accumulated ROI = SUM(revenue) / SUM(spend) - 1 (never an average of daily ROIs).
q(f"""
WITH hit AS (
  SELECT DISTINCT adset_id, CAST(action_date AS DATE) AS date
  FROM $.rule_executions_scoped WHERE rule_id = '{RULE}' AND response = 'SUCCESS'
),
days AS (
  SELECT p.adset_id, p.spend, p.revenue,
         IF(h.adset_id IS NOT NULL, 'fired', 'did not fire')          AS fired,
         IF(p.revenue - p.spend < 0, 'losing', 'winning')             AS close_result
  FROM $.performance_scoped p
  LEFT JOIN hit h ON h.adset_id = p.adset_id AND h.date = CAST(p.date AS DATE)
  WHERE p.account_name = 'ACC-04' AND p.spend > 0 AND {CONDITION}
)
SELECT IFNULL(fired, 'ALL') AS rule_fired, IFNULL(close_result, 'all') AS day_close,
       COUNT(*)                                             AS adset_days,
       COUNT(DISTINCT adset_id)                             AS adsets,
       ROUND(SUM(spend), 2)                                 AS spend,
       ROUND(SUM(revenue), 2)                               AS revenue,
       ROUND(SUM(revenue) - SUM(spend), 2)                  AS profit,
       ROUND(SAFE_DIVIDE(SUM(revenue), SUM(spend)) - 1, 3)  AS accumulated_roi
FROM days
GROUP BY ROLLUP(fired, close_result)
ORDER BY fired, close_result
""")
# * ACC-04 adset-days aged 5+ with spend: 65 (20 adsets), $2,066 spend, +$383, accumulated ROI +18.6%.
# *   fired        3 days  $31    -$1   ROI  -3.7%  (losing 2: -18.8% · winning 1: +30.0%)
# *   did not fire 62 days $2,036 +$384 ROI +18.9%  (losing 27 / 18 adsets: -$90, -11.3%
# *                                                  · winning 35 / 15 adsets: +$475, +38.4%)
# * as named, R01 would have turned off a pool earning +18.9% — the rule as it ran touched 1.5% of it.
