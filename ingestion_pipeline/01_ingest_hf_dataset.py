# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Step 1: Ingest HuggingFace Pokemon Cards Dataset
# MAGIC
# MAGIC Downloads the [TheFusion21/PokemonCards](https://huggingface.co/datasets/TheFusion21/PokemonCards) dataset (13,100 rows),
# MAGIC adds a `search_text` column for vector search embeddings, and writes to a Delta table.

# COMMAND ----------

# MAGIC %pip install pyyaml
# MAGIC %restart_python

# COMMAND ----------

import os, yaml

try:
    _dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # __file__ is not defined in Databricks notebook context
    _nb_path = dbutils.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    _dir = os.path.dirname(f"/Workspace{_nb_path}")

_config_path = os.path.join(_dir, "config.yaml")
with open(_config_path) as f:
    cfg = yaml.safe_load(f)

CATALOG = cfg["catalog"]
SCHEMA = cfg["schema"]
TABLE = f"{CATALOG}.{SCHEMA}.{cfg['table_name']}"
EMBEDDING_COL = cfg["vector_search"]["embedding_column"]

print(f"Config loaded — target table: {TABLE}")

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

# COMMAND ----------

import pandas as pd

# Download directly as parquet from HuggingFace (avoids datasets library version conflicts)
HF_PARQUET_URL = "https://huggingface.co/datasets/TheFusion21/PokemonCards/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet"
pdf = pd.read_parquet(HF_PARQUET_URL)
print(f"Downloaded {len(pdf)} rows")
print(f"Columns: {list(pdf.columns)}")

# COMMAND ----------

pdf[EMBEDDING_COL] = pdf["name"].fillna("") + ": " + pdf["caption"].fillna("")
pdf["hp"] = pdf["hp"].astype(int)
pdf = pdf[["id", "image_url", "caption", "name", "hp", "set_name", EMBEDDING_COL]]
print(f"Schema after transform:")
print(pdf.dtypes)
pdf.head(3)

# COMMAND ----------

sdf = spark.createDataFrame(pdf)
sdf.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(TABLE)
print(f"Wrote table {TABLE}")

# COMMAND ----------

spark.sql(f"ALTER TABLE {TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
print("Enabled Change Data Feed")

# COMMAND ----------

count = spark.sql(f"SELECT COUNT(*) as cnt FROM {TABLE}").collect()[0]["cnt"]
print(f"Verification: {count} rows in {TABLE}")
assert count > 0, f"Expected rows in table, got {count}"
