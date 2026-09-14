# %%
# Task B: first-call trigger reach and daily call volume, all 6 accounts.
# Reads performance_scoped (end-of-day values, one row per adset-day).
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

# %% Trigger variants: first calls/day and share of all loss reached
q("""
WITH p AS (SELECT * FROM $.performance_scoped WHERE spend > 0),
v AS (
  SELECT 'A new$2/-30 aged$4/-20' variant, (spend_day_no<3 AND spend>=2 AND roi<=-0.30) OR (spend_day_no>=3 AND spend>=4 AND roi<=-0.20) hit, profit FROM p
  UNION ALL SELECT 'B new$2/-30 aged$2/-20', (spend_day_no<3 AND spend>=2 AND roi<=-0.30) OR (spend_day_no>=3 AND spend>=2 AND roi<=-0.20), profit FROM p
  UNION ALL SELECT 'C new$2/-20 aged$3/-10', (spend_day_no<3 AND spend>=2 AND roi<=-0.20) OR (spend_day_no>=3 AND spend>=3 AND roi<=-0.10), profit FROM p
  UNION ALL SELECT 'D new$1/-30 aged$2/-20', (spend_day_no<3 AND spend>=1 AND roi<=-0.30) OR (spend_day_no>=3 AND spend>=2 AND roi<=-0.20), profit FROM p)
SELECT variant,
  ROUND(COUNTIF(hit)/7, 1) first_calls_per_day,
  ROUND(-SUM(IF(hit AND profit<0, profit, 0)), 0) loss_reached,
  ROUND(-SUM(IF(profit<0, profit, 0)), 0) total_loss,
  ROUND(SUM(IF(hit AND profit<0, profit, 0)) / SUM(IF(profit<0, profit, 0)) * 100, 0) pct_of_all_loss
FROM v GROUP BY 1 ORDER BY 1
""")

# %% Chosen bar (C): per day volume, repeat adsets, and the 25% per-account cap
q("""
WITH p AS (
  SELECT *, (spend_day_no<3 AND spend>=2 AND roi<=-0.20) OR (spend_day_no>=3 AND spend>=3 AND roi<=-0.10) hit
  FROM $.performance_scoped WHERE spend > 0),
d AS (SELECT account_name, date, COUNT(*) active, COUNTIF(hit) trig FROM p GROUP BY 1, 2),
t AS (SELECT date, SUM(trig) n FROM d GROUP BY 1),
a AS (SELECT adset_id, COUNT(*) n FROM p WHERE hit GROUP BY 1)
SELECT
  (SELECT ROUND(AVG(n), 1) FROM t) avg_per_day,
  (SELECT MIN(n) FROM t) min_day,
  (SELECT MAX(n) FROM t) max_day,
  (SELECT COUNT(*) FROM a) adsets,
  (SELECT COUNTIF(n > 1) FROM a) repeat_adsets,
  (SELECT ROUND(MAX(trig / active) * 100) FROM d) max_account_share_pct,
  (SELECT COUNTIF(trig > active * 0.25) FROM d) account_days_over_25pct
""")
