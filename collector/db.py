"""
SQLite storage. One file, no server, and plain SQL, so it's easy to inspect.

Every load is an UPSERT (insert, or update if the row already exists). That makes
runs idempotent: running the collector twice in a day never creates duplicates.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS job_postings (
    job_id              TEXT PRIMARY KEY,
    search_term         TEXT NOT NULL,
    title               TEXT NOT NULL,
    company             TEXT,
    location            TEXT,
    state               TEXT,
    salary_min          REAL,
    salary_max          REAL,
    salary_is_predicted INTEGER,
    contract_time       TEXT,
    contract_type       TEXT,
    category            TEXT,
    description         TEXT,
    mentions_sponsorship INTEGER NOT NULL DEFAULT 0,
    says_no_sponsorship  INTEGER NOT NULL DEFAULT 0,
    url                 TEXT,
    posted_at           TEXT,
    first_seen_at       TEXT NOT NULL,
    last_seen_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_skills (
    job_id  TEXT NOT NULL REFERENCES job_postings (job_id),
    skill   TEXT NOT NULL,
    PRIMARY KEY (job_id, skill)
);

CREATE TABLE IF NOT EXISTS weather_daily (
    city             TEXT NOT NULL,
    date             TEXT NOT NULL,
    temp_max_c       REAL,
    temp_min_c       REAL,
    precipitation_mm REAL,
    wind_max_kmh     REAL,
    weather_code     INTEGER,
    is_forecast      INTEGER NOT NULL,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (city, date)
);

CREATE TABLE IF NOT EXISTS reddit_posts (
    post_id       TEXT PRIMARY KEY,
    subreddit     TEXT NOT NULL,
    title         TEXT NOT NULL,
    flair         TEXT,
    score         INTEGER,
    num_comments  INTEGER,
    created_at    TEXT NOT NULL,
    permalink     TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_log (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,          -- success | failed | skipped
    rows_loaded INTEGER,
    message     TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_posted ON job_postings (posted_at);
CREATE INDEX IF NOT EXISTS idx_skills_skill ON job_skills (skill);
"""


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def connect(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert(conn: sqlite3.Connection, table: str, rows: list[dict], key: tuple[str, ...],
           keep_on_update: tuple[str, ...] = ()) -> int:
    """
    Insert rows; when the key already exists, update every other column
    except those in keep_on_update (e.g. first_seen_at must never change).
    """
    if not rows:
        return 0
    cols = list(rows[0].keys())
    updates = [c for c in cols if c not in key and c not in keep_on_update]
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) "
        f"ON CONFLICT ({', '.join(key)}) DO "
        + (f"UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in updates)}" if updates else "NOTHING")
    )
    conn.executemany(sql, rows)
    return len(rows)
