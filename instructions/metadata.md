# Data Metadata — Recon Reference

Structural reference for the five CSV snapshots in `data/`. Column names, dtypes as they appear in the raw files, grain, keys, and the caveats stated in `instructions/README_DATA.md`.

Observations here are from the header + first 3 rows of each file plus row counts. No cleaning, no analysis, no assumptions beyond what is visible in the raw text.

---

## `data/auto_rules.csv` — 12 rows

| column | dtype as it appears | sample |
|---|---|---|
| rule_id | string, `R01`–`R12` | `R01` |
| rule_name | string, pipe-delimited expression | `Turn OFF \| Total Days >= 5 \| OWN RSOC` |
| action | string, free-form incl. parenthetical | `Decrease -20% (min 9)` |
| schedule | string | `every 30 minutes` |
| scope | string (quoted, contains comma) | `OWN RSOC adsets, all accounts` |
| firings | integer | `4` |

**Grain:** one row = one active automation rule definition.
**PK:** `rule_id` (`rule_name` also appears unique).

---

## `data/buyer_actions.csv` — 1,001 rows

| column | dtype as it appears | sample |
|---|---|---|
| action_time | timestamp, space-separated, microseconds, `+00` offset | `2026-06-12 18:16:27.133162+00` |
| object_type | string | `adset` |
| adset_id | numeric string, 14- and 18-digit both present; **blank on some rows** | `730122709357812221`, `31190610559771` |
| event_type | string | `ui_adjust_budget` |
| old_budget | float | `19.05` |
| new_budget | float | `25.4` |
| note | string, **blank in all 3 sample rows** | *(empty)* |

**Grain:** one row = one manual action taken by a media buyer in the internal UI.
**PK:** no declared key; `(action_time, adset_id)` is the practical candidate — timestamps carry microseconds.

---

## `data/daily_adset_performance.csv` — 4,947 rows

| column | dtype as it appears | sample |
|---|---|---|
| adset_id | numeric string, 14- and 18-digit both present | `730127988250776273` |
| fb_ad_account_id | numeric string, 16-digit | `9948963373021856` |
| account_name | string | `ACC-01` |
| date | date, `YYYY-MM-DD` | `2026-06-06` |
| spend | float | `76.2762` |
| impressions | integer | `26581` |
| clicks | integer | `3377` |
| fb_conversions | integer | `363` |
| estimated_conversions | float | `375.0` |
| revenue | float | `86.4235` |
| profit | float | `10.1473` |
| roi | float (ratio) | `0.133` |
| rpc | float | `0.2305` |
| cpa | float | `0.2034` |
| ctr | float (fraction) | `0.127046` |
| cr | float (fraction) | `0.107492` |
| first_spend_date | date | `2026-05-07` |
| spend_day_no | integer | `31` |

**Grain:** one row = one adset × one reporting date. Date range 2026-06-06 → 2026-06-12.
**PK:** `(adset_id, date)`.

---

## `data/rule_executions.csv` — 214 rows

| column | dtype as it appears | sample |
|---|---|---|
| action_date | date | `2026-06-12` |
| action_time | timestamp, **ISO-8601 with `T` and `Z`** | `2026-06-12T17:00:08.000Z` |
| rule_name | string | `Turn OFF \| Total Days >= 5 \| OWN RSOC` |
| condition_name | string, **trailing space present** | `Turn OFF \| Total Days >= 5 \| OWN RSOC ` |
| action_name | string | `Turn OFF` |
| account_id | numeric string, 16-digit | `9913405683583663` |
| adset_id | numeric string, 14-digit in all samples | `31626016833981` |
| campaign_id | numeric string, 14-digit | `31237106436763` |
| old_budget | float | `39.5986` |
| new_budget | float | `31.6738` |
| set_budget | float, **blank on Turn OFF rows** | `31.6789` |
| response | string | `SUCCESS` |
| spend_at_action | float | `20.9677` |
| total_spend_at_action | float | `787.4635` |
| total_days_at_action | integer | `15` |
| today_roi_at_action | float (ratio) | `-0.18` |
| current_budget_from_fb | float | `31.6738` |
| last_3_days_revenue_at_action | float | `937.4505` |
| last_3_days_total_roi_at_action | float (ratio) | `0.19` |
| today_rpc_at_action | float | `3.0099` |
| today_cpa_at_action | float | `3.4925` |
| last_3_days_spend_at_action | float | `203.7461` |
| last_3_days_roi_at_action | float (ratio) | `-0.11` |
| budget_level | string | `adset` |
| rule_id | string | `R01` |
| condition_id | string | `C01` |
| action_id | string | `A01` |

**Grain:** one row = one rule-engine evaluation **that resulted in an action**. Evaluations that fired no action are not present.
**PK:** no declared key; `(action_time, adset_id, rule_id)` is the practical candidate. The first two sample rows are the same rule on the same adset 30 minutes apart with identical `old_budget`/`new_budget` — repeated firings are expected, not duplicates.

---

## `data/campaign_adset_metadata.csv` — 7,129 rows

| column | dtype as it appears | sample |
|---|---|---|
| account_name | string | `ACC-01` |
| campaign_id | numeric string, 18-digit | `730151843849929835` |
| adset_id | numeric string, 18-digit in samples | `730131742827261201` |
| campaign_name | string, encodes metadata | `own_rsoc_[ch=23079]_vtag:_131618_prst:315_conf:134_usr:42_MU_date:20260310_Version:2514_1762_US On_71_131618_2772597` |
| adset_name | string, same convention (campaign name minus trailing segments) | `own_rsoc_[ch=23079]_..._US On` |
| effective_status | string enum | `PAUSED`, `ACTIVE` |
| delivery_status | string enum | `CAMPAIGN_OFF`, `ADSET_OFF` |
| daily_budget | float | `635.0` |
| bid_amount | float, **blank in all 3 sample rows** | *(empty)* |
| bid_strategy | string enum | `LOWEST_COST_WITH_MIN_ROAS`, `LOWEST_COST_WITHOUT_CAP` |
| budget_optimization | string enum | `ABO` |
| roas_target | float (ratio), **blank on row 3** | `0.7` |
| objective | string enum | `OUTCOME_SALES` |
| optimization_goal | string enum | `VALUE` |
| geo_countries | **JSON array embedded as a quoted string** | `["US"]` |
| language | string | `en`, `NO_LANGUAGE` |
| creation_date | timestamp, `+00` offset | `2026-03-10 10:03:25+00` |
| start_time | timestamp, `+00` offset | `2026-03-10 10:03:27+00` |

**Grain:** one row = one adset's configuration snapshot (campaign attributes denormalized onto it).
**PK:** `adset_id`.

---

## Foreign keys between files

| from | column | to | column |
|---|---|---|---|
| `rule_executions` | `rule_id` | `auto_rules` | `rule_id` |
| `rule_executions` | `rule_name` | `auto_rules` | `rule_name` (redundant with `rule_id`) |
| `rule_executions` | `adset_id` | `daily_adset_performance` / `campaign_adset_metadata` | `adset_id` |
| `rule_executions` | `campaign_id` | `campaign_adset_metadata` | `campaign_id` |
| `rule_executions` | `account_id` | `daily_adset_performance` | `fb_ad_account_id` |
| `rule_executions` | `action_date` | `daily_adset_performance` | `date` (with `adset_id`, forms the join to that day's performance) |
| `buyer_actions` | `adset_id` | `daily_adset_performance` / `campaign_adset_metadata` | `adset_id` |
| `daily_adset_performance` | `adset_id` | `campaign_adset_metadata` | `adset_id` |
| `daily_adset_performance` | `account_name` | `campaign_adset_metadata` | `account_name` |

No lookup table exists for `condition_id` or `action_id` — `auto_rules.csv` carries only `rule_id`.

---

## What `README_DATA.md` states about issues, delays, and caveats

### Explicit warnings

- "This is production-grade data. It is not guaranteed to be clean, consistent, or complete. Treat it accordingly."
- "Adset identifiers may appear in more than one format across systems. Welcome to production." — the only named data-quality issue.

### Convention traps

Stated as conventions, but they behave like traps:

- **ROI is a ratio, not a percentage.** `0.52` = +52%, `-1.0` = spent with zero revenue. Applies to `roi`, all `*_roi_at_action` columns, and `roas_target`.
- **But ROI thresholds inside rule names are percentages** — `ROI <= -50` in a rule name means a ratio of `-0.50`. The two conventions coexist in the same analysis.
- `ctr` and `cr` are fractions, not percentages.
- `estimated_conversions` can be fractional, because the attribution model splits credit across sources; `cpa` and `cr` are derived from it, not from `fb_conversions`.
- Two competing conversion counts sit side by side: `fb_conversions` (Meta's) vs `estimated_conversions` (internal model's). The README does not say which to trust.

### Structural caveats

- `rule_executions.csv` is described as "evaluations **that resulted in an action**" — non-firing evaluations are absent by design.
- Three different budget values are documented for the same row: `old_budget`/`new_budget` (reporting system), `set_budget` (what the rule attempted), `current_budget_from_fb` (live from Meta). The README lists them as distinct sources without stating precedence.
- Rule logic is encoded in the rule *name*, "this is how it is in the real system too" — no structured condition columns.
- Metadata naming conventions "encode operational metadata (channel, vertical slug, buyer, bid type, etc.)" — parseable, but no schema is given.

### On revenue delay

`README_DATA.md` says **nothing**. It describes `revenue` as a daily total from "the internal revenue pipeline" and `estimated_conversions` as attribution-model output, but makes no claim about lag or backfill. The brief asserts revenue arrives with delay and that its characteristics are to be discovered in Task A — that characterization exists only in the data, not in the docs.
