
from __future__ import annotations
import os
import sqlite3
from typing import Optional, Iterable, Dict, Any, List, Tuple
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
    raw_hash TEXT, -- for dedup
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_user_rawhash ON transactions(user_id, raw_hash);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    pattern TEXT,          -- regex on merchant/description
    field TEXT,            -- 'merchant' or 'description'
    category TEXT,
    subcategory TEXT,
    priority INTEGER DEFAULT 100, -- lower is stronger
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    year INTEGER,
    month INTEGER,         -- 1-12
    category TEXT,
    amount REAL,           -- monthly budget for category
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS incomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    year INTEGER,
    month INTEGER,
    source TEXT,
    amount REAL,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

@contextmanager
def connect(db_path: Optional[str] = None):
    path = db_path or DB_PATH
    conn = sqlite3.connect(path, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()

def init_db(user_id: str):
    with connect() as con:
        cur = con.cursor()
        for stmt in SCHEMA_SQL.strip().split(";
"):
            s = stmt.strip()
            if s:
                cur.execute(s + ";")
        # ensure user exists
        cur.execute("INSERT OR IGNORE INTO users(id) VALUES (?)", (user_id,))

def insert_transactions(user_id: str, rows: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Returns (inserted, skipped) based on raw_hash uniques"""
    if not rows:
        return 0, 0
    with connect() as con:
        cur = con.cursor()
        inserted = 0
        skipped = 0
        for r in rows:
            try:
                cur.execute("""
                    INSERT INTO transactions
                    (user_id, date, account, merchant, description, amount, currency, category, subcategory, type, source, raw_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    r.get("date"),
                    r.get("account"),
                    r.get("merchant"),
                    r.get("description"),
                    float(r.get("amount", 0) or 0),
                    r.get("currency"),
                    r.get("category"),
                    r.get("subcategory"),
                    r.get("type"),
                    r.get("source"),
                    r.get("raw_hash"),
                ))
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
        return inserted, skipped

def upsert_budget(user_id: str, year: int, month: int, category: str, amount: float):
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT id FROM budgets WHERE user_id=? AND year=? AND month=? AND category=?
        """, (user_id, year, month, category))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE budgets SET amount=? WHERE id=?", (amount, row[0]))
        else:
            cur.execute("INSERT INTO budgets (user_id, year, month, category, amount) VALUES (?, ?, ?, ?, ?)",
                        (user_id, year, month, category, amount))

def add_income(user_id: str, year: int, month: int, source: str, amount: float):
    with connect() as con:
        cur = con.cursor()
        cur.execute("INSERT INTO incomes (user_id, year, month, source, amount) VALUES (?, ?, ?, ?, ?)",
                    (user_id, year, month, source, amount))

def list_transactions(user_id: str, year: Optional[int]=None, month: Optional[int]=None) -> List[Dict[str, Any]]:
    q = "SELECT date, account, merchant, description, amount, currency, category, subcategory, type, source FROM transactions WHERE user_id=?"
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

def get_budgets(user_id: str, year: int, month: int) -> Dict[str, float]:
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT category, amount FROM budgets WHERE user_id=? AND year=? AND month=?", (user_id, year, month))
        return {cat: amt for cat, amt in cur.fetchall()}

def get_incomes(user_id: str, year: int, month: int) -> float:
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT COALESCE(SUM(amount),0) FROM incomes WHERE user_id=? AND year=? AND month=?", (user_id, year, month))
        total = cur.fetchone()[0]
        return float(total or 0)

def add_rule(user_id: str, pattern: str, field: str, category: str, subcategory: str = "", priority: int = 100):
    with connect() as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO rules (user_id, pattern, field, category, subcategory, priority) VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, pattern, field, category, subcategory, priority))

def list_rules(user_id: str):
    with connect() as con:
        cur = con.cursor()
        cur.execute("SELECT id, pattern, field, category, subcategory, priority FROM rules WHERE user_id=? ORDER BY priority ASC, id ASC", (user_id,))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

def export_backup() -> bytes:
    with open(DB_PATH, "rb") as f:
        return f.read()

def import_backup(content: bytes):
    with open(DB_PATH, "wb") as f:
        f.write(content)
