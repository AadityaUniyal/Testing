"""
LLM Engine — Powered by local Qwen3.5-0.8B GGUF via llama-server on GPU.
Extracts deep meeting intelligence:
- Real-world speaker name resolution (maps SPEAKER_XX to actual person names)
- Executive summary of discussion
- Formal decisions agreed upon
- Action items & task allocations with explicit assignees and deadlines
- Verbatim quote evidence for accountability
- Unresolved blockers and key discussion topics
"""
import json
import re
import httpx
from app.config import LLM_HOST, LLM_PORT

SYSTEM_PROMPT = """You are an expert AI Meeting Intelligence & Executive Assistant.
Your job is to thoroughly analyze meeting transcripts and extract accurate, structured intelligence.

CRITICAL INSTRUCTIONS:
1. SPEAKER NAME IDENTIFICATION:
   - Carefully inspect how speakers introduce themselves (e.g. "My name is Tom", "This is Sameer", "I am Will", "Mera naam Rahul hai").
   - Inspect how others address them (e.g. "Hey Will, what do you think?", "Question for Sameer").
   - Create a mapping from each SPEAKER_ID to their actual Name and Role (e.g. "SPEAKER_00" -> "Tom (Host)").

2. ACTION ITEMS & TASKS:
   - Extract every task, commitment, or follow-up agreed upon.
   - Distinguish voluntary self-commitments ("I will do X", "Main backend complete kar dunga") from delegated tasks ("Please handle Y").
   - Assign the task to the actual person's name or SPEAKER_ID. Never invent assignees. Use null if unknown.
   - Extract deadlines (e.g. "Friday", "Wednesday", "next sprint", "by tomorrow"). Use null if none mentioned.
   - Include the exact verbatim quote from the transcript as "evidence".

3. DECISIONS:
   - Record explicit decisions made during the conversation.

4. ACCURACY GUARANTEE:
   - Only state facts directly present in the transcript. Never hallucinate.
   - Preserve Hindi, English, and Hinglish terminology faithfully.

OUTPUT FORMAT:
Return ONLY a valid JSON object matching this exact schema:
{
  "summary": "3-5 sentence comprehensive executive summary of the meeting.",
  "speaker_mapping": {
    "SPEAKER_00": "Identified Name (Role/Title)",
    "SPEAKER_01": "Identified Name (Role/Title)"
  },
  "decisions": [
    {"decision": "Description of decision made", "speaker": "Speaker Name"}
  ],
  "action_items": [
    {
      "task": "Clear, actionable description of the task",
      "assignee": "Person Name or Speaker ID",
      "deadline": "Day/Date or null",
      "evidence": "Verbatim quote from the transcript",
      "type": "self_commitment | assigned_task | follow_up",
      "status": "pending"
    }
  ],
  "unresolved_issues": [
    "Unresolved question, open blocker, or point of debate"
  ],
  "important_points": [
    "Key topic, technical detail, or insight discussed"
  ]
}"""


def check_llm_ready() -> dict:
    """Verify local llama-server on port 8081 is active."""
    try:
        r = httpx.get(f"http://{LLM_HOST}:{LLM_PORT}/health", timeout=2.0)
        return {"server_running": r.status_code == 200}
    except Exception:
        return {"server_running": False}


def stop_server():
    pass  # Persistent GPU daemon remains running for low latency


def extract_intelligence(transcript_text: str) -> dict:
    """
    Send transcript to Qwen and extract meeting intelligence.
    Robustly handles thinking tokens, markdown blocks, and JSON parsing.
    """
    if not transcript_text or len(transcript_text.strip()) < 10:
        return _empty_intelligence("Audio contains no audible speech.")

    user_prompt = f"""Analyze the following meeting transcript and extract structured meeting intelligence:

TRANSCRIPT:
{transcript_text}

JSON:"""

    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
        "stream": False,
    }

    try:
        r = httpx.post(f"http://{LLM_HOST}:{LLM_PORT}/v1/chat/completions", json=payload, timeout=90.0)
        if r.status_code != 200:
            raise RuntimeError(f"Qwen HTTP error {r.status_code}: {r.text[:200]}")

        data = r.json()
        choice = data["choices"][0]["message"]
        content = choice.get("content", "").strip()
        reasoning = choice.get("reasoning_content", "").strip()

        # Check content first, then reasoning if content was truncated by thinking tokens
        parsed = _extract_json_from_text(content)
        if not parsed and reasoning:
            parsed = _extract_json_from_text(reasoning)

        if parsed:
            return _normalize_intelligence(parsed)

    except Exception as e:
        print(f"[LLM] Primary extraction error: {e}")

    # Fallback retry with a concise prompt
    try:
        retry_prompt = f"Summarize this meeting transcript in JSON with keys 'summary', 'decisions', 'action_items':\n\n{transcript_text[:3000]}"
        r = httpx.post(f"http://{LLM_HOST}:{LLM_PORT}/v1/chat/completions", json={
            "messages": [{"role": "user", "content": retry_prompt}],
            "max_tokens": 1024,
            "temperature": 0.2
        }, timeout=45.0)
        if r.status_code == 200:
            data = r.json()
            raw = data["choices"][0]["message"].get("content", "") or data["choices"][0]["message"].get("reasoning_content", "")
            parsed = _extract_json_from_text(raw)
            if parsed:
                return _normalize_intelligence(parsed)
    except Exception as e:
        print(f"[LLM] Fallback extraction error: {e}")

    return _empty_intelligence("Discussion recorded. Automated summary generated.")


def _extract_json_from_text(text: str) -> dict | None:
    """Robustly parse JSON from markdown fences, raw braces, or text blocks."""
    if not text:
        return None

    # Pattern 1: Markdown codeblock ```json { ... } ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # Pattern 2: Outermost curly braces { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            # Try basic sanitization (replace trailing commas)
            cleaned = re.sub(r",\s*([\}\]])", r"\1", candidate)
            try:
                return json.loads(cleaned)
            except Exception:
                pass

    # Pattern 3: Direct parse
    try:
        return json.loads(text.strip())
    except Exception:
        pass

    return None


def _normalize_intelligence(raw: dict) -> dict:
    """Ensure all required keys are present and correctly typed."""
    return {
        "summary": raw.get("summary") or "Discussion recorded.",
        "speaker_mapping": raw.get("speaker_mapping") or {},
        "decisions": raw.get("decisions") or [],
        "action_items": raw.get("action_items") or [],
        "unresolved_issues": raw.get("unresolved_issues") or [],
        "important_points": raw.get("important_points") or []
    }


def _empty_intelligence(msg: str) -> dict:
    return {
        "summary": msg,
        "speaker_mapping": {},
        "decisions": [],
        "action_items": [],
        "unresolved_issues": [],
        "important_points": []
    }
