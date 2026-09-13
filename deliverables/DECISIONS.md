
-------Phase 0 ---------------
1. invastigating, phase 0 - i uploaded the csv to bigquery and asked claude to bring to life step 0- check wether all the tabels are connected via keys- to major findings land by the probe which i furthur invstigated with dedicated script (task_a_recon.py)
    a.  ACC-04 is 100% 14-digit + all 214 rule executions belong to ACC-04 alone + ACC-04 is the best account (ROAS 1.19, top of book, $3,076 revenue on $2,586), so the rules were aimed at the healthiest big spender or created it? 
    b. 2026-06-09 all 13 executions hit a single adset via a single rule 
    c. Human buyers acted on all six accounts - which can be natural control group
    d. 8 rules executed after preformence 
    e. the accounts are 1:1 adset-to-campaign
    table tracked last date and not relevant
all of this represented in the script via sql tables
   
2. filtering and cleaning all applyed in the py file:
    a. filter for only the adstes that appear 
    in preformance table, its my playgroung

3. i've asked claude to check on outlaires, nulls and suspicious rul;e execution patterns, and added the relevant queries to (task_a_recon.py)
findings:
    Adset 31302925337341 in ACC-04 is outlier in spent but look valids in numbels
    From 03:30 to 16:30 UTC there were 27 failed actions and zero successes
    R02 retried every 30 minutes and got "No budget to change" 


Finding: All 72 duplicate (adset_id, date) pairs are byte-identical rows confined to a single account-day (ACC-03, 2026-06-09, every group exactly 2 rows) whose 72 adsets sit normally on that account's daily ramp — a double-emission of one slice, not conflicting restatements or missing data.

Decision: Drop with plain df.drop_duplicates() (4947 → 4875 rows, 4875 unique keys); no keep-rule is needed since no column differs within any grou


Finding: rule_executions carries four budget columns. set_budget / current_budget_from_fb equals the rule's stated % on 17/17 budget rows (set/new_budget: 12/17, set/old_budget: 0/17), and buyer_actions logs the same change (update_ad_set_budget, same timestamp, fb → set). old_budget / new_budget instead repeat the adset's previous budget change, often a buyer's — which is why "Decrease" rows show new_budget > old_budget.

Decision: A rule's budget change = current_budget_from_fb → set_budget. old_budget / new_budget are not used to measure rule actions.

Finding: spend_at_action is cumulative same-day spend up to action_time (monotonic, ≤ day spend on 212/214 rows), so the day splits into before (spend_at_action, today_roi_at_action) and after (perf day totals minus at-action).

Decision: Revenue at action = spend_at_action × (1 + today_roi_at_action) — roi is 2dp (≤0.5% of spend error); rpc/cpa reconstruction was off by ~0.05 ROI and is not used. First firing per adset-day-action only; failed executions used as the comparison group.

Decision: In the per-rule template, failed executions are counted but not calculated (no exposure or before/after effect) — the question is what the rules did, not what they could have done; failed runs get their own analysis in a later session.


-------Rule impact method ---------------
Asked Claude for a one-shot per-rule summary table; rejected it — fast, but errors hide in bulk and a wrong number costs more than a careful pass. Chose instead: segment the rules, define KPIs per segment, then a manual rule-by-rule pass.

Decision: 12 rules in 5 segments — Day 1-2 kill (R04 R05 R06), Never profitable (R03 R11), Age kill (R01 R08), Budget cut (R02 R07 R10 R12), Undo (R09). Full map, KPIs and column definitions in INVESTIGATION.md "Rule impact — method".

Decision: each rule gets a fixed two-block table by action_date (activity + money), plus its segment KPIs.
  - decision = rule x adset x action_date; "before" = first SUCCESS firing; ROI always Σrev/Σspend.
  - exposure = what the action removed (OFF: budget − spend so far; Decrease: budget − set_budget).
  - accumulated "after" stops at the same rule's next action on that adset (no double count).
  - overlapping rules both get credit (both acted); same-segment overlap = flagged redundant.
  - failed runs counted, not calculated; rollover decisions flagged, negatives shown as-is.
  - replay on the other 5 accounts deferred to the rule-by-rule pass; failed-run control to a later session.

Rejected: the earlier segment summary's exposure figures (~$1,012 Age kill, ~$3,491 Budget cut) — no budget or spend column reproduces them; not carried forward.
