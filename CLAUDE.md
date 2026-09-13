# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A take-home data analysis (brief: [instructions/candidate_brief.pdf](instructions/candidate_brief.pdf)) on one week (2026-06-06 → 06-12) of production media-buying data for six Meta ad accounts (`ACC-01`…`ACC-06`): adset performance, automation rules, rule executions, and manual buyer actions. The output is analysis written into [deliverables/](deliverables/) (`DECISIONS.md`, `INVESTIGATION.md`, `RESULTS.md`, `ARCHITECTURE.md`), not an application. There are no tests, linter, or build.

Data dictionary and caveats: [instructions/README_DATA.md](instructions/README_DATA.md) (metric conventions) and [instructions/metadata.md](instructions/metadata.md) (per-column dtypes, grain, candidate keys). Read these before writing queries.

## Environment & commands

Python 3.13 managed with `uv` (`.venv` at repo root; VS Code points at it).

```
uv sync                                   # install deps
uv run python "Task A/load_bigquery.py"   # (re)load data/*.csv into BigQuery — WRITE_TRUNCATE
uv run python "Task A/task_a_recon.py"    # rebuilds the *_scoped views
```

The analysis scripts use `# %%` cells and are meant to be run cell-by-cell in the VS Code interactive window; bare `q(...)` calls only display output there.

BigQuery: project `first-proj001`, dataset `mine_marketing`, auth via Google ADC; `.env` is loaded with `python-dotenv`.

## Pipeline architecture

Everything lives in BigQuery as a chain of views, so fixing scope upstream propagates downstream:

1. **Raw tables** (`load_bigquery.py`): `performance`, `rule_executions`, `auto_rules`, `metadata`, `buyer_actions`. ID columns (`adset_id`, `campaign_id`, `fb_ad_account_id`, `account_id`) are loaded as STRING — 18-digit IDs lose precision as INT64. CSVs must be read with `encoding="utf-8"` (metadata crashes under cp1252).
2. **Scoped views** (`task_a_recon.py`, CH.2): the *only* place rows are removed. `performance_scoped` = `SELECT DISTINCT *` (drops 72 byte-identical duplicate rows for ACC-03 on 06-09; 4947 → 4875). `metadata_scoped`, `rule_executions_scoped`, `buyer_actions_scoped` are filtered to adsets present in `performance_scoped`. Only CH.1 reads raw tables; all later analysis reads `*_scoped` or later.
3. **Selection views** (`Archive/task_A_script_v1.py`): `perf_sel`, `rx_sel`, `rules_sel` narrow to working columns; the earlier exploration queries read these. The current rule template, `Task A/task_A_script.py`, reads the `*_scoped` views directly and is run per rule with `.claude/skills/rule-analysis/run_rule.py <RULE>` (or `leftover` for ACC-04 adset-days no rule acted on). Rule conditions live in its `CONDITIONS` dict, replayed as `condition_name`. Earlier template versions: `Archive/task_A_script_v1.py`, `_v2.py`.

Query helper convention used in every script: `q(sql)` replaces the token `$.` with the fully-qualified `` `first-proj001.mine_marketing`. `` prefix and returns a DataFrame. The token is `$.` (not `$`) so regex anchors in SQL survive.

## Data gotchas already established

- ROI/ctr/cr are ratios (`0.52` = +52%); ROI thresholds in rule names are percentages (`-50` → `-0.50`). Recompute profit/ROI from `SUM(revenue)`/`SUM(spend)` rather than averaging row-level ratios.
- `rule_executions` has no `action` column — `action_name` matches `auto_rules.action` and is aliased to `action` in `rx_sel`.
- Key rule executions on `action_date`, not `DATE(action_time)`: `action_time` is UTC and late-evening firings roll to the next reporting date.
- Only `response = 'SUCCESS'` executions actually changed anything (164 of 214). All 214 executions are ACC-04. Repeated firings of the same rule on the same adset are expected, not duplicates.
- Adset IDs come in 14- and 18-digit formats across systems (ACC-04 is entirely 14-digit); `buyer_actions.adset_id` is blank on some rows. `condition_name` has trailing whitespace.
- Performance data is sparse (~60% zero-spend rows); campaign:adset is 1:1.

## Conventions

- Comment markers (Better Comments style) in scripts: `# *` finding/confirmed result, `# !` warning/anomaly, `# ?` rationale/open question, `# TODO` — record query results as `# *`/`# !` comments directly under the cell that produced them.
- Record cleaning/scoping decisions and their justification in `deliverables/DECISIONS.md`.
- `Archive/` holds earlier-phase notes (superseded recon summary); don't treat it as current.
