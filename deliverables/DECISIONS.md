## Phase 0 — recon (`task_a_recon.py`)

I've loaded the CSVs into BigQuery and asked Claude to check that all tables connect by keys. I investigated the findings further in `task_a_recon.py`. I did some back-and-forth prompting to grasp a hunch on the data, crystallising on insights and EDA queries.
Every insight below is in the py script as SQL views.

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

- **Finding:** the delay is within the day. Revenue for a finished day is complete by the next day, but rules firing at 00–12 UTC or 21–23 UTC see ROI far below the day's final.
- **Decision:** flag early and rollover firings — their "profit before" reads too low, so those rules look like they stopped bigger losses than they did.

## Task 1 (`INVESTIGATION.md`, `task_a_script.py`)

### Step 1. Segment the rules

- I've asked Claude Code to segment the 12 rules into major groups (in INVESTIGATION.md).
- Asked Claude to drill down on ACC-04 because it is the one that got the auto-rules active. I checked how many loser and winner adsets there were each day; as well, I further asked it to compare to other accounts to look for a trend in winning/losing. Claude's answer: ACC-04's share of losing adsets drops! But it also has fewer new adsets toward the end, and no higher ROI or fewer losers over the week.
 - Asked for a rule view table: definition, unique adsets, fails, repeats, successes, losers and winners at action (ROI when the rule fired), and losers and winners at end of day (from performance).
 - Estimate the cost of cutting winners (loser when the rule fired, winner by the end of the day).
- To decide whether the rules did good or not, I've decided to check each rule by itself.
- After I ran the analysis for rules 1 and 2, asked it about the adsets the rule captures, data issues, ROI analysis and win/lose computation, I asked Claude to create a skill for easier prompting and analysis of the next rules.
- After revision of rule 2, I decided on the calculation of lose or win:
  for cut-budget rules it is (ROI at close) × budget removed, counted only if the whole day's spend ≥ 95% of the new budget. Action day only.
  Turn-off rules: (the adset's average daily profit on its spend days before the action) × days left in the data. No history (day 1) → flagged, no value. No days left → $0
- I ran the skill on all the other rules to get an assessment of the rule changes.
- For Q2, I called the skill tables for rules 10 and 1, and after reviewing the rule names, decided they are too blind to be good.


-------Task B — architecture (logged 2026-09-13 17:57) ---------------
First decision is the architecture, and "agent" is a biased word (as I see it).
Basically, I prefer to use chained LLM prompts with the right code harness and routing in code.
Orchestrator-workers is denied after debating it with Claude, due to its unpredictable and less auditable nature.
LLM chaining can be forced with good structure and fixed against $30/day.

### 1. Topology

Decision (my design): phase 1 handles losers only. Actions: wait / diminish / pause_for X hours / revive in +30% steps up to the manager's budget. Pause only after 2 LLM interventions without recovery. The LLM is prompted again when its wait expires or ROI reverses or dips.

### 2. Decision Boundaries
 I've argued my takes on agent capabilities (one major one I've added: to pause and wait for revenue to accumulate) and asked Claude to push back. It suggested some fine-tuning:
   1. A confidence score of agent orders < 0.6: the agent doesn't know, so it doesn't guess
   2. Shark adsets definition
And helped structure it in the md file.

### 3. The economics
I've discussed with Claude the inputs and outputs that the decision agent will need. I suggested a few JSON tables and Pydantic outputs; it gave me some rejection, but the better insight was that I can use caching with a few-shot prompt: I can easily cache a 2,000-token system prompt.
- Another discussion was on the trigger of the agent. I wanted ROI and spend bars which differ by the age of the adsets; Claude suggested raising the spend bar (to screen out 200 calls of small new adsets) and adding a time argument to the LLM call so it can relate to the lag in revenue. Nice!
- A decision that in the morning an agent can't pause, only wait or diminish, and can pause an adset only after noon. I chose that it can pause for up to 2 hours.
- Agent bar: I wanted to set a bar for targeting an adset for the agent loop. I devised a bar that would get 25% of the adsets; Claude revised it and suggested a bar that will clean noise yet include losses. It used a query, `trigger_reach.py`, to find the right bar, and I've settled on a bar that targets 47% of losses — approx. 32 adsets in the agent loop each day.
- I've asked Claude to compute an average scenario and a hard-day scenario of costs, both below the 30 dollars spend.

### 4. Failure modes
- I've asked Claude to criticise me and list 5 failure modes.
- It listed five: revenue lag read as a loss, better ROI by shrinking spend, too many budget edits, bad or stale data, fighting the buyer. I thought on adjusted handling, and also thought on: missing big losers, not catching losers in time, letting losers continue to spend, loads of LLM calls due to data mismatch.
5 were chosen; there could be more.

### 5. Data flow
- Most of it had already been figured out in part 3, The economics. I'm reordering with Claude and locking the new table I'll need to keep track of the agent.
- Sonnet, as far as I can guess, can handle the decision task. Anyway, prompt eval tests can be made to check both the prompt and the model.
- Claude did a loop diagram, with some edits, to my satisfaction.
