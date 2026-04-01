# Databricks notebook source

# COMMAND ----------

# MAGIC %md
# MAGIC # Step 3: Create Vector Search Index
# MAGIC
# MAGIC Creates a Vector Search endpoint and a Delta Sync index with managed embeddings.

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

vs = cfg["vector_search"]
ENDPOINT_NAME = vs["endpoint_name"]
ENDPOINT_TYPE = vs["endpoint_type"]
INDEX_NAME = f"{CATALOG}.{SCHEMA}.{vs['index_name']}"
EMBEDDING_COL = vs["embedding_column"]
EMBEDDING_MODEL = vs["embedding_model"]
PIPELINE_TYPE = vs["pipeline_type"]
COLUMNS_TO_SYNC = vs["columns_to_sync"]

print(f"Config loaded — endpoint: {ENDPOINT_NAME}, index: {INDEX_NAME}")

# COMMAND ----------

import time
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create or reuse Vector Search endpoint

# COMMAND ----------

try:
    endpoint = w.vector_search_endpoints.get_endpoint(ENDPOINT_NAME)
    print(f"Endpoint '{ENDPOINT_NAME}' already exists, status: {endpoint.endpoint_status}")
except Exception:
    print(f"Creating endpoint '{ENDPOINT_NAME}' ({ENDPOINT_TYPE})...")
    # Use REST API directly to avoid SDK enum compatibility issues
    w.api_client.do(
        "POST",
        "/api/2.0/vector-search/endpoints",
        body={"name": ENDPOINT_NAME, "endpoint_type": ENDPOINT_TYPE},
    )
    print("Endpoint creation initiated")

# COMMAND ----------

# Wait for endpoint to be ONLINE
while True:
    ep = w.api_client.do("GET", f"/api/2.0/vector-search/endpoints/{ENDPOINT_NAME}")
    status = ep.get("endpoint_status", {}).get("state", "UNKNOWN")
    print(f"Endpoint status: {status}")
    if status == "ONLINE":
        break
    time.sleep(30)

print(f"Endpoint '{ENDPOINT_NAME}' is ONLINE")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Delta Sync index with managed embeddings

# COMMAND ----------

try:
    idx = w.api_client.do("GET", f"/api/2.0/vector-search/indexes/{INDEX_NAME}")
    print(f"Index '{INDEX_NAME}' already exists, status: {idx.get('status')}")
except Exception:
    print(f"Creating index '{INDEX_NAME}'...")
    w.api_client.do(
        "POST",
        "/api/2.0/vector-search/indexes",
        body={
            "name": INDEX_NAME,
            "endpoint_name": ENDPOINT_NAME,
            "primary_key": "id",
            "index_type": "DELTA_SYNC",
            "delta_sync_index_spec": {
                "source_table": TABLE,
                "embedding_source_columns": [
                    {
                        "name": EMBEDDING_COL,
                        "embedding_model_endpoint_name": EMBEDDING_MODEL,
                    }
                ],
                "pipeline_type": PIPELINE_TYPE,
                "columns_to_sync": COLUMNS_TO_SYNC,
            },
        },
    )
    print("Index creation initiated")

# COMMAND ----------

# Wait for index to finish provisioning before triggering sync
while True:
    idx = w.api_client.do("GET", f"/api/2.0/vector-search/indexes/{INDEX_NAME}")
    idx_status = idx.get("status", {}).get("ready", False)
    idx_msg = idx.get("status", {}).get("message", "provisioning")
    print(f"Index status: ready={idx_status}, message={idx_msg}")
    if idx_status:
        break
    time.sleep(30)

# Trigger initial sync
w.api_client.do("POST", f"/api/2.0/vector-search/indexes/{INDEX_NAME}/sync")
print("Sync triggered")

# COMMAND ----------

# Verify index status
idx = w.api_client.do("GET", f"/api/2.0/vector-search/indexes/{INDEX_NAME}")
print(f"Index: {idx.get('name')}")
print(f"Status: {idx.get('status')}")
