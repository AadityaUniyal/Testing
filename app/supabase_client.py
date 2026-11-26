"""
Supabase Database Synchronization Client
Enables hybrid offline/cloud synchronization:
- If SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) are configured in the environment or .env,
  meeting intelligence reports, transcripts, action items, decisions, and speakers are automatically synced to the cloud.
- If not configured, gracefully falls back to local SQLite without disruption.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, Union
import urllib.request
import urllib.error
import urllib.parse

# Load .env if present
try:
    from pathlib import Path
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v
except Exception:
    pass

logger = logging.getLogger("meeting_intelligence.supabase")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", os.environ.get("SUPABASE_ANON_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))).strip()

def is_supabase_configured() -> bool:
    """Check if Supabase connection credentials are provided."""
    return bool(SUPABASE_URL and SUPABASE_KEY)

def is_configured() -> bool:
    """Alias for is_supabase_configured."""
    return is_supabase_configured()

def _post_rest(table: str, data: list, on_conflict: Optional[str] = None) -> bool:
    """Send a batch upsert/insert to Supabase PostgREST endpoint."""
    if not is_supabase_configured():
        return False
    
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if on_conflict:
        url += f"?on_conflict={on_conflict}"

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal"
    }

    try:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status in (200, 201, 204)
    except Exception as e:
        logger.warning(f"Supabase sync failed for table '{table}': {e}")
        return False

def _patch_rest(table: str, query_params: str, data: dict) -> bool:
    """Send a PATCH update to Supabase PostgREST endpoint with query filters."""
    if not is_supabase_configured():
        return False
    
    url = f"{SUPABASE_URL}/rest/v1/{table}?{query_params}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    try:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status in (200, 204)
    except Exception as e:
        logger.warning(f"Supabase PATCH failed for table '{table}': {e}")
        return False

def sync_meeting(meeting: Union[Dict[str, Any], Any]) -> bool:
    """Synchronize a meeting (MeetingIntelligence object or dict) to Supabase."""
    if hasattr(meeting, "model_dump"):
        meeting_dict = meeting.model_dump()
    elif isinstance(meeting, dict):
        meeting_dict = meeting
    else:
        logger.warning("Unrecognized meeting type passed to sync_meeting.")
        return False
    return sync_meeting_to_supabase(meeting_dict)

def sync_meeting_to_supabase(meeting_dict: Dict[str, Any]) -> bool:
    """
    Sync complete meeting report to Supabase:
    - meetings
    - speakers
    - transcript_segments
    - action_items
    - decisions
    """
    if not is_supabase_configured():
        logger.info("Supabase not configured (SUPABASE_URL / SUPABASE_KEY missing). Stored in local SQLite only.")
        return False

    meeting_id = meeting_dict.get("meeting_id") or meeting_dict.get("id")
    if not meeting_id:
        return False

    logger.info(f"Syncing meeting {meeting_id} to Supabase...")

    # 1. Sync Meeting record
    meeting_row = [{
        "meeting_id": meeting_id,
        "title": meeting_dict.get("title", meeting_dict.get("filename", f"Meeting {meeting_id}")),
        "audio_path": meeting_dict.get("audio_path", meeting_dict.get("filename", "")),
        "duration_seconds": float(meeting_dict.get("duration_seconds", meeting_dict.get("duration", 0.0)) or 0.0),
        "created_at": meeting_dict.get("processed_at") or meeting_dict.get("created_at"),
        "summary": meeting_dict.get("summary", ""),
        "speaker_stats": meeting_dict.get("speaker_stats", []),
        "key_topics": meeting_dict.get("key_topics", []),
        "unresolved_issues": meeting_dict.get("unresolved_issues", []),
        "important_points": meeting_dict.get("important_points", []),
        "raw_response": meeting_dict,
        "telemetry": meeting_dict.get("telemetry", {})
    }]
    _post_rest("meetings", meeting_row, on_conflict="meeting_id")

    # 2. Sync Speakers with stats
    speakers_data = []
    # Build lookup map for speaker stats
    stats_map = {}
    for st in meeting_dict.get("speaker_stats", []):
        if isinstance(st, dict):
            spk_name = st.get("speaker_name") or st.get("speaker")
            if spk_name:
                stats_map[spk_name] = st

    speaker_map = meeting_dict.get("speaker_map")
    if speaker_map and isinstance(speaker_map, dict):
        for spk_id, name in speaker_map.items():
            st = stats_map.get(name, {})
            speakers_data.append({
                "meeting_id": meeting_id,
                "speaker_id": spk_id,
                "display_name": name,
                "confidence": 1.0,
                "talk_time_seconds": float(st.get("total_speech_seconds", 0.0)),
                "talk_percentage": float(st.get("talk_percentage", 0.0)),
                "turn_count": int(st.get("turn_count", 0))
            })
    else:
        speakers = meeting_dict.get("speakers", [])
        for idx, spk in enumerate(speakers):
            display_name = spk if isinstance(spk, str) else str(spk)
            st = stats_map.get(display_name, {})
            speakers_data.append({
                "meeting_id": meeting_id,
                "speaker_id": f"SPEAKER_{idx:02d}",
                "display_name": display_name,
                "confidence": 1.0,
                "talk_time_seconds": float(st.get("total_speech_seconds", 0.0)),
                "talk_percentage": float(st.get("talk_percentage", 0.0)),
                "turn_count": int(st.get("turn_count", 0))
            })

    if speakers_data:
        _post_rest("speakers", speakers_data, on_conflict="meeting_id,speaker_id")

    # 3. Sync Transcript Segments
    segments_data = []
    transcript = meeting_dict.get("aligned_transcript") or meeting_dict.get("transcript") or []
    for idx, seg in enumerate(transcript):
        speaker_val = seg.get("speaker_id") or seg.get("speaker", "SPEAKER_00")
        speaker_name = seg.get("speaker") or seg.get("speaker_name", speaker_val)
        segments_data.append({
            "meeting_id": meeting_id,
            "segment_index": idx,
            "start_time": float(seg.get("start_sec", seg.get("start", 0.0))),
            "end_time": float(seg.get("end_sec", seg.get("end", 0.0))),
            "speaker_id": str(speaker_val),
            "speaker_name": str(speaker_name),
            "text": seg.get("text", "")
        })
    if segments_data:
        _post_rest("transcript_segments", segments_data)

    # 4. Sync Action Items
    actions_data = []
    for item in meeting_dict.get("action_items", []):
        actions_data.append({
            "meeting_id": meeting_id,
            "assignee": item.get("assignee") or "Unassigned",
            "task": item.get("task", ""),
            "deadline": item.get("deadline") or "",
            "quote": item.get("quote") or "",
            "status": item.get("status", "pending")
        })
    if actions_data:
        _post_rest("action_items", actions_data)

    # 5. Sync Decisions
    decisions_data = []
    for dec in meeting_dict.get("decisions", []):
        decisions_data.append({
            "meeting_id": meeting_id,
            "decision": dec.get("decision", ""),
            "decided_by": dec.get("speaker_id") or dec.get("decided_by") or "",
            "rationale": dec.get("rationale") or ""
        })
    if decisions_data:
        _post_rest("decisions", decisions_data)

    # 6. Sync Execution Telemetry
    telemetry = meeting_dict.get("telemetry")
    if telemetry and isinstance(telemetry, dict):
        telem_row = [{
            "meeting_id": meeting_id,
            "audio_duration_seconds": float(telemetry.get("audio_duration_seconds", 0.0)),
            "whisper_latency_seconds": float(telemetry.get("whisper_latency_seconds", 0.0)),
            "diarization_latency_seconds": float(telemetry.get("diarization_latency_seconds", 0.0)),
            "llm_latency_seconds": float(telemetry.get("llm_latency_seconds", 0.0)),
            "total_latency_seconds": float(telemetry.get("total_latency_seconds", 0.0)),
            "realtime_factor": float(telemetry.get("realtime_factor", 0.0)),
            "speech_ratio": float(telemetry.get("speech_ratio", 0.0)),
            "silence_percentage": float(telemetry.get("silence_percentage", 0.0)),
            "word_count": int(telemetry.get("word_count", 0)),
            "turn_count": int(telemetry.get("turn_count", 0)),
            "speaker_count": int(telemetry.get("speaker_count", 0)),
            "task_count": int(telemetry.get("task_count", 0)),
            "decision_count": int(telemetry.get("decision_count", 0)),
            "device_profile": str(telemetry.get("device_profile", "hybrid_edge_ios")),
            "model_versions": telemetry.get("model_versions", {})
        }]
        _post_rest("execution_telemetry", telem_row)

    logger.info(f"Successfully synced meeting {meeting_id} to Supabase cloud.")
    return True

def rename_speaker_in_supabase(meeting_id: str, old_name: str, new_name: str) -> bool:
    """
    Update speaker name across all relational tables in Supabase:
    - speakers: display_name
    - transcript_segments: speaker_name
    - action_items: assignee
    - decisions: decided_by
    """
    if not is_supabase_configured():
        return False

    old_q = urllib.parse.quote(old_name)
    # 1. Update speakers table
    _patch_rest("speakers", f"meeting_id=eq.{meeting_id}&display_name=eq.{old_q}", {"display_name": new_name})
    _patch_rest("speakers", f"meeting_id=eq.{meeting_id}&speaker_id=eq.{old_q}", {"display_name": new_name})

    # 2. Update transcript_segments table
    _patch_rest("transcript_segments", f"meeting_id=eq.{meeting_id}&speaker_name=eq.{old_q}", {"speaker_name": new_name})
    _patch_rest("transcript_segments", f"meeting_id=eq.{meeting_id}&speaker_id=eq.{old_q}", {"speaker_name": new_name})

    # 3. Update action_items
    _patch_rest("action_items", f"meeting_id=eq.{meeting_id}&assignee=eq.{old_q}", {"assignee": new_name})

    # 4. Update decisions
    _patch_rest("decisions", f"meeting_id=eq.{meeting_id}&decided_by=eq.{old_q}", {"decided_by": new_name})

    logger.info(f"Renamed speaker '{old_name}' to '{new_name}' in Supabase for meeting {meeting_id}.")
    return True
