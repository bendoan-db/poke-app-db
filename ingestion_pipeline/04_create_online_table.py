# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Step 4: Create Synced Table (Lakebase Autoscaling)
# MAGIC
# MAGIC Creates a Lakebase synced table from the Delta source table for low-latency
# MAGIC point lookups by card ID. Uses Lakebase Autoscaling project/branch.
# MAGIC
# MAGIC **Prerequisite**: A Lakebase Autoscaling project must already exist.

# COMMAND ----------

# MAGIC %pip install databricks-sdk --upgrade pyyaml
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

st_cfg = cfg["synced_table"]
LAKEBASE_CATALOG = st_cfg["lakebase_catalog"]
LAKEBASE_SCHEMA = st_cfg["lakebase_schema"]
SYNCED_TABLE_NAME = f"{LAKEBASE_CATALOG}.{LAKEBASE_SCHEMA}.{st_cfg['name']}"
SCHEDULING_POLICY = st_cfg["scheduling_policy"]
DB_PROJECT = st_cfg["database_project"]
DB_BRANCH = st_cfg["database_branch"]

print(f"Config loaded — source: {TABLE}, synced table: {SYNCED_TABLE_NAME}")
print(f"Lakebase project: {DB_PROJECT}, branch: {DB_BRANCH}")

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# COMMAND ----------

try:
    st = w.api_client.do("GET", f"/api/2.0/database/synced_tables/{SYNCED_TABLE_NAME}")
    print(f"Synced table '{SYNCED_TABLE_NAME}' already exists")
    print(f"Status: {st.get('data_synchronization_status', {}).get('detailed_state', 'UNKNOWN')}")
except Exception:
    print(f"Creating synced table '{SYNCED_TABLE_NAME}'...")
    st = w.api_client.do(
        "POST",
        "/api/2.0/database/synced_tables",
        body={
            "name": SYNCED_TABLE_NAME,
            "database_project": DB_PROJECT,
            "database_branch": DB_BRANCH,
            "spec": {
                "source_table_full_name": TABLE,
                "primary_key_columns": ["id"],
                "scheduling_policy": SCHEDULING_POLICY,
                "create_database_objects_if_missing": True,
            },
        },
    )
    print(f"Synced table creation initiated")

# COMMAND ----------

st = w.api_client.do("GET", f"/api/2.0/database/synced_tables/{SYNCED_TABLE_NAME}")
print(f"Synced table: {SYNCED_TABLE_NAME}")
print(f"Status: {st.get('data_synchronization_status', {}).get('detailed_state', 'UNKNOWN')}")
