"""SQLite — 讓狀態不會在程序結束時蒸發。

現在的 CLI:AuditLog 存在記憶體 list,每次 run.py 重新建一條空的。
後端:同樣的 Entry,改寫進這裡的 audit_entries 表,任何 session 都讀得到同一條鏈。

只用標準庫的 sqlite3。每個 request 開一條新連線(sqlite 對這個很在行),用完即關。
"""

import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("CLAIM_DB_PATH") or os.path.join(HERE, "app.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    password      TEXT NOT NULL,              -- pbkdf2 salt$hash,見 auth.py
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL,              -- worker | agency_officer | auditor
    acting_for    TEXT,                       -- 代表哪個組織(顯示名),自然人留 NULL
    org_lei       TEXT,
    role_credential TEXT,                     -- 證明代理關係的 ECR 憑證 SAID
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    id             TEXT PRIMARY KEY,          -- 例:WIC-2026-0829-4F2A
    worker_user_id INTEGER NOT NULL,
    title          TEXT NOT NULL,
    status         TEXT NOT NULL,             -- OPEN | DOCS_PENDING | SUBMITTED | ...
    created_at     TEXT NOT NULL
);

-- 機制 2/6:授權範圍、期限、撤銷。對應 trustagent.models.Grant
CREATE TABLE IF NOT EXISTS grants (
    id          TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    purpose     TEXT NOT NULL,
    scopes      TEXT NOT NULL,                -- 逗號分隔:claim_prep,employer_record
    expires_at  TEXT NOT NULL,
    revoked_at  TEXT,
    UNIQUE(case_id, user_id)
);

-- 機制 5:稽核鏈。欄位與 trustagent.audit.Entry 一一對應
CREATE TABLE IF NOT EXISTS audit_entries (
    case_id   TEXT NOT NULL,
    seq       INTEGER NOT NULL,
    ts        TEXT NOT NULL,
    principal TEXT NOT NULL,
    tool      TEXT NOT NULL,
    code      TEXT NOT NULL,
    allowed   INTEGER NOT NULL,               -- 0/1
    detail    TEXT NOT NULL,                  -- JSON
    prev      TEXT NOT NULL,
    hash      TEXT NOT NULL,
    sig       TEXT,
    PRIMARY KEY (case_id, seq)
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
