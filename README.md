Hi,
Thank you for the assignment.
So basically every task is standalone and can be found the md files in the 'Deliverables' folder suppurted by scripts nad files in each task dedicated folder. DECISIONS.md will complement all the tasks with ,most, of my logs and decisions.

**How to run**
- Setup: Python 3.13 with `uv`; run `uv sync`. BigQuery (project `first-proj001`, dataset `mine_marketing`) uses Google ADC auth. Put `ANTHROPIC_API_KEY=...` in `.env` for Task C.
- Load the data: `uv run python "Task A/load_bigquery.py"`, then `uv run python "Task A/task_a_recon.py"` to build the scoped views.
- Task A: `task_A_script.py` per rule, via `uv run python "Task A/rule-analysis/run_rule.py" <RULE>`.
- Task B: `Task B/trigger_reach.py` (the bar and call-volume queries).
- Task C: set `MODEL`, `LIMIT` and `RUN_DAYS` (one day per run; earlier days are read back from the logs) at the top of `Task C/agent.py`, then `uv run python "Task C/agent.py"`. Output: `Task C/agent_log.csv` (LLM calls) and `Task C/bar_check_log.jsonl` (bar checks).
- The scripts use `# %%` cells and can also be run cell by cell in the VS Code interactive window.

Task A took loads of time, mostly to understand the data and try to devise a "right way", which I didn't.
It reads along with DECISIONS.md, and there is a skill + script to analyse each rule's performance and characteristics.

I've cut corners at the computation of the cost in Task A, where I've tried many angles and many ways to figure it out, and it just collapsed on me each time. So I've settled on a direct, simple way once I felt I was grasping the dataset enough in my mind, and built the skill to give Claude Code an auditable plan for how to understand, analyse and explore each rule's behavior.
In Task C, I cut corners with the stub, but designed an LLM pipeline (already in the architecture) to support the agentic improvement every day, and on the comparison to the auto-rule executions.

Also, some of the decisions are written after the advances in the build-up of the md files. I did chase butterflies with Claude Code, which many times led to dead ends, but they were appealing and intriguing chases nonetheless.


Approx. it took me 10 hours of playing with the data, 10 hours of building, and a couple more hours of cursing Claude Code.

Best regards, Idan Lasry
