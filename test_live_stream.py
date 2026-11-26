import asyncio
import json
import wave
import websockets

async def test_live():
    uri = "ws://127.0.0.1:8000/ws/live-meeting/live_test_123"
    print(f"Connecting to {uri}...")
    async with websockets.connect(uri) as ws:
        print("Connected!")

        # Read sample wav and send as 2-second PCM chunks
        wav_path = r"E:\TESTING\audio\processed\test_latency.wav"
        with wave.open(wav_path, "rb") as wf:
            frames = wf.readframes(wf.getnframes())

        chunk_size = 16000 * 2 * 2 # 2 seconds of 16kHz 16-bit mono
        for i in range(0, len(frames), chunk_size):
            chunk = frames[i:i+chunk_size]
            print(f"Sending audio chunk {len(chunk)} bytes...")
            await ws.send(chunk)
            await asyncio.sleep(0.5)

        # Send stop meeting
        print("Sending STOP_MEETING command...")
        await ws.send(json.dumps({"action": "STOP_MEETING"}))

        # Wait for response
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                data = json.loads(msg)
                print("Received from server:", data.get("type"))
                if data.get("type") == "meeting_completed":
                    print("Meeting completed successfully!")
                    print("Summary:", data["data"].get("summary"))
                    break
            except asyncio.TimeoutError:
                print("Timeout waiting for response")
                break

if __name__ == "__main__":
    asyncio.run(test_live())
