# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pokemon Card Explorer — a Databricks app with an ingestion pipeline and Dash web UI for browsing/searching 13K+ Pokemon TCG cards. Demonstrates Vector Search, AI Functions, Foundation Model API, and Lakebase.

## Key Commands

```bash
# Validate the bundle (app + pipeline)
databricks bundle validate

# Deploy everything (app + pipeline job)
databricks bundle deploy

# Run the ingestion pipeline (4-step sequential job)
databricks bundle run ingestion_pipeline

# Deploy and start the app
databricks bundle run pokemon_card_explorer

# Check app logs
databricks apps logs pokemon-card-explorer-dev

# Run a single ingestion notebook locally via Databricks Connect
source .databricks/.databricks.env
.venv/bin/python ingestion_pipeline/03_create_vector_search.py
```

## Architecture

Two main components deployed as a single Databricks Asset Bundle (`databricks.yml`):

**Ingestion Pipeline** (`ingestion_pipeline/`) — 4 Databricks notebooks run as a sequential job:
1. `01_ingest_hf_dataset.py` — Downloads HuggingFace parquet → Delta table
2. `02_extract_rarity.py` — `ai_query()` classifies card rarity (staging table + MERGE workaround since `ai_query` is non-deterministic and can't be used in UPDATE)
3. `03_create_vector_search.py` — Creates VS endpoint + Delta Sync index with managed embeddings
4. `04_create_online_table.py` — Creates Lakebase synced table

**Dash App** (`app/`) — `app.py` (layout + callbacks) imports `backend.py` (data access):
- SQL warehouse for metrics and default gallery
- Vector Search hybrid queries for search
- Foundation Model API for Agent Search query expansion

## Critical Patterns

**Notebook format**: Files start with `# Databricks notebook source`, cells separated by `# COMMAND ----------`. VS Code is configured to recognize these markers (`.vscode/settings.json`).

**Config loading in notebooks**: Each notebook loads `ingestion_pipeline/config.yaml` independently. Uses `__file__` locally, falls back to `dbutils.entry_point.getDbutils().notebook().getContext().notebookPath().get()` on Databricks runtime.

**REST API over SDK**: Vector Search and synced table creation use `w.api_client.do()` (raw REST) instead of high-level SDK methods to avoid enum/signature compatibility issues across SDK versions.

**Storage-optimized Vector Search filters**: Use SQL-like strings (`rarity = 'Rare'`), NOT JSON format (`{"rarity": "Rare"}`). The `filters_json` parameter name is misleading.

**App env vars**: Configured in `app/app.yaml` (not `databricks.yml`). Resources like the SQL warehouse are injected via `valueFrom: sql-warehouse`. The LLM model and query expansion prompt are also parameterized there.

## Configuration

- `ingestion_pipeline/config.yaml` — Catalog, schema, table name, VS endpoint/index config, Lakebase synced table config, AI model + prompt for rarity extraction
- `app/app.yaml` — App command, env vars (warehouse, VS index, table, LLM model, expansion prompt), resource bindings
- `databricks.yml` — Bundle definition, app resources (warehouse, VS index, table, serving endpoint), job definition with task chain

## Workspace

- Target: `https://fe-vm-vdm-classic-hkbucz.cloud.databricks.com`
- Catalog: `doan`, Schema: `pokemon_cards`
- VS Endpoint: `pokemon-cards-vs-endpoint` (STORAGE_OPTIMIZED)
- Lakebase Project: `pokemondb` (Autoscaling)
