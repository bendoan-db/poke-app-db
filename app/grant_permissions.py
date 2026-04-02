"""
Grant the app's service principal SELECT access to the synced table schema
in Lakebase. Run this after deploying the app.

Usage:
    source .databricks/.databricks.env
    .venv/bin/python app/grant_permissions.py

Or via Databricks Connect:
    python app/grant_permissions.py
"""

import os
import sys

import psycopg
from databricks.sdk import WorkspaceClient

# ---------------------------------------------------------------------------
# Configuration — override via env vars or edit defaults
# ---------------------------------------------------------------------------
PG_PROJECT = os.getenv("PG_PROJECT", "pokemondb")
PG_BRANCH = os.getenv("PG_BRANCH", "production")
PG_DATABASE = os.getenv("PG_DATABASE", "pokebase")
PG_SCHEMA = os.getenv("PG_SCHEMA", "pokemon_cards")
APP_NAME = os.getenv("APP_NAME", "pokemon-card-explorer-dev")


def main():
    w = WorkspaceClient()

    # 1. Get the app's service principal ID
    print(f"Looking up app '{APP_NAME}'...")
    app = w.apps.get(APP_NAME)
    sp_id = app.service_principal_id
    print(f"App service principal ID: {sp_id}")

    # 2. Resolve the SP's username (used as the Postgres role name)
    sp = w.service_principals.get(sp_id)
    sp_username = sp.application_id  # This is the UUID used as PG role
    print(f"Service principal application ID (PG role): {sp_username}")

    # 3. Connect to Lakebase as the current user (who owns the schema)
    ep_name = f"projects/{PG_PROJECT}/branches/{PG_BRANCH}/endpoints/primary"
    endpoint = w.postgres.get_endpoint(name=ep_name)
    host = endpoint.status.hosts.host

    cred = w.postgres.generate_database_credential(endpoint=ep_name)
    current_user = w.current_user.me().user_name

    print(f"Connecting to {host} / {PG_DATABASE} as {current_user}...")
    conn = psycopg.connect(
        host=host,
        dbname=PG_DATABASE,
        user=current_user,
        password=cred.token,
        sslmode="require",
        autocommit=True,
    )

    # 4. Grant permissions
    with conn.cursor() as cur:
        # Check if the role exists
        cur.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (sp_username,)
        )
        if not cur.fetchone():
            print(f"WARNING: Role '{sp_username}' not found in pg_roles.")
            print("The app may need to connect once first to create its role.")
            print("Available roles:")
            cur.execute("SELECT rolname FROM pg_roles ORDER BY rolname")
            for row in cur.fetchall():
                print(f"  {row[0]}")
            conn.close()
            sys.exit(1)

        print(f"Granting USAGE on schema {PG_SCHEMA} to {sp_username}...")
        cur.execute(
            f'GRANT USAGE ON SCHEMA "{PG_SCHEMA}" TO "{sp_username}"'
        )

        print(f"Granting SELECT on all tables in {PG_SCHEMA} to {sp_username}...")
        cur.execute(
            f'GRANT SELECT ON ALL TABLES IN SCHEMA "{PG_SCHEMA}" TO "{sp_username}"'
        )

        print("Granting default privileges for future tables...")
        cur.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{PG_SCHEMA}" '
            f'GRANT SELECT ON TABLES TO "{sp_username}"'
        )

    conn.close()
    print("Permissions granted successfully.")


if __name__ == "__main__":
    main()
