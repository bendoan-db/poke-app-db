# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Step 2: Extract Rarity with AI Functions
# MAGIC
# MAGIC Uses `ai_query` to classify each Pokemon card's rarity
# MAGIC as **Common**, **Uncommon**, or **Rare** based on its caption.
# MAGIC
# MAGIC This processes ~13K LLM calls and may take 30-60+ minutes.

# COMMAND ----------

# MAGIC %pip install pyyaml
# MAGIC %restart_python

# COMMAND ----------

import os, yaml

try:
    _dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _nb_path = dbutils.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    _dir = os.path.dirname(f"/Workspace{_nb_path}")

_config_path = os.path.join(_dir, "config.yaml")
with open(_config_path) as f:
    cfg = yaml.safe_load(f)

CATALOG = cfg["catalog"]
SCHEMA = cfg["schema"]
TABLE = f"{CATALOG}.{SCHEMA}.{cfg['table_name']}"
AI_MODEL = cfg["ai"]["model"]
RARITY_PROMPT = cfg["ai"]["rarity_prompt"]

print(f"Config loaded — table: {TABLE}, model: {AI_MODEL}")
print(f"Prompt: {RARITY_PROMPT[:80]}...")

# COMMAND ----------

# ADD COLUMN doesn't support IF NOT EXISTS in Spark SQL — check schema first
existing_cols = [c.name for c in spark.table(TABLE).schema]
if "rarity" not in existing_cols:
    spark.sql(f"ALTER TABLE {TABLE} ADD COLUMN rarity STRING")
    print("Added rarity column")
else:
    print("Rarity column already exists")

# COMMAND ----------

# ai_query is non-deterministic, so UPDATE SET won't accept it directly.
# Workaround: compute rarity via SELECT into a staging table, then MERGE back.
_escaped_prompt = RARITY_PROMPT.replace("'", "''")
STAGING = f"{TABLE}_rarity_staging"

spark.sql(f"""
CREATE OR REPLACE TABLE {STAGING} AS
SELECT id, ai_query(
  '{AI_MODEL}',
  CONCAT(
    '{_escaped_prompt}',
    '\n\nCard: ', name, '\nDescription: ', caption
  )
) as rarity
FROM {TABLE}
""")
print("Rarity computed in staging table")

# COMMAND ----------

spark.sql(f"""
MERGE INTO {TABLE} AS t
USING {STAGING} AS s
ON t.id = s.id
WHEN MATCHED THEN UPDATE SET t.rarity = s.rarity
""")
print("Rarity merged back into source table")

spark.sql(f"DROP TABLE IF EXISTS {STAGING}")
print("Staging table cleaned up")

# COMMAND ----------

display(spark.sql(f"SELECT rarity, COUNT(*) as cnt FROM {TABLE} GROUP BY rarity ORDER BY cnt DESC"))
