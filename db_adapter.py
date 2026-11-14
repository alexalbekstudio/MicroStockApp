# db_adapter.py
"""
Dual-Mode Database Adapter za MicroStockApp (Standalone & Server Edition).
- Ako je podešen DATABASE_URL (ili DB_ENGINE=postgres), koristi PostgreSQL.
- Ako je DATABASE_URL prazan, automatski koristi ugrađeni SQLite (microstock_local.db)
  i u letu prevodi PostgreSQL sintaksu u SQLite sintaksu.
"""

import os
import re
import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager

log = logging.getLogger(__name__)

SQLITE_DB_PATH = Path(__file__).parent / "microstock_local.db"
SQLITE_DEMO_PATH = Path(__file__).parent / "microstock_demo.db"


def _should_use_postgres() -> bool:
    url = (os.environ.get("DATABASE_URL") or os.environ.get("DB_URL") or "").strip()
    engine = (os.environ.get("DB_ENGINE") or "").strip().lower()
    if url.startswith(("postgres://", "postgresql://")) or engine == "postgres":
        return True
    return False


USE_POSTGRES = _should_use_postgres()
DATABASE_URL = None

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
    import psycopg2.extensions
    from psycopg2.pool import ThreadedConnectionPool

    DEC2FLOAT = psycopg2.extensions.new_type(
        psycopg2.extensions.DECIMAL.values,
        "DEC2FLOAT",
        lambda value, curs: float(value) if value is not None else None,
    )
    psycopg2.extensions.register_type(DEC2FLOAT)


def _refresh_module_globals():
    global USE_POSTGRES, DATABASE_URL
    USE_POSTGRES = _should_use_postgres()
    DATABASE_URL = _database_url() if USE_POSTGRES else f"sqlite:///{SQLITE_DB_PATH}"


def get_conn():
    return connect()


def adapt_query(sql):
    return sql if USE_POSTGRES else _pg_to_sqlite_sql(sql)


def adapt_schema(schema_sql):
    return schema_sql if USE_POSTGRES else _pg_to_sqlite_sql(schema_sql)


# ---------------------------------------------------------------------------
# PostgreSQL -> SQLite automatski prevodilac upita
# ---------------------------------------------------------------------------

def _pg_to_sqlite_sql(sql: str) -> str:
    s = sql.strip()

    # 1. Placeholders: %s -> ?
    s = s.replace("%s", "?")

    # 2. DDL i tipovi za kreiranje tabela i pogleda
    s = re.sub(r"\bSERIAL\s+PRIMARY\s+KEY\b", "INTEGER PRIMARY KEY AUTOINCREMENT", s, flags=re.IGNORECASE)
    s = re.sub(r"DROP\s+VIEW\s+IF\s+EXISTS\s+([a-zA-Z0-9_.]+)\s+CASCADE", r"DROP VIEW IF EXISTS \1", s, flags=re.IGNORECASE)
    s = re.sub(r"CREATE\s+OR\s+REPLACE\s+VIEW\s+([a-zA-Z0-9_.]+)", r"CREATE VIEW IF NOT EXISTS \1", s, flags=re.IGNORECASE)
    s = re.sub(r"\bpublic\.", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\bdemo\.", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\bBYTEA\b", "BLOB", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNOW\(\)", "CURRENT_TIMESTAMP", s, flags=re.IGNORECASE)

    # 3. ALTER TABLE ... ADD COLUMN IF NOT EXISTS
    s = re.sub(r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\b", "ADD COLUMN", s, flags=re.IGNORECASE)

    # 4. ILIKE -> LIKE
    s = re.sub(r"\bILIKE\b", "LIKE", s, flags=re.IGNORECASE)

    # 5. Svi PostgreSQL INTERVAL izrazi (+ i -, sa CURRENT_DATE ili CURRENT_TIMESTAMP/NOW(), parametarski i fiksni)
    # 5a) Dinamički sa parametrom: CURRENT_TIMESTAMP - (? || ' days')::interval ili INTERVAL ? DAY
    s = re.sub(
        r"(?:CURRENT_TIMESTAMP|CURRENT_DATE)\s*([+-])\s*\(\?\s*\|\|\s*' days?'\)::interval",
        r"datetime('now', '\1' || ? || ' days')",
        s,
        flags=re.IGNORECASE,
    )
    # 5b) Fiksni sa CURRENT_DATE: CURRENT_DATE + INTERVAL '14 days' ili CURRENT_DATE - INTERVAL '30 days'
    s = re.sub(
        r"CURRENT_DATE\s*([+-])\s*INTERVAL\s*'(\d+)\s*days?'",
        r"date('now', '\1\2 days')",
        s,
        flags=re.IGNORECASE,
    )
    # 5c) Fiksni sa CURRENT_TIMESTAMP / NOW(): CURRENT_TIMESTAMP - INTERVAL '7 days'
    s = re.sub(
        r"CURRENT_TIMESTAMP\s*([+-])\s*INTERVAL\s*'(\d+)\s*days?'",
        r"datetime('now', '\1\2 days')",
        s,
        flags=re.IGNORECASE,
    )
    # 5d) Bilo koji preostali + / - INTERVAL 'X days' (npr. nad kolonom ili zagradom)
    s = re.sub(
        r"([+-])\s*INTERVAL\s*'(\d+)\s*days?'",
        r"\1 \2",
        s,
        flags=re.IGNORECASE,
    )

    # 6. DATE_TRUNC('month' / 'day', col) -> strftime
    s = re.sub(
        r"DATE_TRUNC\(\s*'month'\s*,\s*([^)]+)\)",
        r"strftime('%Y-%m', \1)",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"DATE_TRUNC\(\s*'day'\s*,\s*([^)]+)\)",
        r"date(\1)",
        s,
        flags=re.IGNORECASE,
    )

    # 7. PostgreSQL type casts (::date, ::timestamp, ::text, ::numeric, ::interval)
    s = re.sub(r"([a-zA-Z0-9_.)]+)::date\b", r"date(\1)", s, flags=re.IGNORECASE)
    s = re.sub(r"::(?:timestamp|text|numeric(?:\(\d+,\d+\))?|int|integer|float|interval)\b", "", s, flags=re.IGNORECASE)

    # 8. SELECT DISTINCT ON (source_currency, target_currency) u currency_rates.py
    if "DISTINCT ON (source_currency, target_currency)" in s:
        s = """
            SELECT source_currency, target_currency, rate, rate_date, fetched_at
            FROM exchange_rates
            WHERE id IN (
                SELECT MAX(id) FROM exchange_rates GROUP BY source_currency, target_currency
            )
            ORDER BY source_currency, target_currency
        """

    return s


# ---------------------------------------------------------------------------
# SQLite Wrapper (kada aplikacija radi u Desktop / Lokalnom režimu)
# ---------------------------------------------------------------------------

def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


class _SQLiteConnWrapper:
    def __init__(self, db_path: Path):
        self._raw = sqlite3.connect(str(db_path), check_same_thread=False, timeout=20.0)
        self._raw.row_factory = _dict_factory
        self._raw.execute("PRAGMA foreign_keys = ON;")
        self._raw.execute("PRAGMA journal_mode = WAL;")
        self._closed = False

    def execute(self, sql: str, params=None):
        q = _pg_to_sqlite_sql(sql)
        if q.upper().startswith("SET SEARCH_PATH"):
            cur = self._raw.cursor()
            return cur
        cur = self._raw.cursor()
        try:
            # Konvertuj date/datetime objekte u stringove za SQLite
            clean_params = tuple(
                str(p) if hasattr(p, "isoformat") else p
                for p in (params or ())
            )
            cur.execute(q, clean_params)
        except Exception:
            self._raw.rollback()
            cur.close()
            raise
        return cur

    def executemany(self, sql: str, seq_of_params):
        q = _pg_to_sqlite_sql(sql)
        cur = self._raw.cursor()
        try:
            cur.executemany(q, seq_of_params)
        except Exception:
            self._raw.rollback()
            cur.close()
            raise
        return cur

    def executescript(self, script: str):
        cur = self._raw.cursor()
        try:
            cur.executescript(_pg_to_sqlite_sql(script))
        except Exception:
            self._raw.rollback()
            cur.close()
            raise
        return cur

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                self._raw.close()
            except Exception:
                pass

    def cursor(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


# ---------------------------------------------------------------------------
# PostgreSQL Konfiguracija i Wrapper (za Server / Docker režim)
# ---------------------------------------------------------------------------

def _database_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    user = os.environ.get("PGUSER", "postgres")
    pwd  = os.environ.get("PGPASSWORD", "postgres")
    db   = os.environ.get("PGDATABASE", "microstock")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


_POOL = None


def _get_pool():
    global _POOL
    if _POOL is None:
        dsn = _database_url()
        log.info("Kreiram PostgreSQL ThreadedConnectionPool")
        _POOL = ThreadedConnectionPool(
            minconn=2,
            maxconn=30,
            dsn=dsn,
            cursor_factory=psycopg2.extras.RealDictCursor,
            options="-c extra_float_digits=3",
        )
    return _POOL


class _ConnWrapper:
    def __init__(self, raw_conn, pool):
        self._raw = raw_conn
        self._pool = pool
        self._closed = False

    def execute(self, sql: str, params=None):
        sql = sql.replace("?", "%s")
        cur = self._raw.cursor()
        try:
            cur.execute(sql, params or ())
        except Exception:
            self._raw.rollback()
            cur.close()
            raise
        return cur

    def executemany(self, sql: str, seq_of_params):
        sql = sql.replace("?", "%s")
        cur = self._raw.cursor()
        try:
            cur.executemany(sql, seq_of_params)
        except Exception:
            self._raw.rollback()
            cur.close()
            raise
        return cur

    def executescript(self, script: str):
        cur = self._raw.cursor()
        try:
            cur.execute(script)
        except Exception:
            self._raw.rollback()
            cur.close()
            raise
        return cur

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._raw.rollback()
        except Exception:
            pass
        try:
            self._pool.putconn(self._raw)
        except Exception:
            try:
                self._raw.close()
            except Exception:
                pass

    def cursor(self, *args, **kwargs):
        return self._raw.cursor(*args, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            try:
                self.commit()
            except Exception:
                self.rollback()
                raise
        else:
            self.rollback()
        self.close()


def connect():
    _refresh_module_globals()
    is_demo = False
    try:
        from flask import has_request_context, session, request
        if has_request_context():
            endpoint = request.endpoint or ""
            if not (
                "auth." in endpoint
                or request.path in ("/login", "/logout", "/demo/exit", "/forgot-password")
                or request.path.startswith("/reset-password")
            ):
                if session.get("demo_mode"):
                    is_demo = True
    except Exception:
        pass

    if not USE_POSTGRES:
        return _SQLiteConnWrapper(SQLITE_DEMO_PATH if is_demo else SQLITE_DB_PATH)

    return connect_demo() if is_demo else _connect_public()


def _connect_public():
    if not USE_POSTGRES:
        return _SQLiteConnWrapper(SQLITE_DB_PATH)
    pool = _get_pool()
    raw = pool.getconn()
    try:
        cur = raw.cursor()
        try:
            cur.execute("SET search_path TO public;")
            raw.commit()
        finally:
            cur.close()
    except Exception:
        raw.rollback()
        pool.putconn(raw)
        raise
    return _ConnWrapper(raw, pool)


def connect_demo():
    if not USE_POSTGRES:
        return _SQLiteConnWrapper(SQLITE_DEMO_PATH)
    pool = _get_pool()
    raw = pool.getconn()
    try:
        cur = raw.cursor()
        try:
            cur.execute("SET search_path TO demo, public;")
            raw.commit()
        finally:
            cur.close()
    except Exception as e:
        raw.rollback()
        pool.putconn(raw)
        log.error(f"Ne mogu da postavim search_path na demo: {e}")
        raise
    return _ConnWrapper(raw, pool)


# ---------------------------------------------------------------------------
# Helperi
# ---------------------------------------------------------------------------

def query(sql: str, params=None):
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def query_one(sql: str, params=None):
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        return cur.fetchone()
    finally:
        conn.close()


def execute(sql: str, params=None):
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_returning(sql: str, params=None):
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        conn.commit()
        return row
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def healthcheck():
    try:
        if not USE_POSTGRES:
            row = query_one("SELECT sqlite_version() AS v")
            return True, {"version": f"SQLite {row['v']}", "database": str(SQLITE_DB_PATH.name)}
        row = query_one("SELECT version() AS v, current_database() AS db")
        return True, {"version": row["v"], "database": row["db"]}
    except Exception as e:
        return False, str(e)


_refresh_module_globals()