// Meeting Intelligence — Live Streaming & Offline Processing

const API = '';
let activeTab = 'live';

// Live Meeting State
let liveWs = null;
let audioContext = null;
let mediaStream = null;
let scriptProcessor = null;
let liveMeetingId = null;
let timerInterval = null;
let timerSeconds = 0;
let isLiveActive = false;

// Visualizer
let analyser = null;
let visualizerAnimId = null;

// Tab Switching
function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`tab-${tab}-btn`).classList.add('active');

    if (tab === 'live') {
        document.getElementById('live-section').classList.remove('hidden');
        document.getElementById('upload-section').classList.add('hidden');
    } else {
        document.getElementById('live-section').classList.add('hidden');
        document.getElementById('upload-section').classList.remove('hidden');
    }
}

// ── 1. LIVE STREAMING MICROPHONE ENGINE ─────────────────────────

async function startLiveMeeting() {
    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                sampleRate: 16000,
                echoCancellation: true,
                noiseSuppression: true
            }
        });
    } catch (err) {
        alert("Microphone access denied or not available: " + err.message);
        return;
    }

    liveMeetingId = `live_${Date.now()}`;
    const wsUrl = `ws://${location.host}/ws/live-meeting/${liveMeetingId}`;
    liveWs = new WebSocket(wsUrl);
    liveWs.binaryType = "arraybuffer";

    liveWs.onopen = () => {
        console.log("[Live] WebSocket connected!");
        initAudioPipeline();
        isLiveActive = true;

        // UI Changes
        document.getElementById('start-live-btn').classList.add('hidden');
        document.getElementById('stop-live-btn').classList.remove('hidden');
        document.getElementById('live-timer').classList.remove('hidden');
        document.getElementById('live-grid').classList.remove('hidden');
        document.getElementById('results-section').classList.add('hidden');

        // Start Timer
        timerSeconds = 0;
        updateTimerDisplay();
        timerInterval = setInterval(() => {
            timerSeconds++;
            updateTimerDisplay();
        }, 1000);
    };

    liveWs.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "live_transcript") {
            appendLiveTranscript(msg);
        } else if (msg.type === "live_task") {
            appendLiveTask(msg.item);
        } else if (msg.type === "meeting_completed") {
            console.log("[Live] Final report received:", msg.data);
            cleanupAudio();
            renderResults(msg.data);
            document.getElementById('results-section').classList.remove('hidden');
            loadHistory();
        }
    };

    liveWs.onerror = (e) => console.error("[Live] WebSocket error:", e);
    liveWs.onclose = () => {
        console.log("[Live] Session closed");
        cleanupAudio();
    };
}

function initAudioPipeline() {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(mediaStream);

    // Setup visualizer
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 64;
    source.connect(analyser);
    drawVisualizer();

    // 4096 samples at 16kHz ≈ 250ms chunks
    scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);
    source.connect(scriptProcessor);
    scriptProcessor.connect(audioContext.destination);

    let pcmBuffer = [];
    const BUFFER_LIMIT = 16000 * 2.5; // Send audio every ~2.5 seconds

    scriptProcessor.onaudioprocess = (e) => {
        if (!isLiveActive || !liveWs || liveWs.readyState !== WebSocket.OPEN) return;

        const inputData = e.inputBuffer.getChannelData(0);
        // Convert Float32 to 16-bit PCM
        const pcm16 = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
            let s = Math.max(-1, Math.min(1, inputData[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        pcmBuffer.push(pcm16);

        let totalLength = pcmBuffer.reduce((acc, curr) => acc + curr.length, 0);
        if (totalLength >= BUFFER_LIMIT) {
            // Concatenate buffer and send to backend
            const merged = new Int16Array(totalLength);
            let offset = 0;
            for (let chunk of pcmBuffer) {
                merged.set(chunk, offset);
                offset += chunk.length;
            }
            liveWs.send(merged.buffer);
            pcmBuffer = [];
        }
    };
}

function stopLiveMeeting() {
    if (!isLiveActive || !liveWs) return;
    isLiveActive = false;

    document.getElementById('stop-live-btn').disabled = true;
    document.getElementById('stop-live-btn').textContent = "⏳ Generating AI Intelligence...";

    // Send stop signal to server
    liveWs.send(JSON.stringify({ action: "STOP_MEETING" }));
}

function cleanupAudio() {
    if (timerInterval) clearInterval(timerInterval);
    if (mediaStream) mediaStream.getTracks().forEach(t => t.stop());
    if (scriptProcessor) scriptProcessor.disconnect();
    if (audioContext) audioContext.close();
    if (visualizerAnimId) cancelAnimationFrame(visualizerAnimId);

    document.getElementById('start-live-btn').classList.remove('hidden');
    document.getElementById('stop-live-btn').classList.add('hidden');
    document.getElementById('stop-live-btn').disabled = false;
    document.getElementById('stop-live-btn').textContent = "⏹️ End Meeting & Generate Report";
    document.getElementById('live-timer').classList.add('hidden');
}

function updateTimerDisplay() {
    const mins = Math.floor(timerSeconds / 60);
    const secs = timerSeconds % 60;
    document.getElementById('timer-display').textContent = `${pad(mins)}:${pad(secs)}`;
}

function drawVisualizer() {
    const canvas = document.getElementById('audio-visualizer');
    const ctx = canvas.getContext('2d');
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function render() {
        visualizerAnimId = requestAnimationFrame(render);
        analyser.getByteFrequencyData(dataArray);

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const barWidth = (canvas.width / bufferLength) * 2;
        let x = 0;

        for (let i = 0; i < bufferLength; i++) {
            const barHeight = (dataArray[i] / 255) * canvas.height * 0.9;
            ctx.fillStyle = `rgba(79, 140, 255, ${0.3 + (dataArray[i] / 255) * 0.7})`;
            ctx.fillRect(x, canvas.height - barHeight, barWidth - 1, barHeight);
            x += barWidth;
        }
    }
    render();
}

function appendLiveTranscript(msg) {
    const feed = document.getElementById('live-transcript-feed');
    const empty = feed.querySelector('.empty-state');
    if (empty) empty.remove();

    const bubble = document.createElement('div');
    bubble.className = 'live-bubble';
    bubble.innerHTML = `
        <div class="live-bubble-header">
            <span class="live-bubble-speaker speaker-${msg.speaker}">${msg.speaker}</span>
            <span class="live-bubble-time">${msg.start.toFixed(1)}s - ${msg.end.toFixed(1)}s</span>
        </div>
        <div class="live-bubble-text">${msg.text}</div>
    `;
    feed.appendChild(bubble);
    feed.scrollTop = feed.scrollHeight;
}

function appendLiveTask(item) {
    const feed = document.getElementById('live-tasks-feed');
    const empty = feed.querySelector('.empty-state');
    if (empty) empty.remove();

    const card = document.createElement('div');
    card.className = 'live-task-badge';
    card.innerHTML = `
        <div class="live-task-title">⚡ ${item.task}</div>
        <div class="live-task-meta">
            👤 Assignee: <strong>${item.assignee || 'Unknown'}</strong> · 📅 Deadline: <strong>${item.deadline || 'Pending'}</strong>
        </div>
    `;
    feed.appendChild(card);
    feed.scrollTop = feed.scrollHeight;
}


// ── 2. FILE UPLOAD & BATCH PROCESSING ───────────────────────────

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileInfo = document.getElementById('file-info');
const fileName = document.getElementById('file-name');
const fileSize = document.getElementById('file-size');
const processBtn = document.getElementById('process-btn');
let selectedFile = null;

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files.length) handleFile(fileInput.files[0]); });

function handleFile(file) {
    selectedFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = (file.size / (1024 * 1024)).toFixed(1) + ' MB';
    fileInfo.classList.remove('hidden');
    processBtn.disabled = false;
}

processBtn.addEventListener('click', async () => {
    if (!selectedFile) return;
    processBtn.disabled = true;
    processBtn.textContent = '⏳ Uploading...';

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
        const uploadRes = await fetch(`${API}/api/upload`, { method: 'POST', body: formData });
        const uploadData = await uploadRes.json();
        const meetingId = uploadData.meeting_id;

        document.getElementById('upload-section').classList.add('hidden');
        document.getElementById('progress-section').classList.remove('hidden');
        document.getElementById('results-section').classList.add('hidden');

        // Connect status WebSocket
        const ws = new WebSocket(`ws://${location.host}/ws/${meetingId}`);
        ws.onmessage = (event) => {
            const status = JSON.parse(event.data);
            updateStage(status);
            if (status.stage === 'complete') {
                setTimeout(async () => {
                    const res = await fetch(`${API}/api/meetings/${meetingId}`);
                    const data = await res.json();
                    document.getElementById('progress-section').classList.add('hidden');
                    renderResults(data);
                    document.getElementById('results-section').classList.remove('hidden');
                    loadHistory();
                }, 500);
            }
        };

        const minSpk = document.getElementById('min-speakers').value;
        const maxSpk = document.getElementById('max-speakers').value;
        await fetch(`${API}/api/process/${meetingId}?min_speakers=${minSpk}&max_speakers=${maxSpk}`, { method: 'POST' });

    } catch (err) {
        alert("Upload error: " + err.message);
        processBtn.disabled = false;
        processBtn.textContent = '🚀 Process File';
    }
});

function updateStage(status) {
    const stageEl = document.getElementById(`stage-${status.stage}`);
    if (!stageEl) return;

    const stages = ['preprocess', 'transcription', 'diarization', 'alignment', 'intelligence', 'saving'];
    const idx = stages.indexOf(status.stage);
    for (let i = 0; i < idx; i++) {
        const prev = document.getElementById(`stage-${stages[i]}`);
        if (prev) {
            prev.classList.add('done');
            prev.querySelector('.stage-fill').style.width = '100%';
        }
    }

    stageEl.classList.add('active');
    stageEl.querySelector('.stage-status').textContent = status.message;
    stageEl.querySelector('.stage-fill').style.width = (status.progress * 100) + '%';

    if (status.progress >= 1.0) {
        stageEl.classList.remove('active');
        stageEl.classList.add('done');
    }
}


// ── 3. RENDER MEETING REPORT ────────────────────────────────────

function renderResults(data) {
    document.getElementById('result-summary').textContent = data.summary || 'Summary unavailable.';

    // Speakers
    const spkEl = document.getElementById('result-speakers');
    spkEl.innerHTML = '';
    (data.speakers || []).forEach((s, idx) => {
        const tag = document.createElement('span');
        tag.className = `speaker-tag speaker-tag-${idx % 5}`;
        tag.textContent = s;
        spkEl.appendChild(tag);
    });

    // Action Items
    const actEl = document.getElementById('result-actions');
    actEl.innerHTML = '';
    const items = data.action_items || [];
    if (!items.length) {
        actEl.innerHTML = '<p class="small">No explicit action items detected.</p>';
    } else {
        items.forEach(a => {
            const card = document.createElement('div');
            card.className = 'action-item';
            card.innerHTML = `
                <div class="task">${a.task}</div>
                <div class="meta">
                    👤 <strong>${a.assignee || 'Unassigned'}</strong> · 📅 Deadline: <strong>${a.deadline || 'None'}</strong>
                </div>
                ${a.evidence ? `<div class="evidence">"${a.evidence}"</div>` : ''}
            `;
            actEl.appendChild(card);
        });
    }

    // Decisions
    const decEl = document.getElementById('result-decisions');
    decEl.innerHTML = '';
    const decisions = data.decisions || [];
    if (!decisions.length) {
        decEl.innerHTML = '<p class="small">No formal decisions recorded.</p>';
    } else {
        decisions.forEach(d => {
            const card = document.createElement('div');
            card.className = 'decision-item';
            card.textContent = `${d.speaker_id ? d.speaker_id + ': ' : ''}${d.decision}`;
            decEl.appendChild(card);
        });
    }

    // Unresolved
    const unrEl = document.getElementById('result-unresolved');
    unrEl.innerHTML = '';
    (data.unresolved || data.unresolved_issues || []).forEach(u => {
        const li = document.createElement('li');
        li.textContent = u;
        unrEl.appendChild(li);
    });

    // Important
    const impEl = document.getElementById('result-important');
    impEl.innerHTML = '';
    (data.important || data.important_points || []).forEach(p => {
        const li = document.createElement('li');
        li.textContent = p;
        impEl.appendChild(li);
    });

    // Transcript
    const trEl = document.getElementById('result-transcript');
    trEl.innerHTML = '';
    (data.transcript || data.aligned_transcript || []).forEach(seg => {
        const row = document.createElement('div');
        row.className = 'transcript-line';
        const startM = Math.floor(seg.start / 60);
        const startS = Math.floor(seg.start % 60);
        const endM = Math.floor(seg.end / 60);
        const endS = Math.floor(seg.end % 60);
        row.innerHTML = `
            <span class="timestamp">[${pad(startM)}:${pad(startS)} - ${pad(endM)}:${pad(endS)}]</span>
            <strong class="speaker-${seg.speaker_id || seg.speaker}">${seg.speaker_id || seg.speaker}:</strong> ${seg.text}
        `;
        trEl.appendChild(row);
    });
}

function pad(n) { return String(n).padStart(2, '0'); }

function toggleTranscript() {
    document.getElementById('result-transcript').classList.toggle('hidden');
}


// ── 4. HISTORY ──────────────────────────────────────────────────

async function loadHistory() {
    try {
        const res = await fetch(`${API}/api/meetings`);
        const list = await res.json();
        const listEl = document.getElementById('meeting-list');
        listEl.innerHTML = '';

        if (!list.length) {
            listEl.innerHTML = '<p class="small">No meetings saved yet.</p>';
            return;
        }

        list.forEach(m => {
            const div = document.createElement('div');
            div.className = 'meeting-history-item';
            const duration = m.duration_sec ? ` · ${(m.duration_sec / 60).toFixed(1)} min` : '';
            div.innerHTML = `
                <div>
                    <div style="font-weight:700">${m.filename || m.meeting_id}</div>
                    <div class="small">${m.processed_at || ''}${duration}</div>
                </div>
                <span class="badge">${Array.isArray(m.speakers) ? m.speakers.length : 0} Speakers</span>
            `;
            div.onclick = async () => {
                const r = await fetch(`${API}/api/meetings/${m.meeting_id}`);
                const fullData = await r.json();
                renderResults(fullData);
                document.getElementById('results-section').classList.remove('hidden');
                window.scrollTo({ top: document.getElementById('results-section').offsetTop, behavior: 'smooth' });
            };
            listEl.appendChild(div);
        });
    } catch (e) {
        console.error("History fetch error:", e);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadHistory();
});
