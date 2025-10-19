# db.py
import os, sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("BUDGETBUDDY_DB", "budgetbuddy.db")

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    date TEXT,
    account TEXT,
    merchant TEXT,
    description TEXT,
    amount REAL,
    currency TEXT,
    category TEXT,
    subcategory TEXT,
    type TEXT,
    source TEXT,
    raw_hash TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_user_rawhash
  ON transactions(user_id, raw_hash);
"""

@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        yield con
    finally:
        con.commit()
        con.close()

def init_db(user_id: str):
    """Initialize schema and ensure the user row exists."""
    with connect() as con:
        cur = con.cursor()
        # Execute statements safely even if separated by newlines
        for stmt in [s.strip() for s in SCHEMA_SQL.split(";") if s.strip()]:
            cur.execute(stmt + ";")
        cur.execute("INSERT OR IGNORE INTO users(id) VALUES (?)", (user_id,))

def insert_transactions(user_id: str, rows):
    """Insert rows; de-duplicate by (user_id, raw_hash). Returns (inserted, skipped)."""
    if not rows:
        return (0, 0)
    ins = skip = 0
    with connect() as con:
        cur = con.cursor()
        for r in rows:
            try:
                cur.execute("""
                    INSERT INTO transactions
                    (user_id, date, account, merchant, description, amount, currency,
                     category, subcategory, type, source, raw_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    r.get("date"),
                    r.get("account"),
                    r.get("merchant"),
                    r.get("description"),
                    float(r.get("amount") or 0),
                    r.get("currency"),
                    r.get("category"),
                    r.get("subcategory"),
                    r.get("type"),
                    r.get("source"),
                    r.get("raw_hash"),
                ))
                ins += 1
            except sqlite3.IntegrityError:
                skip += 1
    return (ins, skip)

def list_transactions(user_id: str, year: int | None = None, month: int | None = None):
    """Return a list of dict rows for the selected year/month (if provided)."""
    q = ("SELECT date, account, merchant, description, amount, currency, "
         "category, subcategory, type, source "
         "FROM transactions WHERE user_id=?")
    params = [user_id]
    if year:
        q += " AND substr(date,1,4)=?"
        params.append(f"{year:04d}")
    if month:
        q += " AND substr(date,6,2)=?"
        params.append(f"{month:02d}")
    q += " ORDER BY date ASC"

    with connect() as con:
        cur = con.cursor()
        cur.execute(q, tuple(params))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
