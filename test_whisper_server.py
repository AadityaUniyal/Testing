import time
import httpx

test_wav = r"E:\TESTING\audio\processed\test_latency.wav"

with open(test_wav, "rb") as f:
    files = {"file": ("test.wav", f, "audio/wav")}
    t0 = time.time()
    try:
        r = httpx.post("http://127.0.0.1:8082/inference", files=files, timeout=10.0)
        elapsed = time.time() - t0
        print(f"Status: {r.status_code}")
        print(f"Whisper inference took: {elapsed * 1000:.1f} ms!")
        print("Response:", r.text[:200])
    except Exception as e:
        print("Error:", e)
