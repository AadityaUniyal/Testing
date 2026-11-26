"""
LLM Engine — runs Qwen3.5-0.8B (GGUF) via llama-server for:
  1. Executive Minutes & Key Topics
  2. Dynamic Speaker Identification (mapping SPEAKER_XX -> Real Name based on spoken cues)
  3. ActionFlow Task Allocation (assignee, task, deadline, transcript evidence, status)
  4. Key Decisions & Consensus (status, decided_by, evidence)

Optimized with instant-completion prompts that eliminate reasoning loops for 1-2s response times.
"""

import json
import re
import httpx
from app.config import LLM_HOST, LLM_PORT
from app.models import ActionItem, Decision


def check_llm_ready() -> dict:
    try:
        r = httpx.get(f"http://{LLM_HOST}:{LLM_PORT}/health", timeout=3.0)
        return {"server_running": r.status_code == 200}
    except Exception:
        return {"server_running": False}


def _extract_json_from_text(text: str) -> dict:
    if not text:
        return {}

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # Markdown fence matching
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # Curly bracket matching
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            # Fix trailing commas
            cleaned = re.sub(r",\s*([\}\]])", r"\1", candidate)
            try:
                return json.loads(cleaned)
            except Exception:
                pass

    return {}


def _normalize_intelligence(raw: dict) -> dict:
    summary = raw.get("summary") or raw.get("executive_summary") or raw.get("topic", "")
    if isinstance(summary, list):
        summary = " ".join(summary)
    elif not isinstance(summary, str):
        summary = str(summary)

    # Key topics
    key_topics = raw.get("key_topics") or raw.get("important_points") or []
    if isinstance(key_topics, str):
        key_topics = [t.strip() for t in key_topics.split(",") if t.strip()]
    if not key_topics and raw.get("topic"):
        key_topics = [str(raw.get("topic"))]

    # Normalize speaker mapping
    speaker_mapping = {}
    raw_spk = raw.get("speaker_mapping") or raw.get("speakers") or {}
    if isinstance(raw_spk, dict):
        for k, v in raw_spk.items():
            k_clean = k.upper().replace(" ", "_")
            if not k_clean.startswith("SPEAKER_"):
                nums = re.findall(r"\d+", k)
                if nums:
                    k_clean = f"SPEAKER_{int(nums[0]):02d}"
            speaker_mapping[k_clean] = str(v).strip()
    elif isinstance(raw_spk, list):
        for item in raw_spk:
            if isinstance(item, dict):
                spk = item.get("speaker_id") or item.get("id") or item.get("speaker")
                name = item.get("name") or item.get("display_name")
                if spk and name:
                    speaker_mapping[str(spk).upper()] = str(name).strip()

    # Normalize ActionFlow items
    action_items = []
    for item in raw.get("action_items", []):
        if isinstance(item, dict):
            task = item.get("task") or item.get("action") or item.get("description", "")
            if task:
                assignee = item.get("assignee") or item.get("owner") or "Unassigned"
                assignee_upper = str(assignee).upper()
                if assignee_upper in speaker_mapping:
                    assignee = speaker_mapping[assignee_upper]
                action_items.append({
                    "task": str(task).strip(),
                    "assignee": str(assignee).strip(),
                    "deadline": str(item.get("deadline") or "Not specified").strip(),
                    "evidence": item.get("evidence"),
                    "status": str(item.get("status") or "open").lower()
                })
        elif isinstance(item, str) and len(item.strip()) > 3:
            action_items.append({
                "task": item.strip(),
                "assignee": "Unassigned",
                "deadline": "Not specified",
                "evidence": None,
                "status": "open"
            })

    # Normalize Decisions
    decisions = []
    for d in raw.get("decisions", []):
        if isinstance(d, dict):
            dec_text = d.get("decision") or d.get("text") or ""
            if dec_text:
                speaker_val = d.get("speaker") or d.get("speaker_id") or d.get("decided_by")
                if speaker_val and str(speaker_val).upper() in speaker_mapping:
                    speaker_val = speaker_mapping[str(speaker_val).upper()]
                decisions.append({
                    "decision": str(dec_text).strip(),
                    "status": str(d.get("status") or "RESOLVED").upper(),
                    "decided_by": str(speaker_val).strip() if speaker_val else None,
                    "evidence": d.get("evidence")
                })
        elif isinstance(d, str) and len(d.strip()) > 3:
            decisions.append({
                "decision": d.strip(),
                "status": "RESOLVED",
                "decided_by": None,
                "evidence": None
            })

    return {
        "summary": summary.strip() or "Meeting concluded.",
        "speaker_mapping": speaker_mapping,
        "key_topics": key_topics,
        "decisions": decisions,
        "action_items": action_items,
        "unresolved_issues": raw.get("unresolved_issues", []),
        "important_points": raw.get("important_points", []),
    }


def extract_intelligence(transcript_text: str) -> dict:
    """
    Send transcript to Qwen and extract structured meeting minutes, speaker mapping,
    decisions, and action allocations.
    Uses completion endpoint with anti-loop prompt prefix for sub-2s responses.
    """
    if not transcript_text or len(transcript_text.strip()) < 10:
        return {
            "summary": "Audio contains no audible speech.",
            "speaker_mapping": {},
            "key_topics": [],
            "decisions": [],
            "action_items": [],
            "unresolved_issues": [],
            "important_points": [],
        }

    prompt = f"""<|im_start|>system
You are Manent, an expert executive meeting intelligence system.
Analyze the transcript dialogue chronologically to identify speaker names, executive summary, final decisions, and action items.

CHRONOLOGICAL DECISION & TASK OVERRIDE RULES:
1. People often change their minds, cancel plans, or revise decisions later in a conversation.
2. Read the entire dialogue from start to finish. If an earlier proposal, commitment, or decision was revised, rejected, modified, or superseded later in the meeting, you MUST ONLY record the FINAL AGREED DECISION and the FINAL AGREED TASK/DEADLINE.
3. If an initial decision was explicitly revoked or reversed (e.g., "Actually, scratch that, let's not use X, we are going with Y"), record Y as the RESOLVED decision, NOT the cancelled one.
4. Ensure the summary and ActionFlow always reflect the ultimate authoritative truth of the meeting, not intermediate discarded brainstorming.
Respond ONLY with valid JSON.
<|im_end|>
<|im_start|>user
TRANSCRIPT:
{transcript_text[:6800]}

Extract in JSON matching this schema:
{{
  "speaker_mapping": {{"SPEAKER_00": "Name", "SPEAKER_01": "Name"}},
  "topic": "Main meeting topic",
  "summary": "Executive summary reflecting final consensus and resolved outcomes",
  "key_topics": ["Topic 1", "Topic 2"],
  "decisions": [{{"decision": "Final consensus point reached (reflecting any late overrides)", "status": "RESOLVED", "decided_by": "Name"}}],
  "action_items": [{{"task": "Final assigned task description", "assignee": "Name", "deadline": "Final agreed deadline", "evidence": "Final quote"}}]
}}
<|im_end|>
<|im_start|>assistant
<think>
Done thinking.
</think>
```json
{{
  "speaker_mapping": {{
"""

    try:
        r = httpx.post(f"http://{LLM_HOST}:{LLM_PORT}/completion", json={
            "prompt": prompt,
            "n_predict": 1200,
            "temperature": 0.1,
            "stop": ["<|im_end|>", "\n```"]
        }, timeout=30.0)

        if r.status_code == 200:
            content = r.json().get("content", "")
            full_json_str = '{\n  "speaker_mapping": {\n' + content.strip().rstrip("`")
            if not full_json_str.endswith("}"):
                full_json_str += "\n}"
            parsed = _extract_json_from_text(full_json_str)
            if parsed and (parsed.get("summary") or parsed.get("speaker_mapping") or parsed.get("executive_summary") or parsed.get("action_items")):
                return _normalize_intelligence(parsed)

    except Exception as e:
        print(f"[LLM] Fast completion notice: {e}")

    # Fallback to chat completions
    try:
        fallback_prompt = f"""Analyze transcript and output JSON with keys: speaker_mapping, summary, key_topics, decisions, action_items.\n\n{transcript_text[:4000]}"""
        r = httpx.post(f"http://{LLM_HOST}:{LLM_PORT}/v1/chat/completions", json={
            "messages": [
                {"role": "system", "content": "You are a meeting analyst. Respond ONLY with raw valid JSON."},
                {"role": "user", "content": fallback_prompt}
            ],
            "max_tokens": 1500,
            "temperature": 0.1
        }, timeout=40.0)
        if r.status_code == 200:
            data = r.json()
            raw = data["choices"][0]["message"].get("content", "") or data["choices"][0]["message"].get("reasoning_content", "")
            parsed = _extract_json_from_text(raw)
            if parsed:
                return _normalize_intelligence(parsed)
    except Exception as e:
        print(f"[LLM] Chat fallback notice: {e}")

    return {
        "summary": "Meeting discussion transcribed successfully.",
        "speaker_mapping": {},
        "key_topics": [],
        "decisions": [],
        "action_items": [],
        "unresolved_issues": [],
        "important_points": [],
    }
