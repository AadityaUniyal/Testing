-- Supabase SQL Schema for Meeting Intelligence Platform

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Meetings Table
CREATE TABLE IF NOT EXISTS public.meetings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id VARCHAR(64) UNIQUE NOT NULL,
    title TEXT NOT NULL,
    audio_path TEXT,
    duration_seconds FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    summary TEXT,
    raw_response JSONB,
    telemetry JSONB DEFAULT '{}'::jsonb
);

-- Index for quick lookups by meeting_id and created_at
CREATE INDEX IF NOT EXISTS idx_meetings_meeting_id ON public.meetings(meeting_id);
CREATE INDEX IF NOT EXISTS idx_meetings_created_at ON public.meetings(created_at DESC);

-- 2. Speakers Table
CREATE TABLE IF NOT EXISTS public.speakers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id VARCHAR(64) REFERENCES public.meetings(meeting_id) ON DELETE CASCADE,
    speaker_id VARCHAR(32) NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(meeting_id, speaker_id)
);

CREATE INDEX IF NOT EXISTS idx_speakers_meeting_id ON public.speakers(meeting_id);

-- 3. Transcript Segments Table
CREATE TABLE IF NOT EXISTS public.transcript_segments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id VARCHAR(64) REFERENCES public.meetings(meeting_id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    speaker_id VARCHAR(32) NOT NULL,
    speaker_name VARCHAR(128) NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transcript_meeting_id ON public.transcript_segments(meeting_id);
CREATE INDEX IF NOT EXISTS idx_transcript_start_time ON public.transcript_segments(meeting_id, start_time);

-- 4. Action Items Table
CREATE TABLE IF NOT EXISTS public.action_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id VARCHAR(64) REFERENCES public.meetings(meeting_id) ON DELETE CASCADE,
    assignee VARCHAR(128) NOT NULL,
    task TEXT NOT NULL,
    deadline VARCHAR(128),
    status VARCHAR(32) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_action_items_meeting_id ON public.action_items(meeting_id);
CREATE INDEX IF NOT EXISTS idx_action_items_assignee ON public.action_items(assignee);

-- 5. Decisions Table
CREATE TABLE IF NOT EXISTS public.decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id VARCHAR(64) REFERENCES public.meetings(meeting_id) ON DELETE CASCADE,
    decision TEXT NOT NULL,
    decided_by VARCHAR(128),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decisions_meeting_id ON public.decisions(meeting_id);

-- 6. Execution Telemetry Table
CREATE TABLE IF NOT EXISTS public.execution_telemetry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id VARCHAR(64) REFERENCES public.meetings(meeting_id) ON DELETE CASCADE,
    audio_duration_seconds FLOAT DEFAULT 0.0,
    whisper_latency_seconds FLOAT DEFAULT 0.0,
    diarization_latency_seconds FLOAT DEFAULT 0.0,
    llm_latency_seconds FLOAT DEFAULT 0.0,
    total_latency_seconds FLOAT DEFAULT 0.0,
    realtime_factor FLOAT DEFAULT 0.0,
    speech_ratio FLOAT DEFAULT 0.0,
    silence_percentage FLOAT DEFAULT 0.0,
    word_count INTEGER DEFAULT 0,
    turn_count INTEGER DEFAULT 0,
    speaker_count INTEGER DEFAULT 0,
    task_count INTEGER DEFAULT 0,
    decision_count INTEGER DEFAULT 0,
    device_profile TEXT DEFAULT 'hybrid_edge_ios',
    model_versions JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_telemetry_meeting_id ON public.execution_telemetry(meeting_id);
ALTER TABLE public.execution_telemetry ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'execution_telemetry' AND policyname = 'Allow all access to execution_telemetry'
    ) THEN
        CREATE POLICY "Allow all access to execution_telemetry" ON public.execution_telemetry FOR ALL USING (true) WITH CHECK (true);
    END IF;
END
$$;

ALTER TABLE public.meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.speakers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transcript_segments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.action_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.decisions ENABLE ROW LEVEL SECURITY;

-- Allow public read/insert for anonymous/authenticated API keys (configurable for prod)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'meetings' AND policyname = 'Allow all access to meetings'
    ) THEN
        CREATE POLICY "Allow all access to meetings" ON public.meetings FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'speakers' AND policyname = 'Allow all access to speakers'
    ) THEN
        CREATE POLICY "Allow all access to speakers" ON public.speakers FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'transcript_segments' AND policyname = 'Allow all access to transcript_segments'
    ) THEN
        CREATE POLICY "Allow all access to transcript_segments" ON public.transcript_segments FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'action_items' AND policyname = 'Allow all access to action_items'
    ) THEN
        CREATE POLICY "Allow all access to action_items" ON public.action_items FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'decisions' AND policyname = 'Allow all access to decisions'
    ) THEN
        CREATE POLICY "Allow all access to decisions" ON public.decisions FOR ALL USING (true) WITH CHECK (true);
    END IF;
END
$$;
