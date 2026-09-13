# Dataset Summary — Automated Adset Budget Optimization

## 1. Overview

This dataset describes an **automated advertising budget optimization system** operating on Meta/Facebook adsets.

The system combines:

* Adset/campaign metadata
* Daily advertising performance
* Automated optimization rules
* Rule executions
* Manual/buyer budget actions

The main business goal appears to be:

> **Automatically increase, decrease, turn off, or turn on adsets based on their performance and profitability.**

The data covers multiple Facebook ad accounts and a relatively small performance window of **June 6–12, 2026**, while the metadata contains campaigns created as far back as December 2025.

---

# 2. Files

| File                          |  Rows | Columns | Main Purpose                              |
| ----------------------------- | ----: | ------: | ----------------------------------------- |
| `auto_rules.csv`              |    12 |       6 | Defines the automation rules              |
| `buyer_actions.csv`           | 1,001 |       7 | Manual/user budget changes                |
| `daily_adset_performance.csv` | 4,947 |      18 | Daily adset performance                   |
| `rule_executions.csv`         |   214 |      27 | Actual automated rule executions          |
| `campaign_adset_metadata.csv` | 7,129 |      18 | Campaign/adset configuration and metadata |

---

# 3. Core Business Model

The basic flow is:

```text
Campaign / Adset
       |
       v
Daily Performance
       |
       +--> Spend
       +--> Impressions
       +--> Clicks
       +--> Conversions
       +--> Revenue
       +--> Profit
       +--> ROI
       |
       v
Automation Rules
       |
       +--> Turn OFF
       +--> Turn ON
       +--> Decrease Budget
       |
       v
Rule Execution
       |
       v
Facebook / Meta Budget Change
```

There is also a parallel **manual buyer-action** process:

```text
Buyer / User
     |
     v
Manual Budget Action
     |
     v
Adset / Campaign Budget Change
```

---

# 4. Main Entities

## Adset

The central entity in the dataset.

`adset_id` connects:

* Metadata
* Daily performance
* Automated rule executions
* Buyer actions

The metadata contains **7,129 unique adsets**.

---

## Campaign

Campaigns are also represented through `campaign_id`.

The metadata contains **7,129 unique campaign IDs**, although the relationship between campaign and adset appears unusual because each row has a unique campaign ID in this dataset.

---

## Account

There are **6 advertising accounts** in the performance and metadata data.

Examples:

```text
ACC-01
ACC-02
ACC-03
ACC-04
ACC-05
ACC-06
```

---

# 5. `daily_adset_performance.csv`

This is the main performance fact table.

### Grain

Approximately:

> **One adset × one day**

It contains 4,947 rows covering **June 6–12, 2026**.

### Main fields

| Category       | Fields                                         |
| -------------- | ---------------------------------------------- |
| Identification | `adset_id`, `fb_ad_account_id`, `account_name` |
| Date           | `date`                                         |
| Spend          | `spend`                                        |
| Traffic        | `impressions`, `clicks`                        |
| Conversions    | `fb_conversions`, `estimated_conversions`      |
| Revenue        | `revenue`                                      |
| Profitability  | `profit`, `roi`                                |
| Efficiency     | `rpc`, `cpa`                                   |
| Funnel rates   | `ctr`, `cr`                                    |
| Lifecycle      | `first_spend_date`, `spend_day_no`             |

### KPI formulas

The dataset validates these formulas:

| KPI    | Formula                           |
| ------ | --------------------------------- |
| Profit | `revenue - spend`                 |
| ROI    | `profit / spend`                  |
| RPC    | `revenue / estimated_conversions` |
| CPA    | `spend / estimated_conversions`   |
| CTR    | `clicks / impressions`            |
| CR     | `estimated_conversions / clicks`  |

Most formulas match their source fields exactly.

**Exception:** `cr` has 232 mismatches among 1,843 comparable rows (~12.6%).

---

# 6. Performance Characteristics

The performance data is highly sparse.

For example:

| Metric         | Zero values |
| -------------- | ----------: |
| Spend          |       60.6% |
| Impressions    |       59.7% |
| Clicks         |       62.6% |
| FB conversions |       70.8% |
| Revenue        |       14.7% |

Revenue, profit and estimated-conversion fields also contain many NULLs.

### Important implication

The dataset appears to contain many adsets that are technically present but **not actively delivering/spending on a particular day**.

Therefore, calculating averages across all rows can be misleading.

For example:

```text
Average CPA across all rows
```

is probably less useful than:

```text
CPA among adsets with spend > 0
```

---

# 7. Profitability

`profit` ranges from:

```text
-26.09 → +107.24
```

There are:

* 1,320 negative-profit observations
* 274 zero-profit observations
* 632 positive-profit observations approximately

ROI ranges from:

```text
-1.00 → 23.55
```

The distribution is highly skewed, with many zero/negative observations and a small number of very high ROI observations.

This is important when using:

* Mean ROI
* Mean CPA
* Mean RPC

A weighted or aggregate calculation may be more meaningful than a simple row-level average.

---

# 8. `campaign_adset_metadata.csv`

This is the main configuration/dimension table.

It contains:

**7,129 rows × 18 columns**

### Main fields

| Area           | Fields                                    |
| -------------- | ----------------------------------------- |
| Identification | `account_name`, `campaign_id`, `adset_id` |
| Names          | `campaign_name`, `adset_name`             |
| Status         | `effective_status`, `delivery_status`     |
| Budget         | `daily_budget`, `bid_amount`              |
| Bidding        | `bid_strategy`                            |
| Budget model   | `budget_optimization`                     |
| ROAS           | `roas_target`                             |
| Objective      | `objective`                               |
| Optimization   | `optimization_goal`                       |
| Geography      | `geo_countries`                           |
| Language       | `language`                                |
| Dates          | `creation_date`, `start_time`             |

---

# 9. Adset Status

Current effective status:

| Status  | Count |
| ------- | ----: |
| ACTIVE  | 4,023 |
| PAUSED  | 3,014 |
| DELETED |    92 |

Delivery status:

| Status       | Count |
| ------------ | ----: |
| ADSET_OFF    | 3,747 |
| CAMPAIGN_OFF | 2,974 |
| ACTIVE       |   305 |
| DELETED      |    92 |
| SCHEDULED    |    11 |

This suggests that **status and actual delivery are separate concepts**.

For example, an adset can be configured as active while delivery is effectively blocked at the campaign level.

---

# 10. Budget Optimization

Two budget optimization modes exist:

| Mode | Count |
| ---- | ----: |
| ABO  | 5,918 |
| CBO  | 1,211 |

Where:

* **ABO** = Ad Set Budget Optimization
* **CBO** = Campaign Budget Optimization

The dataset is therefore mostly **ABO-based**.

---

# 11. Bidding Strategy

The main bidding strategies are:

| Strategy                    | Count |
| --------------------------- | ----: |
| `LOWEST_COST_WITH_MIN_ROAS` | 3,617 |
| `LOWEST_COST_WITHOUT_CAP`   | 3,014 |
| `LOWEST_COST_WITH_BID_CAP`  |   452 |
| `COST_CAP`                  |    46 |

The vast majority use either:

```text
LOWEST_COST_WITH_MIN_ROAS
```

or

```text
LOWEST_COST_WITHOUT_CAP
```

---

# 12. Campaign Objective

Almost everything is optimized for sales:

| Objective            | Count |
| -------------------- | ----: |
| `OUTCOME_SALES`      | 7,127 |
| `OUTCOME_ENGAGEMENT` |     2 |

So this dataset is overwhelmingly a **performance/sales advertising environment**.

Optimization goals are also dominated by:

| Goal                  | Count |
| --------------------- | ----: |
| `VALUE`               | 6,567 |
| `OFFSITE_CONVERSIONS` |   559 |
| Other                 |     3 |

---

# 13. ROAS Targets

`roas_target` is populated for roughly half of the rows.

Important values include:

```text
0.3
0.6
0.7
0.9
1.1
...
```

There are also some very low targets, such as:

```text
0.007
0.0073
0.0089
```

These should probably be investigated before assuming they represent normal business targets.

---

# 14. `auto_rules.csv`

This table defines the automation logic.

There are:

**12 rules**

Every rule:

* Runs every **30 minutes**
* Applies to **OWN RSOC adsets**
* Covers all accounts

### Available actions

| Action        | Number of rules |
| ------------- | --------------: |
| Turn OFF      |               7 |
| Decrease -40% |               2 |
| Decrease -20% |               1 |
| Turn ON       |               1 |
| Decrease -15% |               1 |

---

# 15. Examples of Automation Rules

The rules use performance conditions such as:

### Poor performance

```text
Total Days >= 5
```

→ Turn OFF

---

### Negative ROI

```text
-30 < ROI <= -10
```

→ Decrease budget by 20%

---

### No positive days

```text
positive_days = 0
AND total_days > 2
```

→ Turn OFF

---

### Very poor early performance

```text
Total Days = 1
AND budget > 35%
AND ROI < -50%
```

→ Turn OFF

---

### Negative profit / high budget consumption

```text
Total Profit <= -2.5
AND budget_usage_today >= 15%
```

→ Turn OFF

---

# 16. Rule Firings

The number of firings varies substantially.

One rule fired:

```text
109 times
```

while some fired only:

```text
1–2 times
```

The rule-firing distribution is strongly skewed.

The largest rule is:

> `Turn Off - OWN RSOC | Total Days = 1 | budget > 35% | ROI < -50%`

with **109 executions**.

This is a major candidate for analysis because it represents roughly half of all rule executions.

---

# 17. `rule_executions.csv`

This table records actual automation activity.

### Size

```text
214 executions
27 columns
```

It covers:

```text
June 6–12, 2026
```

### Important fields

| Category               | Fields                                                                                          |
| ---------------------- | ----------------------------------------------------------------------------------------------- |
| Time                   | `action_date`, `action_time`                                                                    |
| Rule                   | `rule_name`, `rule_id`, `condition_id`, `action_id`                                             |
| Entity                 | `account_id`, `adset_id`, `campaign_id`                                                         |
| Budget                 | `old_budget`, `new_budget`, `set_budget`                                                        |
| Result                 | `response`                                                                                      |
| Performance            | `spend_at_action`, `today_roi_at_action`, `today_rpc_at_action`, `today_cpa_at_action`          |
| Historical performance | `last_3_days_revenue_at_action`, `last_3_days_roi_at_action`, `last_3_days_total_roi_at_action` |
| Lifecycle              | `total_spend_at_action`, `total_days_at_action`                                                 |
| Budget                 | `current_budget_from_fb`, `budget_level`                                                        |

---

# 18. Automation Results

The 214 executions produced:

| Action        | Executions |
| ------------- | ---------: |
| Turn OFF      |        174 |
| Decrease -20% |         23 |
| Turn ON       |          8 |
| Decrease -40% |          7 |
| Decrease -15% |          2 |

So:

> **~81% of automated executions were Turn OFF actions.**

This is a very important business characteristic of the system.

---

# 19. Execution Responses

Responses include:

| Response                 | Count |
| ------------------------ | ----: |
| SUCCESS                  |   164 |
| OAuth/access-token error |    30 |
| No budget to change      |    20 |

Therefore:

* ~76.6% of executions were successful
* ~14.0% encountered authentication/token errors
* ~9.3% had no budget available to change

This is a significant operational issue.

The OAuth error appears as:

```text
access token invalidated
```

This should be investigated separately from the optimization logic itself.

---

# 20. `buyer_actions.csv`

This table captures manual actions.

### Size

```text
1,001 rows
```

### Action types

| Event                        | Count |
| ---------------------------- | ----: |
| `ui_update_budget`           |   481 |
| `ui_adjust_budget`           |   446 |
| `update_ad_set_budget`       |    48 |
| `update_campaign_budget`     |    25 |
| `update_ad_set_bid_strategy` |     1 |

Most actions are therefore performed through the UI.

---

# 21. Manual vs Automated Optimization

There are two distinct optimization mechanisms:

| Mechanism | Source                |
| --------- | --------------------- |
| Automated | `rule_executions.csv` |
| Manual    | `buyer_actions.csv`   |

This enables potentially valuable analysis such as:

```text
Manual action
      ↓
Performance change
      ↓
Subsequent automated action
      ↓
Performance change
```

This could help determine whether automation is:

* Complementing human decisions
* Undoing human decisions
* Reacting to human changes
* Producing excessive budget churn

---

# 22. Data Relationships

The inferred data model is approximately:

```text
campaign_adset_metadata
        |
        | adset_id
        |
        +-------------------+
        |                   |
        v                   v
daily_adset_performance   rule_executions
        |
        |
        v
  buyer_actions
```

And:

```text
auto_rules
     |
     | rule_id
     v
rule_executions
```

### Main join keys

| Key           | Parent                    | Children                               |
| ------------- | ------------------------- | -------------------------------------- |
| `adset_id`    | `campaign_adset_metadata` | Performance, executions, buyer actions |
| `rule_id`     | `auto_rules`              | Rule executions                        |
| `campaign_id` | `campaign_adset_metadata` | Rule executions                        |
| `account_id`  | No clear parent           | Performance, executions                |

---

# 23. Join Coverage

`rule_id` is very clean:

* All 12 rules appear in executions
* No orphan rule IDs
* 100% parent coverage

`adset_id` is different.

Only a small subset of metadata adsets appear in the activity tables:

| Table             | Distinct adsets | Coverage of metadata |
| ----------------- | --------------: | -------------------: |
| Buyer actions     |             185 |                 2.6% |
| Daily performance |           1,000 |                14.0% |
| Rule executions   |              75 |                1.05% |

This is not necessarily a problem.

It likely means the metadata table represents a much larger universe of campaigns/adsets than the subset actively involved in the June analysis.

---

# 24. Data Quality Issues

## High Priority

### 1. Duplicate performance records

`daily_adset_performance` contains:

* 72 full-row duplicates
* 72 affected `adset_id + date` combinations
* 144 duplicated rows

The expected grain appears to be:

```text
adset_id + date
```

So these duplicates should be investigated before aggregating performance.

---

### 2. Conversion-rate inconsistencies

`cr` does not always equal:

```text
estimated_conversions / clicks
```

There are:

```text
232 mismatches
12.59% of comparable rows
```

This needs clarification before using CR as a trusted KPI.

---

### 3. OAuth failures

30 rule executions contain an authentication/token error.

This means some automation actions may have **failed operationally**, even though the underlying rule correctly triggered.

---

## Medium Priority

### 4. Large number of NULL metrics

For example, in daily performance:

* Estimated conversions: ~55% NULL
* Revenue: ~55% NULL
* Profit: ~55% NULL
* CTR: ~60% NULL
* CR: ~63% NULL

These NULLs appear strongly related to adsets/days without meaningful delivery.

---

### 5. Highly skewed distributions

Spend, conversions, revenue, ROI, CPA and RPC all have strong skew.

For example:

* Spend has ~16.99 skewness
* RPC has ~19.45 skewness
* ROI has ~11.73 skewness

Simple averages should therefore be treated carefully.

---

### 6. Metadata inconsistencies

Examples include:

* `language` values such as `en`, `EN`, and `EN `
* Many NULL `adset_name` values
* Many NULL `bid_amount` values
* Many NULL `roas_target` values

Some of these may be legitimate, but normalization would improve analysis.

---

# 25. Most Important Business Questions

This dataset is well suited to answering questions such as:

### Automation effectiveness

1. **Are automated rules improving ROI?**
2. Do adsets perform better after a rule changes their budget?
3. Does turning an adset OFF prevent future losses?
4. Are some rules firing too aggressively?

### Rule quality

5. Which rules fire most frequently?
6. Which rules generate the most successful actions?
7. Which rules produce the most failed actions?
8. Are certain rules redundant or overlapping?

### Budget optimization

9. Does increasing/decreasing budget improve profitability?
10. How often does automation fight against manual buyer actions?
11. How much budget is saved by turning poor performers OFF?
12. Are profitable adsets being turned OFF too early?

### Operational reliability

13. Why are OAuth errors occurring?
14. How often does the system attempt to change a budget that cannot be changed?
15. What percentage of triggered rules actually result in a successful Meta action?

---

# 26. Recommended Analytical Framework

For an analysis/dashboard, I would structure the data into four layers:

```text
1. BUSINESS PERFORMANCE
   ↓
Spend / Revenue / Profit / ROI

2. AD PERFORMANCE
   ↓
Impressions / Clicks / CTR / Conversions / CPA / RPC

3. AUTOMATION
   ↓
Rules / Firings / Actions / Success rate

4. HUMAN INTERACTION
   ↓
Buyer actions / Manual budget changes
```

Then connect them through:

```text
Adset
  ↓
Performance
  ↓
Decision
  ↓
Action
  ↓
Post-action performance
```

---

# 27. Best KPIs for a Dashboard

| KPI                   | Why it matters                             |
| --------------------- | ------------------------------------------ |
| Total Spend           | Scale of advertising activity              |
| Total Revenue         | Business output                            |
| Total Profit          | Actual economic result                     |
| Aggregate ROI         | Overall profitability                      |
| Active Adsets         | Current scale                              |
| Automated Actions     | Automation activity                        |
| Turn-Off Rate         | How aggressively automation cuts campaigns |
| Rule Success Rate     | Operational reliability                    |
| Automation Error Rate | Technical health                           |
| Manual Actions        | Human intervention                         |
| Budget Changes        | Optimization intensity                     |
| Post-action ROI       | Whether decisions work                     |

---

# 28. Key Takeaways

### The dataset represents an automated ad optimization system

The central business process is:

> **Measure ad performance → evaluate rules → change budgets/status → observe results.**

### Automation is highly aggressive

Most automated actions are **Turn OFF**, accounting for 174 of 214 executions.

### One rule dominates

The rule:

```text
Total Days = 1
AND budget > 35%
AND ROI < -50%
```

accounts for **109 executions**, making it the most important rule to investigate.

### Technical reliability is a problem

30 of 214 executions contain OAuth/token errors.

### The performance data needs careful aggregation

There are substantial:

* Duplicates
* NULLs
* Zero values
* Skewed distributions
* KPI inconsistencies

### The biggest analytical opportunity

The most valuable analysis is probably **not simply "which ads perform best?"**

It is:

> **"Does the automation system make better decisions than the business would have made without it?"**

That requires comparing **pre-action vs post-action performance**, ideally while controlling for adset age, spend level, rule type, and baseline performance.
