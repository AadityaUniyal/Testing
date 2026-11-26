"""
Model Manager — Automatic Lifecycle & Triggering System.
Ensures that all local models (Whisper, Pyannote, Qwen LLM) auto-activate
on demand without requiring the user to run manual terminal commands.
"""

import os
import shutil
import subprocess
import time
import httpx
import logging
from typing import Optional, Dict, Any

from app import config

logger = logging.getLogger("meeting_intelligence.models")

_llm_process: Optional[subprocess.Popen] = None
_llm_managed_by_us: bool = False

_whisper_process: Optional[subprocess.Popen] = None
_whisper_managed_by_us: bool = False

WHISPER_SERVER_EXE = os.path.join(config.BASE_DIR, "tools", "whisper", "Release", "whisper-server.exe")
WHISPER_HOST = "127.0.0.1"
WHISPER_PORT = 8082


def find_llama_server_binary() -> Optional[str]:
    """Locate the llama-server executable."""
    # 1. System PATH
    found = shutil.which("llama-server")
    if found:
        return found
    
    # 2. Local tools directory
    local_tool = os.path.join(config.BASE_DIR, "tools", "llama", "llama-server.exe")
    if os.path.exists(local_tool):
        return local_tool

    # 3. Known WinGet install path
    winget_base = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Microsoft", "WinGet", "Packages"
    )
    if os.path.exists(winget_base):
        for root, _, files in os.walk(winget_base):
            if "llama-server.exe" in files:
                return os.path.join(root, "llama-server.exe")

    return None


def is_llm_running() -> bool:
    """Check if the Qwen llama-server is healthy and listening on the designated port."""
    try:
        r = httpx.get(f"http://{config.LLM_HOST}:{config.LLM_PORT}/health", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


def is_whisper_server_running() -> bool:
    """Check if the Whisper GPU server is responsive on port 8082."""
    try:
        r = httpx.get(f"http://{WHISPER_HOST}:{WHISPER_PORT}/", timeout=1.5)
        return r.status_code in (200, 404, 405)
    except Exception:
        return False


def ensure_whisper_server(max_wait_sec: float = 8.0) -> bool:
    """
    Ensure the Whisper GPU server is running for real-time live transcription.
    Auto-activates whisper-server.exe on port 8082 with CUDA and Flash Attention.
    """
    global _whisper_process, _whisper_managed_by_us

    if is_whisper_server_running():
        return True

    if not os.path.exists(WHISPER_SERVER_EXE):
        logger.warning(f"whisper-server.exe not found at: {WHISPER_SERVER_EXE}")
        return False

    if not os.path.exists(config.WHISPER_MODEL):
        logger.warning(f"Whisper model not found at: {config.WHISPER_MODEL}")
        return False

    cmd = [
        WHISPER_SERVER_EXE,
        "--host", WHISPER_HOST,
        "--port", str(WHISPER_PORT),
        "-m", config.WHISPER_MODEL,
        "-fa",
        "-l", "auto"
    ]

    logger.info(f"Auto-activating Whisper GPU server on port {WHISPER_PORT}...")
    print(f"[ModelManager] Auto-activating Whisper GPU server on port {WHISPER_PORT}...")

    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)

        _whisper_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
        _whisper_managed_by_us = True

        start_time = time.time()
        while time.time() - start_time < max_wait_sec:
            if is_whisper_server_running():
                print(f"[ModelManager] Whisper GPU server activated in {time.time() - start_time:.1f}s.")
                return True
            time.sleep(0.4)

        return is_whisper_server_running()
    except Exception as e:
        logger.error(f"Failed to auto-spawn whisper-server: {e}")
        return False


def stop_whisper_server():
    """Stop the Whisper server if managed by us."""
    global _whisper_process, _whisper_managed_by_us
    if _whisper_managed_by_us and _whisper_process is not None:
        try:
            print("[ModelManager] Shutting down managed Whisper server...")
            _whisper_process.terminate()
            _whisper_process.wait(timeout=3.0)
        except Exception:
            try:
                _whisper_process.kill()
            except Exception:
                pass
        finally:
            _whisper_process = None
            _whisper_managed_by_us = False


def ensure_llm_server(max_wait_sec: float = 12.0) -> bool:
    """
    Ensure the Qwen LLM server is running.
    If not running, auto-spawns it in the background with GPU offload (-ngl 99).
    """
    global _llm_process, _llm_managed_by_us

    if is_llm_running():
        return True

    exe_path = find_llama_server_binary()
    if not exe_path:
        logger.error("llama-server binary not found on the system.")
        return False

    if not os.path.exists(config.QWEN_MODEL):
        logger.error(f"Qwen model file not found at: {config.QWEN_MODEL}")
        return False

    cmd = [
        exe_path,
        "-m", config.QWEN_MODEL,
        "--host", config.LLM_HOST,
        "--port", str(config.LLM_PORT),
        "-c", "4096",
        "-ngl", "99",
        "--no-warmup"
    ]

    logger.info(f"Auto-activating Qwen LLM server: {' '.join(cmd)}")
    print(f"[ModelManager] Auto-activating Qwen LLM server on port {config.LLM_PORT}...")

    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)

        _llm_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
        _llm_managed_by_us = True

        start_time = time.time()
        while time.time() - start_time < max_wait_sec:
            if is_llm_running():
                print(f"[ModelManager] Qwen LLM server activated in {time.time() - start_time:.1f}s.")
                return True
            time.sleep(0.5)

        logger.warning(f"Qwen server process launched (PID {_llm_process.pid}) but did not respond to /health in {max_wait_sec}s.")
        return is_llm_running()

    except Exception as e:
        logger.error(f"Failed to auto-spawn llama-server: {e}")
        return False


def stop_llm_server():
    """Stop the LLM server if it was started by this process."""
    global _llm_process, _llm_managed_by_us
    if _llm_managed_by_us and _llm_process is not None:
        try:
            print("[ModelManager] Shutting down managed Qwen LLM server...")
            _llm_process.terminate()
            _llm_process.wait(timeout=3.0)
        except Exception:
            try:
                _llm_process.kill()
            except Exception:
                pass
        finally:
            _llm_process = None
            _llm_managed_by_us = False


def stop_all_models():
    """Stop all background managed model processes."""
    stop_llm_server()
    stop_whisper_server()


def trigger_all_models() -> Dict[str, Any]:
    """
    On-demand trigger for all models (called when user clicks Record or Import Audio).
    Ensures:
      - Whisper model & CLI are verified
      - Whisper GPU streaming server is active on port 8082
      - Pyannote weights are checked
      - Qwen LLM server is active and warm on port 8081
    """
    from app import whisper_engine, diarization_engine

    llm_ok = ensure_llm_server(max_wait_sec=8.0)
    whisper_srv_ok = ensure_whisper_server(max_wait_sec=8.0)
    whisper_status = whisper_engine.check_whisper_ready()
    diarize_status = diarization_engine.check_diarization_ready()

    return {
        "status": "ready" if (llm_ok and whisper_status.get("model_exists")) else "degraded",
        "llm": {"server_running": is_llm_running()},
        "whisper_streaming_server": {"running": is_whisper_server_running()},
        "whisper": whisper_status,
        "diarization": diarize_status,
        "auto_activated": True
    }
