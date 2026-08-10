from pathlib import Path
import psycopg
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from databricks.sdk import WorkspaceClient

import config

_pool = None
_workspace = None


class OAuthConnection(psycopg.Connection):
    @classmethod
    def connect(cls, conninfo="", **kwargs):
        global _workspace
        if _workspace is None:
            _workspace = WorkspaceClient()
        if not config.ENDPOINT_NAME:
            raise RuntimeError(
                "ENDPOINT_NAME is missing. Attach the Lakebase Autoscaling database "
                "as a Databricks App resource with key 'postgres'."
            )
        credential = _workspace.postgres.generate_database_credential(
            endpoint=config.ENDPOINT_NAME
        )
        kwargs["password"] = credential.token
        return super().connect(conninfo, **kwargs)


def get_pool():
    global _pool
    if _pool is not None:
        return _pool

    if config.DATABASE_URL:
        _pool = ConnectionPool(
            conninfo=config.DATABASE_URL,
            min_size=1,
            max_size=8,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        return _pool

    missing = [
        name
        for name, value in {
            "PGHOST": config.PGHOST,
            "PGUSER": config.PGUSER,
            "PGDATABASE": config.PGDATABASE,
            "ENDPOINT_NAME": config.ENDPOINT_NAME,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing Lakebase configuration: " + ", ".join(missing)
        )

    conninfo = (
        f"dbname={config.PGDATABASE} "
        f"user={config.PGUSER} "
        f"host={config.PGHOST} "
        f"port={config.PGPORT} "
        f"sslmode={config.PGSSLMODE}"
    )
    _pool = ConnectionPool(
        conninfo=conninfo,
        connection_class=OAuthConnection,
        min_size=1,
        max_size=8,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    return _pool


def init_schema():
    schema_path = Path(__file__).parent / "sql" / "schema.sql"
    ddl = schema_path.read_text(encoding="utf-8")
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()


def fetch_all(sql, params=None):
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def fetch_one(sql, params=None):
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()


def execute(sql, params=None, returning=False):
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone() if returning else None
        conn.commit()
        return row
