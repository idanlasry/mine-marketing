"""One-off: load data/*.csv into BigQuery. Re-run to refresh (tables are replaced)."""
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

PROJECT, DATASET = "first-proj001", "mine_marketing"
DATA = next(p / "data" for p in [Path(__file__).resolve().parent, *Path(__file__).resolve().parents] if (p / "data").is_dir())

# table name -> csv. ids stay STRING: 18-digit adset_ids lose precision as INT64.
TABLES = {"performance": "daily_adset_performance", "rule_executions": "rule_executions",
          "auto_rules": "auto_rules", "metadata": "campaign_adset_metadata",
          "buyer_actions": "buyer_actions"}
TEXT = ["adset_id", "campaign_id", "fb_ad_account_id", "account_id"]

client = bigquery.Client(project=PROJECT)
client.create_dataset(f"{PROJECT}.{DATASET}", exists_ok=True)

for table, csv in TABLES.items():
    df = pd.read_csv(DATA / f"{csv}.csv", encoding="utf-8",
                     dtype={c: str for c in TEXT})  # encoding explicit: cp1252 crashes on metadata
    job = client.load_table_from_dataframe(
        df, f"{PROJECT}.{DATASET}.{table}",
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"))
    job.result()
    print(f"{table:16} {len(df):>5} rows x {df.shape[1]:>2} cols")
