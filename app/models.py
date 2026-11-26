"""
Pydantic models — shared data structures matching the Manent meeting intelligence specification.
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class SpeakerSegment(BaseModel):
    speaker_id: str
    start: float
    end: float


class AlignedSegment(BaseModel):
    start: float
    end: float
    timestamp_str: str = ""
    speaker_id: str
    speaker_name: str = ""
    text: str


class SpeakerStat(BaseModel):
    speaker_id: str
    name: str
    total_seconds: float
    formatted_time: str
    percentage: float
    turn_count: int


class ActionItem(BaseModel):
    task: str
    assignee: Optional[str] = "Unassigned"
    deadline: Optional[str] = "Not specified"
    evidence: Optional[str] = None
    timestamp: Optional[str] = None
    commitment_type: Optional[str] = None
    status: str = "open"  # open, in_progress, completed


class Decision(BaseModel):
    decision: str
    status: str = "RESOLVED"  # RESOLVED, DEFERRED
    decided_by: Optional[str] = None
    timestamp: Optional[str] = None
    evidence: Optional[str] = None


class MeetingIntelligence(BaseModel):
    meeting_id: str
    filename: str
    duration_seconds: float = 0.0
    processed_at: str = ""
    speakers: List[str] = []
    speaker_stats: List[SpeakerStat] = []
    summary: str = ""
    key_topics: List[str] = []
    decisions: List[Decision] = []
    action_items: List[ActionItem] = []
    unresolved_issues: List[str] = []
    important_points: List[str] = []
    aligned_transcript: List[AlignedSegment] = []


class PipelineStatus(BaseModel):
    meeting_id: str
    stage: str
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None
