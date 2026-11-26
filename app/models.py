"""
Pydantic models — shared data structures for the pipeline.
"""
from pydantic import BaseModel
from typing import Optional
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
    speaker_id: str
    text: str


class ActionItem(BaseModel):
    task: str
    assignee: Optional[str] = None
    deadline: Optional[str] = None
    evidence: Optional[str] = None
    commitment_type: Optional[str] = None
    status: str = "pending"


class Decision(BaseModel):
    decision: str
    speaker_id: Optional[str] = None


class MeetingIntelligence(BaseModel):
    meeting_id: str
    filename: str
    duration_seconds: float = 0.0
    processed_at: str = ""
    speakers: list[str] = []
    summary: str = ""
    decisions: list[Decision] = []
    action_items: list[ActionItem] = []
    unresolved_issues: list[str] = []
    important_points: list[str] = []
    aligned_transcript: list[AlignedSegment] = []


class PipelineStatus(BaseModel):
    meeting_id: str
    stage: str
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None
