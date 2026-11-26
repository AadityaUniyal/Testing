"""
Database — SQLite storage for Manent meeting intelligence results.
"""
import json
import os
import sqlite3
from datetime import datetime
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
            raw_llm       TEXT DEFAULT '',
            telemetry     TEXT DEFAULT '{}'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS execution_telemetry (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id                  TEXT NOT NULL,
            audio_duration_seconds      REAL DEFAULT 0,
            whisper_latency_seconds     REAL DEFAULT 0,
            diarization_latency_seconds REAL DEFAULT 0,
            llm_latency_seconds         REAL DEFAULT 0,
            total_latency_seconds       REAL DEFAULT 0,
            realtime_factor             REAL DEFAULT 0,
            speech_ratio                REAL DEFAULT 0,
            silence_percentage          REAL DEFAULT 0,
            word_count                  INTEGER DEFAULT 0,
            turn_count                  INTEGER DEFAULT 0,
            speaker_count               INTEGER DEFAULT 0,
            task_count                  INTEGER DEFAULT 0,
            decision_count              INTEGER DEFAULT 0,
            device_profile              TEXT DEFAULT 'hybrid_edge_ios',
            model_versions              TEXT DEFAULT '{}',
            created_at                  TEXT
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
    if "telemetry" not in existing_cols:
        cursor.execute("ALTER TABLE meetings ADD COLUMN telemetry TEXT DEFAULT '{}'")
    conn.commit()
    conn.close()


# Ensure database and columns are initialized on module load
try:
    init_db()
except Exception as e:
    print(f"[DB] Init warning: {e}")


def save_meeting(meeting: MeetingIntelligence, raw_whisper="", raw_diarize="", raw_llm="", telemetry=None):
    """Save or update a meeting result, including execution telemetry."""
    init_db()
    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO meetings
        (meeting_id, filename, duration_sec, processed_at, speakers, speaker_stats,
         summary, key_topics, decisions, action_items, unresolved, important, transcript,
         raw_whisper, raw_diarize, raw_llm, telemetry)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        json.dumps(telemetry or {}),
    ))
    conn.commit()
    conn.close()

    if telemetry:
        save_telemetry(telemetry)


def save_telemetry(telemetry_data: dict):
    """Save performance and execution telemetry."""
    init_db()
    conn = _get_conn()
    conn.execute("""
        INSERT INTO execution_telemetry
        (meeting_id, audio_duration_seconds, whisper_latency_seconds,
         diarization_latency_seconds, llm_latency_seconds, total_latency_seconds,
         realtime_factor, speech_ratio, silence_percentage, word_count,
         turn_count, speaker_count, task_count, decision_count,
         device_profile, model_versions, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        telemetry_data.get("meeting_id", ""),
        float(telemetry_data.get("audio_duration_seconds", 0.0)),
        float(telemetry_data.get("whisper_latency_seconds", 0.0)),
        float(telemetry_data.get("diarization_latency_seconds", 0.0)),
        float(telemetry_data.get("llm_latency_seconds", 0.0)),
        float(telemetry_data.get("total_latency_seconds", 0.0)),
        float(telemetry_data.get("realtime_factor", 0.0)),
        float(telemetry_data.get("speech_ratio", 0.0)),
        float(telemetry_data.get("silence_percentage", 0.0)),
        int(telemetry_data.get("word_count", 0)),
        int(telemetry_data.get("turn_count", 0)),
        int(telemetry_data.get("speaker_count", 0)),
        int(telemetry_data.get("task_count", 0)),
        int(telemetry_data.get("decision_count", 0)),
        str(telemetry_data.get("device_profile", "hybrid_edge_ios")),
        json.dumps(telemetry_data.get("model_versions", {})),
        telemetry_data.get("created_at") or datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()


def get_telemetry(meeting_id: str) -> dict | None:
    """Retrieve execution telemetry for a meeting."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM execution_telemetry WHERE meeting_id = ? ORDER BY id DESC LIMIT 1", (meeting_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    if "model_versions" in d and isinstance(d["model_versions"], str):
        try:
            d["model_versions"] = json.loads(d["model_versions"])
        except Exception:
            pass
    return d


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
    for key in ["speakers", "speaker_stats", "key_topics", "decisions", "action_items", "unresolved", "important", "transcript", "telemetry"]:
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except json.JSONDecodeError:
                pass
    return d


def rename_speaker(meeting_id: str, old_name: str, new_name: str) -> dict | None:
    """
    Rename a speaker across all intelligence fields:
    - speakers list
    - speaker_stats list
    - transcript turns
    - action_items assignees
    - decisions decided_by
    Persists updates to local SQLite, JSON artifacts, and cloud Supabase.
    """
    meeting = get_meeting(meeting_id)
    if not meeting:
        return None

    old_clean = old_name.strip()
    new_clean = new_name.strip()
    if not old_clean or not new_clean or old_clean == new_clean:
        return meeting

    # 1. Update speakers list
    speakers = meeting.get("speakers", [])
    updated_speakers = []
    for s in speakers:
        if s == old_clean:
            updated_speakers.append(new_clean)
        else:
            updated_speakers.append(s)
    meeting["speakers"] = updated_speakers

    # 2. Update speaker_stats
    stats = meeting.get("speaker_stats", [])
    for st in stats:
        if isinstance(st, dict):
            if st.get("name") == old_clean or st.get("speaker_name") == old_clean or st.get("speaker_id") == old_clean:
                st["name"] = new_clean
                st["speaker_name"] = new_clean
    meeting["speaker_stats"] = stats

    # 3. Update transcript
    transcript = meeting.get("transcript", [])
    for turn in transcript:
        if isinstance(turn, dict):
            if turn.get("speaker") == old_clean or turn.get("speaker_name") == old_clean or turn.get("speaker_id") == old_clean:
                turn["speaker"] = new_clean
                turn["speaker_name"] = new_clean
    meeting["transcript"] = transcript

    # 4. Update action items
    actions = meeting.get("action_items", [])
    for a in actions:
        if isinstance(a, dict) and a.get("assignee") == old_clean:
            a["assignee"] = new_clean
    meeting["action_items"] = actions

    # 5. Update decisions
    decisions = meeting.get("decisions", [])
    for d in decisions:
        if isinstance(d, dict) and (d.get("decided_by") == old_clean or d.get("speaker_id") == old_clean):
            d["decided_by"] = new_clean
    meeting["decisions"] = decisions

    # Save to SQLite
    conn = _get_conn()
    conn.execute("""
        UPDATE meetings
        SET speakers = ?,
            speaker_stats = ?,
            transcript = ?,
            action_items = ?,
            decisions = ?
        WHERE meeting_id = ?
    """, (
        json.dumps(meeting["speakers"]),
        json.dumps(meeting["speaker_stats"]),
        json.dumps(meeting["transcript"]),
        json.dumps(meeting["action_items"]),
        json.dumps(meeting["decisions"]),
        meeting_id
    ))
    conn.commit()
    conn.close()

    # Update local results JSON file if present
    from app.config import RESULTS_DIR
    res_path = os.path.join(RESULTS_DIR, f"{meeting_id}.json")
    if os.path.exists(res_path):
        try:
            with open(res_path, "w", encoding="utf-8") as f:
                json.dump(meeting, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # Synchronize rename with Supabase
    try:
        from app import supabase_client
        supabase_client.rename_speaker_in_supabase(meeting_id, old_clean, new_clean)
        supabase_client.sync_meeting(meeting)
    except Exception as e:
        print(f"[DB] Supabase speaker rename sync warning: {e}")

    return meeting
