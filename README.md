# Pokemon Card Explorer

A Databricks app that lets users browse and search 13,000+ Pokemon TCG cards using semantic search, AI-powered query expansion, and a responsive card gallery — all built on Databricks platform services.

## Platform Capabilities Demonstrated

| Capability | How It's Used |
|------------|---------------|
| **AI Functions (`ai_query`)** | Classifies card rarity (Common/Uncommon/Rare) from unstructured card descriptions at ingestion time |
| **Vector Search** | Hybrid semantic + keyword search over card names and descriptions |
| **Foundation Model API** | Agent Search mode — LLM rewrites user queries for better retrieval (e.g., "Charizard counter" becomes a search for strong Water-type cards) |
| **Lakebase** | Synced table for low-latency point lookups from Delta Lake |
| **Databricks Apps** | Dash web app deployed and managed via Databricks Asset Bundles |

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
       +---> Vector Search Index (hybrid search, managed embeddings)
       +---> Lakebase Synced Table (low-latency lookups)
       |
       v
Databricks App (Dash + Bootstrap)
   + Card gallery with images, rarity badges, HP
   + Search mode: direct hybrid vector search
   + Agent Search mode: LLM query expansion -> vector search
   + Rarity filtering, pagination
```

## Project Structure

```
.
├── README.md
├── APP.md                          # Detailed design document
├── databricks.yml                  # Asset bundle: app + ingestion job
├── app/                            # Databricks App (Dash)
│   ├── app.py                      # Layout, callbacks, pagination
│   ├── backend.py                  # SQL warehouse, Vector Search, LLM queries
│   ├── app.yaml                    # App config, env vars, resources
│   └── requirements.txt
└── ingestion_pipeline/             # Data pipeline (Databricks notebooks)
    ├── config.yaml                 # Parameterized catalog, schema, models
    ├── requirements.txt
    ├── 01_ingest_hf_dataset.py     # Download dataset, write Delta table
    ├── 02_extract_rarity.py        # ai_query to classify card rarity
    ├── 03_create_vector_search.py  # Create VS endpoint + index
    └── 04_create_online_table.py   # Create Lakebase synced table
```

## Setup

### Prerequisites

- Databricks workspace with Unity Catalog enabled
- A SQL warehouse
- A Lakebase Autoscaling project (for the synced table step)
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
  database_project: your_lakebase_project
  database_branch: production

ai:
  model: databricks-claude-sonnet-4
```

### 2. Run the Ingestion Pipeline

```bash
# Validate and deploy
databricks bundle validate
databricks bundle deploy

# Run the full pipeline (ingest -> rarity -> vector search -> synced table)
databricks bundle run ingestion_pipeline
```

The pipeline runs 4 steps sequentially:
1. **Ingest** — Downloads the PokemonCards dataset from HuggingFace and writes to a Delta table
2. **Extract Rarity** — Uses `ai_query` to classify each card as Common, Uncommon, or Rare
3. **Create Vector Search** — Creates a storage-optimized endpoint and Delta Sync index with managed embeddings
4. **Create Synced Table** — Creates a Lakebase synced table for low-latency lookups

### 3. Deploy the App

```bash
# Deploy (includes app + pipeline resources)
databricks bundle deploy

# Start the app
databricks bundle run pokemon_card_explorer
```

The app URL will be printed on success. Add the SQL warehouse resource via the Databricks UI if not already assigned.

## App Features

### Search

Type a query and click Search. Uses **hybrid search** (semantic + keyword matching) against the Vector Search index. Filter results by rarity using the toggle buttons.

### Agent Search

Toggle the "Agent Search" switch to enable LLM-powered query expansion. The Foundation Model API rewrites your query before searching. Examples:

| User Query | Agent Expands To |
|------------|-----------------|
| "Charizard counter" | Strong Water-type Pokemon cards |
| "strong water types that can heal" | Water Pokemon high HP recovery healing moves |
| "fast electric attacker" | Electric-type Pokemon low energy cost quick attack Thunder |

The rewritten query is shown in a blue banner above the results so you can see how the LLM interpreted your intent.

### Gallery

Cards display in a responsive 4-column grid showing the card image, name, set, rarity badge (color-coded), and HP. Paginated at 20 cards per page.

## Configuration

All app configuration is in `app/app.yaml`:

| Variable | Description |
|----------|-------------|
| `DATABRICKS_WAREHOUSE_ID` | SQL warehouse (injected via `valueFrom: sql-warehouse`) |
| `VS_INDEX_NAME` | Vector Search index full name |
| `TABLE_NAME` | Source Delta table full name |
| `LLM_MODEL` | Foundation Model endpoint for Agent Search |
| `QUERY_EXPANSION_PROMPT` | System prompt for LLM query expansion (customizable) |

## Development

### Local Setup

```bash
# Create and activate virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r ingestion_pipeline/requirements.txt
pip install -r app/requirements.txt
```

### Running Notebooks Locally

The ingestion pipeline notebooks can be run locally via Databricks Connect:

```bash
source .databricks/.databricks.env
python ingestion_pipeline/01_ingest_hf_dataset.py
```

## Design Document

See [APP.md](APP.md) for the full design document including UI wireframes, callback specifications, data flow diagrams, and architecture decisions.
