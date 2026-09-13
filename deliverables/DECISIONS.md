## Phase 0 — recon (`task_a_recon.py`)

ive Loaded the CSVs into BigQuery and asked Claude to check that all tables connect by keys. I investigated the findings further in `task_a_recon.py. i did some back and forth prompting to grasp a hunch on the data, crystelising on insight and EDA queries.
every insight below is in py script as SQL views.

### 1. Duplicates

- **Finding:** 72 duplicate (adset_id, date) pairs, byte-identical, all in ACC-03 on 2026-06-09 (each exactly 2 rows) — one slice loaded twice, not conflicting data.
- **Decision:** drop the 72 duplicates (4947 → 4875 rows). No keep-rule needed, the copies are identical.


### 3. Accounts

- ACC-04 is the most profitable account (ROAS 1.19, $3,076 revenue on $2,586 spend).
- ACC-04 is the only account where rules run (all 214 executions); its adset IDs are all 14-digit.
- Open: were the rules aimed at the healthiest big spender, or did they make it that way?
- Accounts are 1:1 adset-to-campaign.
- One table tracked only the last date — not relevant.

### 4. Execution patterns and outliers

- 2026-06-09: all 13 executions hit one adset via one rule (R02 retrying every 30 min, "No budget to change").
- 03:30–16:30 UTC: 27 failed actions, zero successes.
- Adset 31302925337341 (ACC-04) is a spend outlier, but its numbers look valid.

### 5. Revenue delay

- **Finding:** the delay is within the day. Revenue for a finished day is complete by the next day But rules firing at 00–12 UTC or 21–23 UTC see ROI far below the day's final 
- **Decision:** flag early and rollover firings — their "profit before" reads too low, so those rules look like they stopped bigger losses than they did.

## Task 1 (`Invastigation.md`, `task_a_script.py`)

### Step 1. Segment the rules

- ive Asked Claude Code to segment the 12 rules into major groups (in invastigation.md)
- asked claude to drill down on ACC_04 becuse is the one who got the auto
 rules active. i checkd how many losers and winners adsets was each day, as well, i furthur asked it to compare to other accounts to look for a trend in winning/losing. claude answer: ACC-04's share of losing adsets drops! but also has less new adsets toword the end, but no higher Roi or less losers over the week
 - asked for rule view table :definition, unique adsets, fails, repeats, successes, losers and winners at action (ROI when the rule fired), and losers and winners at end of day (from performance).
 - estimate the cost on cutting winners (loser when the rule fired, winner by the end of the day ) 
- to decide wheather the rules did good or not ive decided to check eachrule by itself
- after ive runed the analysis for rule 1 and 2, asked it about the datasets the rule capture, data issues, roi analysis and win/lose cumpotation, ive asked claude to create a skill for easier prompt and analysis of the next rules
-after revision of rule two, i decided on calculation of lose or win 
  for cut budget rules is (ROI at close) × budget removed, counted only if the whole day's spend ≥ 95% of the new budget. Action day only.
  Turn-offrules: (the adset's average daily profit on its spend days before the action) × days left in the data. No history (day 1) → flagged, no value. No days left → $0
- ive runed the skill on all the others rule to get a assess of the rule changes.
- for Q 2. i called the skill tabels for rules 10, 1, and after reviewing the rules name and decided their are too blind to be good.


-------Task B — architecture (logged 2026-09-13 17:57) ---------------
Asked Claude to choose between prompt chaining, routing, parallelization and orchestrator-workers.

Decision: prompt chaining as the backbone, routing in code, adsets run in parallel. Orchestrator-workers rejected for the live loop — its cost is unpredictable against the $30/day cap and it has no fixed place to enforce limits.

Pushback (mine): "many agents" is mostly hype — it's LLM prompts inside a good harness. Kept the brief's role vocabulary, but the doc says only 2 roles are LLMs (Decision, Reviewer) and the rest is code.

Rejected: Claude's long, multi-section discussion replies — asked for short answers.

Decision (my design): phase 1 handles losers only. Actions: wait / diminish / pause_for X hours / revive in +30% steps up to the manager's budget. Pause only after 2 LLM interventions without recovery. The LLM is prompted again when its wait expires or ROI reverses or dips.

Changed: Claude flagged a conflict between the auto-rules and the agent and suggested locks. I chose an A/B test on different accounts instead.

Decision: test on ACC-02, a middle account, not the worst one. Claude's per-account query backed it: ACC-05 has too little spend to prove anything.

Decision: dropped the "same time yesterday" baseline — the engine's readings aren't stored and the snapshot is daily. Kept Claude's pushback: a 4 h time-of-day guard, because early-day ROI reads too low.

Decision: 30-min ROI checks only for adsets the agent is working on. Sharks (big ROI + big spend) → notify a human only.

Rejected: Claude's detailed Pydantic input/output schemas and its 9-table design — too complex for the assignment. Kept a short step / input / output flow per agent (Decision, Reviewer) and 2 tables (`interventions`, `agent_log`); more tracking tables noted for later.

Open: the §3 thresholds are Claude's starting values from ACC-02 data, not yet approved.
