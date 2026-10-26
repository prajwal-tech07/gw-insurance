"""SQLite storage for saved policies, complaint trackers and court cases.

Uploaded documents are never stored: only the policy terms the user confirms.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from app.config import db_path
from app.models import Case, ComplaintData, PolicyTerms, SavedPolicy

SCHEMA = """
CREATE TABLE IF NOT EXISTS policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    terms_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    source TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- policies

def _policy(row: sqlite3.Row) -> SavedPolicy:
    return SavedPolicy(id=row["id"], name=row["name"], terms=PolicyTerms.model_validate_json(row["terms_json"]),
                       created_at=row["created_at"], updated_at=row["updated_at"])


def create_policy(name: str, terms: PolicyTerms) -> SavedPolicy:
    now = _now()
    with connect() as conn:
        cur = conn.execute("INSERT INTO policies (name, terms_json, created_at, updated_at) VALUES (?, ?, ?, ?)",
                           (name, terms.model_dump_json(), now, now))
        row = conn.execute("SELECT * FROM policies WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _policy(row)


def list_policies() -> list[SavedPolicy]:
    with connect() as conn:
        return [_policy(r) for r in conn.execute("SELECT * FROM policies ORDER BY updated_at DESC, id DESC")]


def get_policy(policy_id: int) -> SavedPolicy | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM policies WHERE id = ?", (policy_id,)).fetchone()
    return _policy(row) if row else None


def update_policy(policy_id: int, name: str, terms: PolicyTerms) -> SavedPolicy | None:
    with connect() as conn:
        cur = conn.execute("UPDATE policies SET name = ?, terms_json = ?, updated_at = ? WHERE id = ?",
                           (name, terms.model_dump_json(), _now(), policy_id))
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM policies WHERE id = ?", (policy_id,)).fetchone()
    return _policy(row)


def delete_policy(policy_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM policies WHERE id = ?", (policy_id,)).rowcount > 0


# ---------------------------------------------------------------- complaints

def create_complaint(data: ComplaintData) -> int:
    now = _now()
    with connect() as conn:
        cur = conn.execute("INSERT INTO complaints (data_json, created_at, updated_at) VALUES (?, ?, ?)",
                           (data.model_dump_json(), now, now))
        return int(cur.lastrowid)


def list_complaints() -> list[tuple[int, ComplaintData]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM complaints ORDER BY id DESC").fetchall()
    return [(r["id"], ComplaintData.model_validate_json(r["data_json"])) for r in rows]


def get_complaint(complaint_id: int) -> ComplaintData | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    return ComplaintData.model_validate_json(row["data_json"]) if row else None


def update_complaint(complaint_id: int, data: ComplaintData) -> bool:
    with connect() as conn:
        cur = conn.execute("UPDATE complaints SET data_json = ?, updated_at = ? WHERE id = ?",
                           (data.model_dump_json(), _now(), complaint_id))
        return cur.rowcount > 0


def delete_complaint(complaint_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM complaints WHERE id = ?", (complaint_id,)).rowcount > 0


# ---------------------------------------------------------------- cases

def upsert_cases(cases: list[Case], source: str) -> int:
    with connect() as conn:
        conn.executemany(
            "INSERT INTO cases (id, data_json, source) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data_json = excluded.data_json, source = excluded.source",
            [(c.id, c.model_dump_json(), source) for c in cases])
    return len(cases)


def list_cases() -> list[Case]:
    with connect() as conn:
        rows = conn.execute("SELECT data_json FROM cases ORDER BY id").fetchall()
    return [Case.model_validate_json(r["data_json"]) for r in rows]
