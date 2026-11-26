-- Migration: 003 Add Execution Telemetry
-- Documents audio duration, Whisper latency, Diarization latency, LLM latency, realtime factor, speech ratio, and silence percentage.

CREATE TABLE IF NOT EXISTS public.execution_telemetry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id TEXT NOT NULL REFERENCES public.meetings(meeting_id) ON DELETE CASCADE,
    audio_duration_seconds REAL DEFAULT 0,
    whisper_latency_seconds REAL DEFAULT 0,
    diarization_latency_seconds REAL DEFAULT 0,
    llm_latency_seconds REAL DEFAULT 0,
    total_latency_seconds REAL DEFAULT 0,
    realtime_factor REAL DEFAULT 0,
    speech_ratio REAL DEFAULT 0,
    silence_percentage REAL DEFAULT 0,
    word_count INTEGER DEFAULT 0,
    turn_count INTEGER DEFAULT 0,
    speaker_count INTEGER DEFAULT 0,
    task_count INTEGER DEFAULT 0,
    decision_count INTEGER DEFAULT 0,
    device_profile TEXT DEFAULT 'hybrid_edge_ios',
    model_versions JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.meetings ADD COLUMN IF NOT EXISTS telemetry JSONB DEFAULT '{}'::jsonb;

ALTER TABLE public.execution_telemetry ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'execution_telemetry' AND policyname = 'Public read telemetry'
    ) THEN
        CREATE POLICY "Public read telemetry" ON public.execution_telemetry FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'execution_telemetry' AND policyname = 'Public write telemetry'
    ) THEN
        CREATE POLICY "Public write telemetry" ON public.execution_telemetry FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;
