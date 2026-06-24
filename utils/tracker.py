import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "applied_jobs.db"


def _conn():
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            portal   TEXT NOT NULL,
            job_id   TEXT NOT NULL,
            title    TEXT,
            company  TEXT,
            url      TEXT,
            status   TEXT DEFAULT 'applied',
            applied_at TEXT,
            UNIQUE(portal, job_id)
        )
    """)
    db.commit()
    return db


def already_applied(portal: str, job_id: str) -> bool:
    with _conn() as db:
        row = db.execute(
            "SELECT 1 FROM applications WHERE portal=? AND job_id=?",
            (portal, job_id),
        ).fetchone()
    return row is not None


def record(portal: str, job_id: str, title: str, company: str, url: str):
    with _conn() as db:
        try:
            db.execute(
                "INSERT INTO applications (portal,job_id,title,company,url,applied_at) VALUES (?,?,?,?,?,?)",
                (portal, job_id, title, company, url, datetime.now().isoformat()),
            )
            db.commit()
        except sqlite3.IntegrityError:
            pass  # duplicate — already tracked


def summary():
    with _conn() as db:
        rows = db.execute(
            "SELECT portal, COUNT(*) FROM applications GROUP BY portal"
        ).fetchall()
    return {r[0]: r[1] for r in rows}
