import os
from functools import lru_cache

import pandas as pd
from databricks import sql
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config

# ---------------------------------------------------------------------------
# Configuration — read from app.yaml env vars with sensible defaults
# ---------------------------------------------------------------------------
TABLE = os.getenv("TABLE_NAME", "doan.pokemon_cards.cards")
VS_INDEX = os.getenv("VS_INDEX_NAME", "doan.pokemon_cards.cards_index")
LLM_MODEL = os.getenv("LLM_MODEL", "databricks-meta-llama-3-3-70b-instruct")

COLUMNS = ["id", "name", "hp", "set_name", "image_url", "rarity", "caption"]
VS_COLUMNS = ["id", "name", "hp", "set_name", "image_url", "rarity"]

# ---------------------------------------------------------------------------
# Connections (cached singletons)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_config():
    return Config()


@lru_cache(maxsize=1)
def _get_workspace_client():
    return WorkspaceClient()


def _get_sql_connection():
    cfg = _get_config()
    return sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
        credentials_provider=lambda: cfg.authenticate,
    )


def _sql_query(query: str) -> pd.DataFrame:
    with _get_sql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall_arrow().to_pandas()


# ---------------------------------------------------------------------------
# Metrics (SQL warehouse)
# ---------------------------------------------------------------------------

def get_metrics() -> dict:
    """Return total cards, rare count, and distinct set count."""
    df = _sql_query(f"""
        SELECT
            COUNT(*) AS total_cards,
            SUM(CASE WHEN rarity = 'Rare' THEN 1 ELSE 0 END) AS rare_cards,
            COUNT(DISTINCT set_name) AS total_sets
        FROM {TABLE}
    """)
    row = df.iloc[0]
    return {
        "total_cards": int(row["total_cards"]),
        "rare_cards": int(row["rare_cards"]),
        "total_sets": int(row["total_sets"]),
    }


# ---------------------------------------------------------------------------
# Default gallery (SQL warehouse)
# ---------------------------------------------------------------------------

def get_default_cards(limit: int = 100, offset: int = 0) -> list[dict]:
    """Fetch cards from the Delta table for the default gallery."""
    cols = ", ".join(COLUMNS)
    df = _sql_query(
        f"SELECT {cols} FROM {TABLE} ORDER BY name LIMIT {limit} OFFSET {offset}"
    )
    return df.to_dict(orient="records")


def get_default_cards_filtered(
    rarity: str, limit: int = 100, offset: int = 0
) -> list[dict]:
    """Fetch cards filtered by rarity."""
    cols = ", ".join(COLUMNS)
    df = _sql_query(
        f"SELECT {cols} FROM {TABLE} WHERE rarity = '{rarity}' "
        f"ORDER BY name LIMIT {limit} OFFSET {offset}"
    )
    return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# Vector Search (hybrid search)
# ---------------------------------------------------------------------------

def search_cards(
    query: str, rarity: str | None = None, num_results: int = 50
) -> list[dict]:
    """Hybrid search against the Vector Search index."""
    w = _get_workspace_client()

    kwargs = dict(
        index_name=VS_INDEX,
        columns=VS_COLUMNS,
        query_text=query,
        query_type="HYBRID",
        num_results=num_results,
    )
    if rarity and rarity != "All":
        # Storage-optimized endpoints use SQL-like filter strings, not JSON
        kwargs["filters_json"] = f"rarity = '{rarity}'"

    results = w.vector_search_indexes.query_index(**kwargs)

    cards: list[dict] = []
    result = results.result
    if result and result.data_array:
        # Column names may be on result.manifest.columns or result.columns
        # depending on SDK version — use the requested columns as fallback
        try:
            col_names = [c.name for c in result.manifest.columns]
        except AttributeError:
            col_names = VS_COLUMNS + ["score"]
        for row in result.data_array:
            card = dict(zip(col_names, row[: len(col_names)]))
            cards.append(card)
    return cards


# ---------------------------------------------------------------------------
# Agent Search — LLM query expansion
# ---------------------------------------------------------------------------

_DEFAULT_EXPANSION_PROMPT = (
    "You are a Pokemon card search query optimizer. "
    "Given a user's natural language search query, rewrite it into an expanded "
    "search query that will retrieve the most relevant Pokemon cards from a vector search index. "
    "The index contains card names, descriptions of attacks, abilities, types, HP, and set names. "
    "Expand abbreviations, add synonyms, include related Pokemon types and move names. "
    "Output ONLY the rewritten query text, nothing else."
)
QUERY_EXPANSION_PROMPT = os.getenv("QUERY_EXPANSION_PROMPT", _DEFAULT_EXPANSION_PROMPT)


def expand_query(query: str) -> str:
    """Use an LLM to rewrite a natural language query for better Vector Search retrieval."""
    w = _get_workspace_client()
    openai_client = w.serving_endpoints.get_open_ai_client()

    response = openai_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": QUERY_EXPANSION_PROMPT},
            {"role": "user", "content": query},
        ],
        max_tokens=150,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()
