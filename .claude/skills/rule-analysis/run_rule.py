"""Run the rule template for one rule, outside the interactive window.

Executes only the header cell (imports, client, q) and the TEMPLATE cell of the script,
then prints the five answers for the given rule. Nothing is written anywhere.

usage (from the repo root):
    PYTHONIOENCODING=utf-8 uv run python .claude/skills/rule-analysis/run_rule.py        # asks for the rule
    PYTHONIOENCODING=utf-8 uv run python .claude/skills/rule-analysis/run_rule.py R04
    PYTHONIOENCODING=utf-8 uv run python .claude/skills/rule-analysis/run_rule.py R05 --script "Task A/task_A_script.py"
"""

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd

# run from the repo root whatever folder it was started from, and print non-Latin names safely
_root = next(p for p in Path(__file__).resolve().parents if (p / "Task A" / "task_A_script.py").exists())
os.chdir(_root)
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser()
parser.add_argument("rule", nargs="?", help="rule id, e.g. R04 (asked for if left out)")
parser.add_argument("--script", default="Task A/task_A_script.py")
args = parser.parse_args()
if not args.rule:
    args.rule = input("rule number (e.g. R04, or leftover): ").strip()
args.rule = args.rule.upper() if args.rule.lower() != "leftover" else "leftover"

pd.set_option("display.width", 400)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", 500)
pd.set_option("display.max_colwidth", 120)

src = open(args.script, encoding="utf-8").read()
cells = [c for c in re.split(r"(?m)^(?=# %%)", src) if c.startswith("# %%")]
template = [c for c in cells if c.startswith("# %% TEMPLATE")]
if not template:
    sys.exit("no '# %% TEMPLATE' cell found")

g = {}
exec(cells[0], g)      # header: imports, client, q
exec(template[0], g)   # shared queries only
if args.rule.lower() == "leftover":  # ACC-04 adset-days no rule acted on
    for title, name in [("ACC-04 leftovers", "K_LEFTOVER"), ("by matched rule", "K_LEFTOVER_BY_RULE"),
                        ("5 biggest losers per bucket", "K_LEFTOVER_TOP")]:
        print(f"===== {title}")
        print(g["q"](g[name]).to_string(index=False))
        print()
    sys.exit()

if args.rule not in g["CONDITIONS"]:
    sys.exit(f"unknown rule '{args.rule}' — use R01 to R12, or leftover")
g["RULE"] = args.rule  # qr reads RULE at call time
print(f"condition: {g['CONDITIONS'].get(args.rule)}\n")

runs = [
    ("1 — what the rule did", "BLOCK_A"),
    ("2 — did it stop the bleeding?", "K_BLEEDING"),
    ("3 — peers and missed", "K_PEERS"),
    ("4 — impact: rule total and verdict", "K_IMPACT"),
    ("4 — impact per decision, most missed income first", "K_IMPACT_DECISIONS"),
    ("5 — data issues", "K_ISSUES"),
]
for title, name in runs:
    print(f"===== {args.rule} — {title}")
    print(g["qr"](g[name]).to_string(index=False))
    print()
