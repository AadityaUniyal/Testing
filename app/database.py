"""
Database — SQLite storage for Manent meeting intelligence results.
"""
import json
import os
import sqlite3
from app.config import DB_PATH
from app.models import MeetingIntelligence


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist and run non-destructive migrations."""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meetings (
            meeting_id    TEXT PRIMARY KEY,
            filename      TEXT NOT NULL,
            duration_sec  REAL DEFAULT 0,
            processed_at  TEXT,
            speakers      TEXT DEFAULT '[]',
            speaker_stats TEXT DEFAULT '[]',
            summary       TEXT DEFAULT '',
            key_topics    TEXT DEFAULT '[]',
            decisions     TEXT DEFAULT '[]',
            action_items  TEXT DEFAULT '[]',
            unresolved    TEXT DEFAULT '[]',
            important     TEXT DEFAULT '[]',
            transcript    TEXT DEFAULT '[]',
            raw_whisper   TEXT DEFAULT '',
            raw_diarize   TEXT DEFAULT '',
            raw_llm       TEXT DEFAULT ''
        )
    """)
    conn.commit()

    # Safe column migrations for existing databases
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(meetings)")
    existing_cols = [c[1] for c in cursor.fetchall()]

    if "speaker_stats" not in existing_cols:
        cursor.execute("ALTER TABLE meetings ADD COLUMN speaker_stats TEXT DEFAULT '[]'")
    if "key_topics" not in existing_cols:
        cursor.execute("ALTER TABLE meetings ADD COLUMN key_topics TEXT DEFAULT '[]'")
    conn.commit()
    conn.close()


# Ensure database and columns are initialized on module load
try:
    init_db()
except Exception as e:
    print(f"[DB] Init warning: {e}")


def save_meeting(meeting: MeetingIntelligence, raw_whisper="", raw_diarize="", raw_llm=""):
    """Save or update a meeting result."""
    init_db()
    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO meetings
        (meeting_id, filename, duration_sec, processed_at, speakers, speaker_stats,
         summary, key_topics, decisions, action_items, unresolved, important, transcript,
         raw_whisper, raw_diarize, raw_llm)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        meeting.meeting_id,
        meeting.filename,
        meeting.duration_seconds,
        meeting.processed_at,
        json.dumps(meeting.speakers),
        json.dumps([s.model_dump() for s in meeting.speaker_stats]),
        meeting.summary,
        json.dumps(meeting.key_topics),
        json.dumps([d.model_dump() for d in meeting.decisions]),
        json.dumps([a.model_dump() for a in meeting.action_items]),
        json.dumps(meeting.unresolved_issues),
        json.dumps(meeting.important_points),
        json.dumps([s.model_dump() for s in meeting.aligned_transcript]),
        raw_whisper,
        raw_diarize,
        raw_llm,
    ))
    conn.commit()
    conn.close()


def get_meeting(meeting_id: str) -> dict | None:
    """Retrieve a meeting by ID."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM meetings WHERE meeting_id = ?", (meeting_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_dict(row)


def list_meetings() -> list[dict]:
    """List all meetings (summary only)."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT meeting_id, filename, duration_sec, processed_at, speakers, speaker_stats, summary, "
        "(SELECT count(*) FROM meetings) as total_count "
        "FROM meetings ORDER BY processed_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key in ["speakers", "speaker_stats", "key_topics", "decisions", "action_items", "unresolved", "important", "transcript"]:
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except json.JSONDecodeError:
                pass
    return d
