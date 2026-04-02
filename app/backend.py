import os
from functools import lru_cache

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from databricks import sdk
from databricks.sdk import WorkspaceClient

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VS_INDEX = os.getenv("VS_INDEX_NAME", "doan.pokemon_cards.cards_index")
LLM_MODEL = os.getenv("LLM_MODEL", "databricks-meta-llama-3-3-70b-instruct")

PG_SCHEMA = os.getenv("PG_SCHEMA", "pokemoncards")
PG_TABLE = os.getenv("PG_TABLE", "cards_online")

COLUMNS = ["id", "name", "hp", "set_name", "image_url", "rarity", "caption"]
VS_COLUMNS = ["id", "name", "hp", "set_name", "image_url", "rarity"]

# ---------------------------------------------------------------------------
# Lakebase connection — follows flask-postgres-app template pattern
# Auto-injected env vars: PGHOST, PGUSER, PGDATABASE, PGPORT, PGSSLMODE,
# PGAPPNAME, PGENDPOINT (from postgres resource binding)
# ---------------------------------------------------------------------------

_workspace_client = sdk.WorkspaceClient()
_pg_endpoint = os.getenv("PGENDPOINT", "")
_connection_pool = None


class _OAuthConnection(psycopg.Connection):
    """Connection subclass that auto-refreshes OAuth credentials."""

    @classmethod
    def connect(cls, conninfo="", **kwargs):
        credential = _workspace_client.postgres.generate_database_credential(
            endpoint=_pg_endpoint
        )
        kwargs["password"] = credential.token
        return super().connect(conninfo, **kwargs)


def _get_pg_pool() -> ConnectionPool:
    """Get or create the Lakebase connection pool."""
    global _connection_pool
    if _connection_pool is None:
        conn_string = (
            f"dbname={os.getenv('PGDATABASE')} "
            f"user={os.getenv('PGUSER')} "
            f"host={os.getenv('PGHOST')} "
            f"port={os.getenv('PGPORT')} "
            f"sslmode={os.getenv('PGSSLMODE', 'require')} "
            f"application_name={os.getenv('PGAPPNAME')}"
        )
        _connection_pool = ConnectionPool(
            conn_string,
            connection_class=_OAuthConnection,
            min_size=2,
            max_size=10,
            kwargs={"row_factory": dict_row},
        )
    return _connection_pool


def _pg_query(query, params=None) -> list[dict]:
    """Execute a PostgreSQL query and return results as list of dicts."""
    with _get_pg_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return list(cur.fetchall())




# ---------------------------------------------------------------------------
# Workspace client (for VS and LLM)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_workspace_client():
    return WorkspaceClient()


# ---------------------------------------------------------------------------
# Metrics (Lakebase)
# ---------------------------------------------------------------------------

def get_metrics(rarity: str | None = None) -> dict:
    """Return total cards, rare count, and distinct set count."""
    table = f'"{PG_SCHEMA}"."{PG_TABLE}"'
    if rarity and rarity != "All":
        rows = _pg_query(
            f"SELECT COUNT(*) AS total_cards, "
            f"SUM(CASE WHEN rarity = 'Rare' THEN 1 ELSE 0 END) AS rare_cards, "
            f"COUNT(DISTINCT set_name) AS total_sets "
            f"FROM {table} WHERE rarity = %s",
            (rarity,),
        )
    else:
        rows = _pg_query(
            f"SELECT COUNT(*) AS total_cards, "
            f"SUM(CASE WHEN rarity = 'Rare' THEN 1 ELSE 0 END) AS rare_cards, "
            f"COUNT(DISTINCT set_name) AS total_sets "
            f"FROM {table}"
        )
    row = rows[0]
    return {
        "total_cards": int(row["total_cards"]),
        "rare_cards": int(row["rare_cards"] or 0),
        "total_sets": int(row["total_sets"]),
    }


# ---------------------------------------------------------------------------
# Default gallery (Lakebase)
# ---------------------------------------------------------------------------

def get_default_cards(limit: int = 100, offset: int = 0) -> list[dict]:
    """Fetch cards from the Lakebase synced table."""
    cols = ", ".join(COLUMNS)
    table = f'"{PG_SCHEMA}"."{PG_TABLE}"'
    return _pg_query(
        f"SELECT {cols} FROM {table} ORDER BY name LIMIT %s OFFSET %s",
        (limit, offset),
    )


def get_default_cards_filtered(rarity: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """Fetch cards filtered by rarity."""
    cols = ", ".join(COLUMNS)
    table = f'"{PG_SCHEMA}"."{PG_TABLE}"'
    return _pg_query(
        f"SELECT {cols} FROM {table} WHERE rarity = %s ORDER BY name LIMIT %s OFFSET %s",
        (rarity, limit, offset),
    )


# ---------------------------------------------------------------------------
# Vector Search (hybrid search)
# ---------------------------------------------------------------------------

def search_cards(query: str, rarity: str | None = None, num_results: int = 50) -> list[dict]:
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
        kwargs["filters_json"] = f"rarity = '{rarity}'"

    results = w.vector_search_indexes.query_index(**kwargs)

    cards: list[dict] = []
    result = results.result
    if result and result.data_array:
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
