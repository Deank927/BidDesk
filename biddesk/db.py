import sqlite3
import shutil
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS leads(
  id INTEGER PRIMARY KEY, source TEXT, agency TEXT, solicitation_no TEXT, title TEXT,
  location TEXT, notice_url TEXT, posted TEXT, decision TEXT DEFAULT 'NEW',
  stage TEXT DEFAULT 'lead', dedupe_key TEXT UNIQUE, created_at TEXT);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY, lead_id INTEGER, kind TEXT, addendum_no INTEGER, filename TEXT,
  original_path TEXT, sha256 TEXT, pages INTEGER, text_status TEXT, reviewed INTEGER DEFAULT 0,
  imported_at TEXT, UNIQUE(lead_id, sha256));
CREATE TABLE IF NOT EXISTS doc_pages(doc_id INTEGER, page INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS findings(
  id INTEGER PRIMARY KEY, lead_id INTEGER, field TEXT, value TEXT, doc_id INTEGER, page INTEGER,
  snippet TEXT, source TEXT, status TEXT DEFAULT 'draft', applicable INTEGER DEFAULT 1, note TEXT);
CREATE TABLE IF NOT EXISTS manual_job_walks(
  finding_id INTEGER PRIMARY KEY REFERENCES findings(id) ON DELETE CASCADE,
  data_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS checklist(
  id INTEGER PRIMARY KEY, lead_id INTEGER, category TEXT, name TEXT, required INTEGER DEFAULT 1,
  status TEXT DEFAULT 'open', file_path TEXT, needs_signature INTEGER DEFAULT 0,
  finding_id INTEGER, notes TEXT, UNIQUE(lead_id, category, name));
CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY, lead_id INTEGER, title TEXT, due_date TEXT, done INTEGER DEFAULT 0,
  finding_id INTEGER, UNIQUE(lead_id, title));
CREATE TABLE IF NOT EXISTS estimate_lines(
  id INTEGER PRIMARY KEY, lead_id INTEGER, category TEXT, description TEXT, qty REAL,
  unit TEXT, unit_cost REAL);
CREATE TABLE IF NOT EXISTS bid_items(
  id INTEGER PRIMARY KEY, lead_id INTEGER, item_no TEXT, description TEXT, is_option INTEGER,
  qty REAL, unit TEXT, unit_price REAL, finding_id INTEGER, UNIQUE(lead_id, item_no));
CREATE TABLE IF NOT EXISTS lead_meta(lead_id INTEGER PRIMARY KEY, markup_pct REAL DEFAULT 10);
CREATE TABLE IF NOT EXISTS packages(
  id INTEGER PRIMARY KEY, lead_id INTEGER, folder TEXT, created_at TEXT, status TEXT, report TEXT);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Project:
    """A user-selected project folder: db + originals + backups + generated, kept separate."""

    def __init__(self, root):
        self.root = Path(root)
        for sub in ("originals", "backups", "generated", "working"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "biddesk.db"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def q(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        return self.conn.execute(sql, args).fetchone()

    def x(self, sql, args=()):
        cur = self.conn.execute(sql, args)
        self.conn.commit()
        return cur.lastrowid

    def setting(self, key, default=None):
        r = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return r["value"] if r else default

    def set_setting(self, key, value):
        self.x("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))

    def backup(self):
        dest = self.root / "backups" / f"biddesk_{datetime.now():%Y%m%d_%H%M%S}.db"
        b = sqlite3.connect(dest)
        self.conn.backup(b)
        b.close()
        return dest

    def close(self):
        self.conn.close()


def copy_readonly(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    dest.chmod(0o444)
    return dest

