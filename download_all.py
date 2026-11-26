import os
import sys
import zipfile
import urllib.request
import json
import subprocess
from huggingface_hub import snapshot_download

BASE_DIR = r"E:\TESTING"
os.chdir(BASE_DIR)

print("=== 1. DOWNLOADING PYANNOTE COMMUNITY-1 ===")
pyannote_target = os.path.join(BASE_DIR, "models", "pyannote", "community-1")
try:
    path = snapshot_download(
        repo_id="pyannote/speaker-diarization-community-1",
        local_dir=pyannote_target
    )
    print(f"Pyannote Community-1 downloaded successfully to: {path}")
except Exception as e:
    print(f"Pyannote download error: {e}")

print("\n=== 2. DOWNLOADING WHISPER.CPP FOR WINDOWS ===")
tools_whisper = os.path.join(BASE_DIR, "tools", "whisper")
os.makedirs(tools_whisper, exist_ok=True)
whisper_cli = os.path.join(tools_whisper, "whisper-cli.exe")

if not os.path.exists(whisper_cli):
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            assets = data.get("assets", [])
            
            # Find prebuilt windows zip (prefer cublas / cuda or x64)
            chosen_url = None
            zip_name = None
            for asset in assets:
                name = asset.get("name", "").lower()
                if "bin-x64" in name and name.endswith(".zip"):
                    chosen_url = asset.get("browser_download_url")
                    zip_name = asset.get("name")
                    break
            
            if not chosen_url:
                for asset in assets:
                    name = asset.get("name", "").lower()
                    if "win" in name and name.endswith(".zip"):
                        chosen_url = asset.get("browser_download_url")
                        zip_name = asset.get("name")
                        break

            if chosen_url:
                print(f"Downloading whisper.cpp asset: {zip_name} from {chosen_url}")
                zip_path = os.path.join(tools_whisper, zip_name)
                urllib.request.urlretrieve(chosen_url, zip_path)
                print(f"Extracting {zip_path}...")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(tools_whisper)
                print("whisper.cpp extracted successfully!")
            else:
                print("Could not find matching windows release asset automatically.")
    except Exception as e:
        print(f"Error downloading whisper.cpp: {e}")
else:
    print(f"whisper-cli.exe already exists at: {whisper_cli}")

print("\n=== 3. VERIFYING ALL 3 MODELS AND TOOLS ===")
for title, p in [
    ("Whisper Large-v3 Turbo Model", os.path.join(BASE_DIR, "models", "whisper", "ggml-large-v3-turbo.bin")),
    ("Qwen3.5-0.8B Q4_K_M GGUF Model", os.path.join(BASE_DIR, "models", "qwen", "qwen3.5-0.8b-Q4_K_M.gguf")),
    ("Pyannote Community-1 Config", os.path.join(pyannote_target, "config.yaml")),
    ("llama-server.exe", r"C:\Users\HP\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\llama-server.exe"),
    ("whisper-cli.exe", os.path.join(tools_whisper, "whisper-cli.exe")),
]:
    exists = os.path.exists(p)
    size = f"({os.path.getsize(p)/(1024*1024):.1f} MB)" if exists and os.path.isfile(p) else ""
    print(f"[{'OK' if exists else 'MISSING'}] {title}: {p} {size}")
