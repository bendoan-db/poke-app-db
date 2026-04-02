# Pokemon Card Explorer

A Databricks app that lets users browse and search 13,000+ Pokemon TCG cards using semantic search, AI-powered query expansion, and a responsive card gallery — all built on Databricks platform services.

## Platform Capabilities Demonstrated

| Capability | How It's Used |
|------------|---------------|
| **AI Functions (`ai_query`)** | Classifies card rarity (Common/Uncommon/Rare) from unstructured card descriptions at ingestion time |
| **Vector Search** | Storage-optimized hybrid semantic + keyword search over card names and descriptions |
| **Foundation Model API** | Agent Search mode — LLM rewrites user queries for better retrieval using Pokemon type matchup knowledge (e.g., "Charizard counter" becomes a search for strong Water-type cards) |
| **Lakebase Autoscaling** | Synced table (`cards_online`) provides low-latency PostgreSQL reads for the card gallery and metrics, powered by a Lakebase Autoscaling project with OAuth connection pooling |
| **Databricks Apps** | Dash web app deployed and managed via Databricks Asset Bundles with auto-provisioned resources (SQL warehouse, VS index, Lakebase, serving endpoint) |

## Architecture

```
HuggingFace Dataset (13K Pokemon cards)
       |
  [Ingestion Pipeline — 4-step Databricks Job]
       |
       v
Delta Table (doan.pokemon_cards.cards)
   + search_text column (name + caption)
   + rarity column (AI-classified via ai_query)
       |
       +---> Vector Search Index (storage-optimized, hybrid search, managed embeddings)
       +---> Lakebase Synced Table (pokebase/pokemon_cards.cards_online)
       |
       v
Databricks App (Dash + Bootstrap)
   + Card gallery powered by Lakebase (psycopg + OAuth connection pool)
   + Search mode: direct hybrid vector search
   + Agent Search mode: LLM query expansion with type matchups -> vector search
   + Rarity filtering with dynamic metrics
   + Pagination (20 cards per page)
```

## Project Structure

```
.
├── README.md
├── CLAUDE.md                       # Claude Code guidance
├── APP.md                          # Detailed design document
├── databricks.yml                  # Asset bundle: app + ingestion job + all resources
├── app/                            # Databricks App (Dash)
│   ├── app.py                      # Layout, callbacks, pagination
│   ├── backend.py                  # Lakebase, Vector Search, LLM queries
│   ├── grant_permissions.py        # Grant app SP access to Lakebase synced table
│   ├── app.yaml                    # App config, env vars, resource bindings
│   └── requirements.txt
└── ingestion_pipeline/             # Data pipeline (Databricks notebooks)
    ├── config.yaml                 # Parameterized catalog, schema, models, prompts
    ├── requirements.txt
    ├── 01_ingest_hf_dataset.py     # Download HuggingFace parquet -> Delta table
    ├── 02_extract_rarity.py        # ai_query to classify card rarity
    ├── 03_create_vector_search.py  # Create VS endpoint + Delta Sync index
    └── 04_create_online_table.py   # Create Lakebase synced table
```

## Setup

### Prerequisites

- Databricks workspace with Unity Catalog enabled
- A SQL warehouse
- A Lakebase Autoscaling project with a database (for the synced table)
- Python 3.11+ with `uv` or `pip`

### 1. Configure the Pipeline

Edit `ingestion_pipeline/config.yaml` to match your workspace:

```yaml
catalog: your_catalog
schema: pokemon_cards
table_name: cards

vector_search:
  endpoint_name: pokemon-cards-vs-endpoint
  index_name: cards_index
  endpoint_type: STORAGE_OPTIMIZED
  embedding_model: databricks-gte-large-en

synced_table:
  name: cards_online
  database_project: your_lakebase_project
  database_branch: production

ai:
  model: databricks-claude-sonnet-4
  rarity_prompt: "Your custom rarity classification prompt..."
```

### 2. Run the Ingestion Pipeline

```bash
databricks bundle validate
databricks bundle deploy
databricks bundle run ingestion_pipeline
```

The pipeline runs 4 steps sequentially:
1. **Ingest** — Downloads the PokemonCards parquet from HuggingFace, adds `search_text` column, writes to Delta table, enables Change Data Feed
2. **Extract Rarity** — Uses `ai_query` to classify each card as Common, Uncommon, or Rare (staging table + MERGE pattern to handle non-deterministic `ai_query`)
3. **Create Vector Search** — Creates a storage-optimized endpoint and Delta Sync index with managed embeddings via REST API
4. **Create Synced Table** — Creates a Lakebase synced table for low-latency PostgreSQL reads

### 3. Deploy the App

```bash
databricks bundle deploy
databricks bundle run pokemon_card_explorer
```

The bundle automatically provisions these app resources:
- SQL warehouse (`CAN_USE`)
- Vector Search index (`SELECT`)
- Source Delta table (`SELECT`)
- Foundation Model serving endpoint (`CAN_QUERY`)
- Lakebase Autoscaling database (`CAN_CONNECT_AND_CREATE`)

### 4. Grant Lakebase Permissions

After the first deployment, grant the app's service principal `SELECT` access to the synced table schema:

```bash
source .databricks/.databricks.env
.venv/bin/python app/grant_permissions.py
```

This connects to Lakebase as your user and grants `USAGE` + `SELECT` on the `pokemon_cards` schema to the app's SP. Only needs to be run once (or after re-creating the app).

## App Features

### Search

Type a query and click Search. Uses **hybrid search** (semantic + keyword matching) against the storage-optimized Vector Search index. Filter results by rarity using the toggle buttons (All / Common / Uncommon / Rare).

### Agent Search

Toggle the "Agent Search" switch to enable LLM-powered query expansion. The Foundation Model API rewrites your query before searching, using Pokemon type matchup knowledge:

| User Query | Agent Expands To |
|------------|-----------------|
| "Charizard counter" | Strong Water/Ground/Rock-type Pokemon cards |
| "Charizard complement" | Strong Grass-type Pokemon (counters Charizard's Water weakness) |
| "strong water types that can heal" | Water Pokemon high HP recovery healing moves |

The rewritten query is shown in a blue banner above the results. The expansion prompt is fully customizable in `app.yaml` and includes a complete Pokemon type chart with resistances and weaknesses.

### Gallery & Metrics

Cards display in a responsive 4-column grid showing the card image, name, set, rarity badge (color-coded: green/blue/gold), and HP. Paginated at 20 cards per page.

The metrics row (Total Cards, Rare Cards, Card Sets) dynamically updates to reflect the current view — whether browsing all cards, filtering by rarity, or viewing search results.

### Data Backend

The gallery and metrics are powered by **Lakebase Autoscaling** via the synced table, using the `OAuthConnection` pattern from the official [flask-postgres-app](https://github.com/databricks/app-templates/tree/main/flask-postgres-app) template. Connection pooling with automatic OAuth token refresh handles credential management transparently.

## Configuration

### App Configuration (`app/app.yaml`)

| Variable | Source | Description |
|----------|--------|-------------|
| `DATABRICKS_WAREHOUSE_ID` | `valueFrom: sql-warehouse` | SQL warehouse (auto-injected) |
| `VS_INDEX_NAME` | static | Vector Search index full name |
| `PGENDPOINT` | `valueFrom: postgres` | Lakebase endpoint (auto-injected by resource binding) |
| `PGDATABASE` | static | Lakebase database name (`pokebase`) |
| `PG_SCHEMA` | static | Postgres schema for synced table (`pokemon_cards`) |
| `PG_TABLE` | static | Synced table name (`cards_online`) |
| `LLM_MODEL` | static | Foundation Model endpoint for Agent Search |
| `QUERY_EXPANSION_PROMPT` | static | System prompt for LLM query expansion (includes Pokemon type chart) |

### Bundle Resources (`databricks.yml`)

The app declares these resources for automatic provisioning on deploy:

| Resource | Type | Permission |
|----------|------|------------|
| `sql-warehouse` | SQL Warehouse | `CAN_USE` |
| `vs-index` | UC Securable (Table) | `SELECT` |
| `source-table` | UC Securable (Table) | `SELECT` |
| `serving-endpoint` | Serving Endpoint | `CAN_QUERY` |
| `postgres` | Lakebase Autoscaling | `CAN_CONNECT_AND_CREATE` |

## Development

### Local Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
uv pip install -r ingestion_pipeline/requirements.txt
uv pip install -r app/requirements.txt
```

### Running Notebooks Locally

The ingestion pipeline notebooks can be run locally via Databricks Connect:

```bash
source .databricks/.databricks.env
python ingestion_pipeline/01_ingest_hf_dataset.py
```

### Redeploying the App

```bash
databricks bundle deploy && databricks bundle run pokemon_card_explorer
```

## Design Document

See [APP.md](APP.md) for the full design document including UI wireframes, callback specifications, agent search flow diagrams, and architecture decisions.
