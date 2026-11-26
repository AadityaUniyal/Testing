/**
 * MANENT — Frontend Web Application
 * Matches Figma Prototype: Tar6q6zhuhMDIOBlSKzkdI (Manent)
 */

let allMeetings = [];
let currentMeeting = null;
let currentStudioTab = "minutes";

// Live Recording State
let mediaStream = null;
let audioContext = null;
let analyser = null;
let liveWs = null;
let isRecording = false;
let recordTimerInterval = null;
let recordSeconds = 0;
let liveMeetingId = null;
let animationFrameId = null;

// Selected File State
let selectedFile = null;

// Speaker color palette
const SPEAKER_COLORS = [
    { text: "#38bdf8", bg: "rgba(56, 189, 248, 0.15)", border: "rgba(56, 189, 248, 0.3)" },
    { text: "#c084fc", bg: "rgba(192, 132, 252, 0.15)", border: "rgba(192, 132, 252, 0.3)" },
    { text: "#f59e0b", bg: "rgba(245, 158, 11, 0.15)", border: "rgba(245, 158, 11, 0.3)" },
    { text: "#34d399", bg: "rgba(52, 211, 153, 0.15)", border: "rgba(52, 211, 153, 0.3)" },
    { text: "#f472b6", bg: "rgba(244, 114, 182, 0.15)", border: "rgba(244, 114, 182, 0.3)" },
];

function getSpeakerColor(index) {
    return SPEAKER_COLORS[index % SPEAKER_COLORS.length];
}

// ── 1. NAVIGATION & INITIALIZATION ────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    initDropZone();
    loadMeetings();
    checkEngineHealth();
});

function navigateTo(viewId) {
    document.querySelectorAll(".nav-seg-btn").forEach(btn => btn.classList.remove("active"));
    const activeBtn = document.getElementById(`seg-${viewId}-btn`);
    if (activeBtn) activeBtn.classList.add("active");

    document.querySelectorAll(".view-pane").forEach(pane => pane.classList.remove("active"));
    const activePane = document.getElementById(`view-${viewId}`);
    if (activePane) activePane.classList.add("active");

    // Proactively warm models when navigating to Record or Import
    if (viewId === "record" || viewId === "import") {
        fetch("/api/trigger-models", { method: "POST" }).catch(() => {});
    }
}

async function checkEngineHealth() {
    try {
        const res = await fetch("/api/health");
        const data = await res.json();
        const dot = document.querySelector(".status-dot");
        const text = document.getElementById("engine-status-text");
        if (data.status === "ok") {
            dot.className = "status-dot online";
            text.textContent = "Whisper Turbo (CUDA) · Pyannote · Qwen (GPU)";
        }
    } catch (e) {
        console.warn("Health check error:", e);
    }
}

async function refreshData() {
    await loadMeetings();
    await checkEngineHealth();
}

// ── 2. MEETINGS DASHBOARD ──────────────────────────────────────

async function loadMeetings() {
    try {
        const res = await fetch("/api/meetings");
        allMeetings = await res.json();
        renderMetrics();
        renderMeetingsGrid(allMeetings);
    } catch (err) {
        console.error("Failed to load meetings:", err);
    }
}

function renderMetrics() {
    const totalMeetings = allMeetings.length;
    let totalActions = 0;
    let totalSeconds = 0;

    allMeetings.forEach(m => {
        totalSeconds += m.duration_sec || 0;
        if (m.action_items && Array.isArray(m.action_items)) {
            totalActions += m.action_items.length;
        }
    });

    document.getElementById("stat-total-meetings").textContent = totalMeetings;
    document.getElementById("stat-open-actions").textContent = totalActions;
    document.getElementById("stat-total-hours").textContent = (totalSeconds / 3600).toFixed(1) + "h";
}

function renderMeetingsGrid(meetings) {
    const container = document.getElementById("meetings-list-container");
    container.innerHTML = "";

    if (!meetings || meetings.length === 0) {
        container.innerHTML = `
            <div class="empty-state-box">
                <div class="empty-icon">🎙️</div>
                <h3>No meetings recorded yet</h3>
                <p>Click "Start In-Person Meeting" or "Import Audio Recording" to generate minutes automatically.</p>
            </div>
        `;
        return;
    }

    meetings.forEach((m, idx) => {
        const card = document.createElement("div");
        card.className = "meeting-item-card";
        card.onclick = () => openMeetingInStudio(m.meeting_id);

        const durMin = (m.duration_sec / 60).toFixed(1);
        const dateStr = m.processed_at ? new Date(m.processed_at).toLocaleDateString("en-US", {
            month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
        }) : "Recent Meeting";

        const speakers = m.speakers || [];
        const actionsCount = (m.action_items || []).length;

        card.innerHTML = `
            <div class="meeting-card-top">
                <span class="meeting-date-badge">${dateStr}</span>
                <span class="meeting-duration-pill">⏱️ ${durMin} min</span>
            </div>
            <div class="meeting-item-title">${m.filename || `Meeting ${m.meeting_id}`}</div>
            <div class="meeting-item-summary">${m.summary || "Discussion recorded. Click to inspect minutes and action items."}</div>
            <div class="meeting-card-footer">
                <div class="speakers-avatar-group">
                    ${speakers.slice(0, 3).map((s, i) => `
                        <span class="spk-avatar-pill">${typeof s === 'string' ? s : s.name || 'Speaker'}</span>
                    `).join('')}
                    ${speakers.length > 3 ? `<span class="spk-avatar-pill">+${speakers.length - 3}</span>` : ''}
                </div>
                ${actionsCount > 0 ? `<span class="meeting-actions-pill">⚡ ${actionsCount} tasks</span>` : ''}
            </div>
        `;
        container.appendChild(card);
    });
}

function filterMeetingsList() {
    const query = document.getElementById("meetings-search-input").value.toLowerCase();
    const filtered = allMeetings.filter(m => {
        const text = `${m.filename} ${m.summary} ${(m.speakers || []).join(' ')}`.toLowerCase();
        return text.includes(query);
    });
    renderMeetingsGrid(filtered);
}

// ── 3. LIVE IN-PERSON MEETING RECORDER ──────────────────────────

async function startLiveMeeting() {
    fetch("/api/trigger-models", { method: "POST" }).catch(() => {});

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
        alert("Microphone permission required for in-person recording: " + err.message);
        return;
    }

    liveMeetingId = `mtg_live_${Date.now()}`;
    const wsUrl = `ws://${location.host}/ws/live-meeting/${liveMeetingId}`;
    liveWs = new WebSocket(wsUrl);
    liveWs.binaryType = "arraybuffer";

    liveWs.onopen = () => {
        console.log("[Live] WebSocket connected!");
        initAudioCapture();
        isRecording = true;

        // UI Updates
        document.getElementById("btn-start-record").classList.add("hidden");
        document.getElementById("btn-stop-record").classList.remove("hidden");
        document.getElementById("btn-cancel-record").classList.remove("hidden");
        document.getElementById("rec-live-badge").classList.remove("hidden");
        document.getElementById("rec-timer-box").classList.remove("hidden");
        document.getElementById("rec-live-split").classList.remove("hidden");
        document.getElementById("rec-idle-prompt").classList.add("hidden");
        document.getElementById("rec-session-title").textContent = "In-Person Discussion in Progress";
        document.getElementById("rec-session-subtitle").textContent = "Capturing multi-speaker conversation, transcribing, and extracting ActionFlow...";

        // Timer
        recordSeconds = 0;
        updateRecordTimer();
        recordTimerInterval = setInterval(() => {
            recordSeconds++;
            updateRecordTimer();
        }, 1000);
    };

    liveWs.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "live_transcript") {
            appendLiveTurn(msg);
        } else if (msg.type === "live_task") {
            appendLiveAction(msg.item);
        } else if (msg.type === "meeting_completed") {
            console.log("[Live] Final minutes received:", msg.data);
            cleanupRecorder();
            openMeetingInStudio(msg.data.meeting_id || liveMeetingId);
            loadMeetings();
        }
    };

    liveWs.onerror = (e) => console.error("[Live] WebSocket error:", e);
    liveWs.onclose = () => {
        console.log("[Live] Session closed.");
        cleanupRecorder();
    };
}

function initAudioCapture() {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(mediaStream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);

    startVisualizer();

    // Stream 16kHz PCM chunks over WebSocket
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    source.connect(processor);
    processor.connect(audioContext.destination);

    processor.onaudioprocess = (e) => {
        if (!isRecording || !liveWs || liveWs.readyState !== WebSocket.OPEN) return;
        const inputData = e.inputBuffer.getChannelData(0);
        // Convert float32 to int16 PCM
        const pcm16 = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
            let s = Math.max(-1, Math.min(1, inputData[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        liveWs.send(pcm16.buffer);
    };
}

function startVisualizer() {
    const canvas = document.getElementById("live-audio-canvas");
    const ctx = canvas.getContext("2d");
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function draw() {
        if (!isRecording) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            return;
        }
        animationFrameId = requestAnimationFrame(draw);
        analyser.getByteFrequencyData(dataArray);

        ctx.fillStyle = "rgba(11, 14, 22, 0.4)";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const barWidth = (canvas.width / bufferLength) * 2.2;
        let x = 0;

        for (let i = 0; i < bufferLength; i++) {
            const barHeight = (dataArray[i] / 255) * canvas.height * 0.85;
            const gradient = ctx.createLinearGradient(0, canvas.height, 0, canvas.height - barHeight);
            gradient.addColorStop(0, "#6366f1");
            gradient.addColorStop(1, "#c084fc");

            ctx.fillStyle = gradient;
            ctx.fillRect(x, canvas.height - barHeight, barWidth - 1, barHeight);
            x += barWidth;
        }
    }
    draw();
}

function updateRecordTimer() {
    const m = Math.floor(recordSeconds / 60);
    const s = recordSeconds % 60;
    document.getElementById("rec-timer-display").textContent = 
        `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function stopLiveMeeting() {
    if (!isRecording || !liveWs) return;
    document.getElementById("rec-session-title").textContent = "Finalizing Minutes & ActionFlow...";
    document.getElementById("rec-session-subtitle").textContent = "Processing full multi-speaker alignment and executive minutes...";
    liveWs.send(JSON.stringify({ action: "finish_meeting" }));
}

function cancelLiveMeeting() {
    if (confirm("Cancel this live meeting recording?")) {
        cleanupRecorder();
        navigateTo("meetings");
    }
}

function cleanupRecorder() {
    isRecording = false;
    clearInterval(recordTimerInterval);
    if (animationFrameId) cancelAnimationFrame(animationFrameId);

    if (mediaStream) {
        mediaStream.getTracks().forEach(t => t.stop());
        mediaStream = null;
    }
    if (audioContext && audioContext.state !== "closed") {
        audioContext.close();
        audioContext = null;
    }

    document.getElementById("btn-start-record").classList.remove("hidden");
    document.getElementById("btn-stop-record").classList.add("hidden");
    document.getElementById("btn-cancel-record").classList.add("hidden");
    document.getElementById("rec-live-badge").classList.add("hidden");
    document.getElementById("rec-timer-box").classList.add("hidden");
    document.getElementById("rec-live-split").classList.add("hidden");
    document.getElementById("rec-idle-prompt").classList.remove("hidden");
    document.getElementById("rec-session-title").textContent = "Ready to Record";
    document.getElementById("rec-session-subtitle").textContent = "Audio is processed locally with zero cloud leakage.";
}

function appendLiveTurn(msg) {
    const feed = document.getElementById("live-dialogue-feed");
    const empty = feed.querySelector(".empty-feed-hint");
    if (empty) empty.remove();

    const card = document.createElement("div");
    card.className = "live-bubble-turn";
    card.innerHTML = `
        <div class="live-bubble-meta">
            <span class="spk-name-tag" style="color: #818cf8;">${msg.speaker}</span>
            <span class="turn-timestamp">${msg.start.toFixed(1)}s - ${msg.end.toFixed(1)}s</span>
        </div>
        <div class="turn-speech-text">${msg.text}</div>
    `;
    feed.appendChild(card);
    feed.scrollTop = feed.scrollHeight;

    const countElem = document.getElementById("rec-dialogue-count");
    countElem.textContent = `${feed.children.length} turns`;
}

function appendLiveAction(item) {
    const feed = document.getElementById("live-action-feed");
    const empty = feed.querySelector(".empty-feed-hint");
    if (empty) empty.remove();

    const card = document.createElement("div");
    card.className = "live-action-card-mini";
    card.innerHTML = `
        <div class="action-card-task">⚡ ${item.task}</div>
        <div class="action-card-meta">
            👤 <strong>${item.assignee || 'Unassigned'}</strong> · 📅 <strong>${item.deadline || 'Pending'}</strong>
        </div>
    `;
    feed.appendChild(card);
    feed.scrollTop = feed.scrollHeight;

    const countElem = document.getElementById("rec-action-count");
    countElem.textContent = `${feed.children.length} tasks`;
}

// ── 4. IMPORT AUDIO RECORDING ───────────────────────────────────

function initDropZone() {
    const dropZone = document.getElementById("file-drop-zone");
    const fileInput = document.getElementById("audio-file-input");

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("drag-over");
    });
    dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("drag-over");
        if (e.dataTransfer.files.length) handleSelectedFile(e.dataTransfer.files[0]);
    });

    fileInput.addEventListener("change", () => {
        if (fileInput.files.length) handleSelectedFile(fileInput.files[0]);
    });
}

function handleSelectedFile(file) {
    // Auto-warm models on audio select
    fetch("/api/trigger-models", { method: "POST" }).catch(() => {});

    selectedFile = file;
    const ext = file.name.split('.').pop().toUpperCase();
    const sizeMb = (file.size / (1024 * 1024)).toFixed(1);

    document.getElementById("preview-file-ext").textContent = ext;
    document.getElementById("preview-file-name").textContent = file.name;
    document.getElementById("preview-file-size").textContent = `${sizeMb} MB`;
    document.getElementById("file-selected-card").classList.remove("hidden");
}

async function executeFileProcessing() {
    if (!selectedFile) return;

    const btn = document.getElementById("btn-process-file");
    btn.disabled = true;
    btn.textContent = "⏳ Uploading to Local Pipeline...";

    const minSpk = parseInt(document.getElementById("input-min-speakers").value) || 2;
    const maxSpk = parseInt(document.getElementById("input-max-speakers").value) || 10;

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
        // 1. Upload audio
        const uploadRes = await fetch("/api/upload", { method: "POST", body: formData });
        if (!uploadRes.ok) throw new Error("File upload failed");
        const uploadData = await uploadRes.json();
        const meetingId = uploadData.meeting_id;

        // Show Stepper
        document.getElementById("pipeline-stepper").classList.remove("hidden");
        connectProcessingWebSocket(meetingId);

        // 2. Start pipeline processing
        await fetch(`/api/process/${meetingId}?min_speakers=${minSpk}&max_speakers=${maxSpk}`, {
            method: "POST"
        });

    } catch (err) {
        alert("Processing error: " + err.message);
        btn.disabled = false;
        btn.textContent = "🚀 Process with Manent Pipeline";
    }
}

function connectProcessingWebSocket(meetingId) {
    const ws = new WebSocket(`ws://${location.host}/ws/meeting/${meetingId}`);
    
    ws.onmessage = (event) => {
        const status = JSON.parse(event.data);
        updateStepperStage(status.stage, status.progress, status.message);

        if (status.stage === "complete") {
            setTimeout(async () => {
                ws.close();
                await loadMeetings();
                openMeetingInStudio(meetingId);
            }, 1000);
        } else if (status.stage === "error") {
            alert("Pipeline error: " + status.error);
        }
    };
}

function updateStepperStage(stage, progress, message) {
    document.getElementById("stepper-msg").textContent = message;
    const stages = ["preprocess", "transcription", "diarization", "alignment", "intelligence"];
    
    stages.forEach(st => {
        const card = document.getElementById(`step-${st}`);
        if (!card) return;
        const statusElem = card.querySelector(".step-status");

        if (st === stage) {
            card.className = "step-card active";
            statusElem.textContent = `${Math.round(progress * 100)}% Running...`;
        } else if (stages.indexOf(st) < stages.indexOf(stage)) {
            card.className = "step-card completed";
            statusElem.textContent = "✓ Completed";
        }
    });
}

// ── 5. MINUTES STUDIO (INSPECTION & REVIEW) ────────────────────

async function openMeetingInStudio(meetingId) {
    try {
        const res = await fetch(`/api/meetings/${meetingId}`);
        if (!res.ok) throw new Error("Failed to load meeting details");
        currentMeeting = await res.json();

        renderMeetingStudio(currentMeeting);
        navigateTo("studio");
    } catch (e) {
        console.error("Error opening meeting:", e);
    }
}

function renderMeetingStudio(meeting) {
    document.getElementById("studio-empty-state").classList.add("hidden");
    document.getElementById("studio-content-layout").classList.remove("hidden");

    // Title & Meta
    document.getElementById("studio-meeting-title").textContent = meeting.filename || `Meeting ${meeting.meeting_id}`;
    const durMin = ((meeting.duration_sec || meeting.duration_seconds || 0) / 60).toFixed(1);
    document.getElementById("studio-duration").textContent = `⏱️ ${durMin} mins`;
    
    const speakers = meeting.speakers || [];
    document.getElementById("studio-speaker-count").textContent = `👥 ${speakers.length} Participants`;

    // 1. Render Speaker Analytics Bars
    renderSpeakerAnalytics(meeting.speaker_stats || []);

    // 2. Render Minutes & Topics
    document.getElementById("studio-summary-text").textContent = meeting.summary || "No summary available.";
    const topicsContainer = document.getElementById("studio-topics-list");
    topicsContainer.innerHTML = "";
    const topics = meeting.key_topics || meeting.important_points || [];
    if (topics.length > 0) {
        topics.forEach(t => {
            const pill = document.createElement("span");
            pill.className = "topic-pill";
            pill.textContent = t;
            topicsContainer.appendChild(pill);
        });
        document.getElementById("studio-topics-card").classList.remove("hidden");
    } else {
        document.getElementById("studio-topics-card").classList.add("hidden");
    }

    // 3. Render ActionFlow Tasks
    renderActionFlowGrid(meeting.action_items || []);

    // 4. Render Decisions
    renderDecisionsGrid(meeting.decisions || []);

    // 5. Render Who Spoke What (Speaker Dossier with Attached Audio)
    renderSpeakerDossier(meeting);

    // 6. Render Full Transcript
    renderTranscriptStream(meeting.transcript || meeting.aligned_transcript || []);

    // 7. Initialize Audio Player Bar
    setupAudioPlayer(meeting);
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function showToast(msg) {
    let toast = document.getElementById("manent-toast");
    if (!toast) {
        toast = document.createElement("div");
        toast.id = "manent-toast";
        toast.className = "manent-toast";
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => {
        toast.classList.remove("show");
    }, 3200);
}

async function promptRenameSpeaker(oldName) {
    if (!currentMeeting) return;
    const newName = prompt(`Enter new name for speaker "${oldName}":`, oldName);
    if (!newName || newName.trim() === "" || newName.trim() === oldName) return;

    try {
        const res = await fetch(`/api/meetings/${currentMeeting.meeting_id}/speakers/rename`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ old_name: oldName, new_name: newName.trim() })
        });
        if (!res.ok) throw new Error("Server rejected rename request");
        const updated = await res.json();
        currentMeeting = updated;
        renderMeetingStudio(currentMeeting);
        loadMeetings();
        showToast(`Speaker renamed: "${oldName}" ➔ "${newName.trim()}"`);
    } catch (e) {
        alert("Error renaming speaker: " + e.message);
    }
}

function renderSpeakerAnalytics(stats) {
    const container = document.getElementById("speaker-bars-container");
    container.innerHTML = "";

    if (!stats || stats.length === 0) {
        container.innerHTML = `<div class="empty-feed-hint">Individual speaking times will appear after diarization.</div>`;
        return;
    }

    stats.forEach((s, idx) => {
        const color = getSpeakerColor(idx);
        const card = document.createElement("div");
        card.className = "speaker-bar-card";
        const safeName = escapeHtml(s.name);
        card.innerHTML = `
            <div class="spk-bar-header">
                <div class="spk-name-group">
                    <span class="spk-bar-name" style="color: ${color.text}">${safeName}</span>
                    <button class="spk-rename-btn" onclick="promptRenameSpeaker('${safeName}')" title="Rename speaker in minutes and transcript">✏️</button>
                </div>
                <span class="spk-bar-time">${s.formatted_time || s.total_seconds + 's'}</span>
            </div>
            <div class="progress-track">
                <div class="progress-fill" style="width: ${s.percentage}%; background-color: ${color.text}"></div>
            </div>
            <div class="spk-bar-meta">
                <span>${s.percentage}% of conversation</span>
                <span>${s.turn_count || 0} turns</span>
            </div>
        `;
        container.appendChild(card);
    });
}

function renderActionFlowGrid(actions) {
    const container = document.getElementById("studio-actions-grid");
    document.getElementById("studio-actions-count").textContent = actions.length;
    container.innerHTML = "";

    if (!actions || actions.length === 0) {
        container.innerHTML = `<div class="empty-state-box">No action items detected in this meeting.</div>`;
        return;
    }

    actions.forEach(a => {
        const card = document.createElement("div");
        card.className = "actionflow-card";
        card.innerHTML = `
            <div class="actionflow-top">
                <span class="action-assignee-badge">👤 ${a.assignee || 'Unassigned'}</span>
                <span class="action-deadline-badge">📅 ${a.deadline || 'Not specified'}</span>
            </div>
            <div class="actionflow-task">${a.task}</div>
            ${a.evidence ? `<div class="actionflow-evidence">💬 "${a.evidence}"</div>` : ''}
        `;
        container.appendChild(card);
    });
}

function renderDecisionsGrid(decisions) {
    const container = document.getElementById("studio-decisions-grid");
    document.getElementById("studio-decisions-count").textContent = decisions.length;
    container.innerHTML = "";

    if (!decisions || decisions.length === 0) {
        container.innerHTML = `<div class="empty-state-box">No formal decisions recorded.</div>`;
        return;
    }

    decisions.forEach(d => {
        const card = document.createElement("div");
        card.className = "decision-card";
        card.innerHTML = `
            <span class="decision-badge-resolved">✓ ${d.status || 'RESOLVED'}</span>
            <div class="decision-text">${d.decision}</div>
            ${d.decided_by ? `<div class="decision-decided-by">Decided by: <strong>${d.decided_by}</strong></div>` : ''}
        `;
        container.appendChild(card);
    });
}

function renderTranscriptStream(transcript) {
    const container = document.getElementById("studio-transcript-stream");
    document.getElementById("studio-turns-count").textContent = transcript.length;
    container.innerHTML = "";

    if (!transcript || transcript.length === 0) {
        container.innerHTML = `<div class="empty-state-box">Transcript unavailable.</div>`;
        return;
    }

    transcript.forEach((t, idx) => {
        const card = document.createElement("div");
        card.className = "transcript-turn-card";
        const spkName = t.speaker_name || t.speaker || t.speaker_id || "Speaker";
        const ts = t.timestamp_str || `${t.start?.toFixed(1) || 0}s - ${t.end?.toFixed(1) || 0}s`;
        const safeName = escapeHtml(spkName);

        card.innerHTML = `
            <div class="turn-header">
                <span class="turn-speaker-badge" style="color: #818cf8; cursor: pointer;" onclick="promptRenameSpeaker('${safeName}')" title="Click to rename speaker across the meeting">${safeName} ✏️</span>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="turn-timestamp">${ts}</span>
                    <button class="btn-play-excerpt" onclick="playAudioExcerpt(${t.start || 0}, ${t.end || 0})" style="padding: 2px 8px; font-size: 11px;">▶️ Play</button>
                </div>
            </div>
            <div class="turn-text-body">${escapeHtml(t.text)}</div>
        `;
        container.appendChild(card);
    });
}

function setupAudioPlayer(meeting) {
    const audioBar = document.getElementById("studio-audio-player-bar");
    const audioEl = document.getElementById("meeting-audio-element");
    if (!audioBar || !audioEl) return;

    audioBar.classList.remove("hidden");
    audioEl.src = `/api/meetings/${meeting.meeting_id}/audio`;
    document.getElementById("audio-current-label").textContent = meeting.filename || `Meeting ${meeting.meeting_id}`;
}

function playAudioExcerpt(startSec, endSec) {
    const audioEl = document.getElementById("meeting-audio-element");
    if (!audioEl) return;
    audioEl.currentTime = startSec;
    audioEl.play().catch(e => console.warn("Playback prevented:", e));
    showToast(`Playing audio: ${startSec.toFixed(1)}s - ${endSec.toFixed(1)}s`);
}

async function renderSpeakerDossier(meeting) {
    const container = document.getElementById("studio-speakers-dossier");
    if (!container) return;
    container.innerHTML = `<div class="empty-feed-hint">Organizing individual speaker statements...</div>`;

    try {
        const res = await fetch(`/api/meetings/${meeting.meeting_id}/speakers-grouped`);
        if (!res.ok) throw new Error("Could not retrieve grouped speakers");
        const data = await res.json();
        const speakers = data.speakers || [];

        const countBadge = document.getElementById("studio-speakers-count");
        if (countBadge) countBadge.textContent = speakers.length;

        container.innerHTML = "";
        if (speakers.length === 0) {
            container.innerHTML = `<div class="empty-state-box">No speaker dialogue records found.</div>`;
            return;
        }

        speakers.forEach((spk, idx) => {
            const color = getSpeakerColor(idx);
            const card = document.createElement("div");
            card.className = "speaker-dossier-card";
            const safeName = escapeHtml(spk.name);

            let statementsHtml = "";
            (spk.statements || []).forEach(stmt => {
                const start = stmt.start || 0;
                const end = stmt.end || 0;
                statementsHtml += `
                    <div class="dossier-statement-item">
                        <div class="statement-content">
                            <div class="statement-time">⏱️ ${stmt.timestamp_str} (${(end - start).toFixed(1)}s)</div>
                            <div class="statement-text">"${escapeHtml(stmt.text)}"</div>
                        </div>
                        <button class="btn-play-excerpt" onclick="playAudioExcerpt(${start}, ${end})" title="Play this audio excerpt">
                            ▶️ Play
                        </button>
                    </div>
                `;
            });

            card.innerHTML = `
                <div class="dossier-header">
                    <div class="dossier-speaker-info">
                        <div class="dossier-avatar" style="background: ${color.bg}; color: ${color.text}; border: 1px solid ${color.border};">
                            ${safeName.charAt(0).toUpperCase()}
                        </div>
                        <div>
                            <div class="dossier-name" style="color: ${color.text}; cursor: pointer;" onclick="promptRenameSpeaker('${safeName}')" title="Rename speaker">
                                ${safeName} ✏️
                            </div>
                        </div>
                    </div>
                    <div class="dossier-stats-pill">
                        🗣️ ${spk.turn_count} statements · ⏱️ ${spk.formatted_time || spk.total_seconds + 's'} (${spk.percentage}%)
                    </div>
                </div>
                <div class="dossier-statements-list">
                    ${statementsHtml || '<div class="empty-feed-hint">No statements recorded for this participant.</div>'}
                </div>
            `;
            container.appendChild(card);
        });
    } catch (e) {
        console.error("Error loading speaker dossier:", e);
        container.innerHTML = `<div class="empty-state-box">Could not load speaker breakdown: ${e.message}</div>`;
    }
}

function filterTranscriptTurns() {
    const query = document.getElementById("transcript-filter-input").value.toLowerCase();
    document.querySelectorAll(".transcript-turn-card").forEach(card => {
        const text = card.textContent.toLowerCase();
        card.style.display = text.includes(query) ? "block" : "none";
    });
}

function switchStudioTab(tab) {
    currentStudioTab = tab;
    document.querySelectorAll(".studio-tab-btn").forEach(b => b.classList.remove("active"));
    document.getElementById(`tab-${tab}-btn`).classList.add("active");

    document.querySelectorAll(".studio-pane").forEach(p => p.classList.remove("active"));
    document.getElementById(`studio-pane-${tab}`).classList.add("active");
}

// ── 6. EXPORTING MINUTES ───────────────────────────────────────

function exportMinutesMarkdown() {
    if (!currentMeeting) return;
    const m = currentMeeting;
    let md = `# Meeting Minutes: ${m.filename}\n\n`;
    md += `**Date:** ${m.processed_at || 'N/A'}\n`;
    md += `**Duration:** ${((m.duration_sec || 0)/60).toFixed(1)} mins\n\n`;
    md += `## Executive Summary\n${m.summary}\n\n`;

    md += `## Speaker Participation\n`;
    (m.speaker_stats || []).forEach(s => {
        md += `- **${s.name}**: ${s.formatted_time} (${s.percentage}% of speech, ${s.turn_count} turns)\n`;
    });
    md += `\n`;

    md += `## Key Decisions\n`;
    (m.decisions || []).forEach(d => {
        md += `- [${d.status || 'RESOLVED'}] ${d.decision} ${d.decided_by ? `(Decided by: ${d.decided_by})` : ''}\n`;
    });
    md += `\n`;

    md += `## ActionFlow (Tasks Assigned)\n`;
    (m.action_items || []).forEach(a => {
        md += `- **[${a.assignee || 'Unassigned'}]** ${a.task} *(Deadline: ${a.deadline || 'None'})*\n`;
        if (a.evidence) md += `  > "${a.evidence}"\n`;
    });

    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Manent_Minutes_${m.meeting_id}.md`;
    a.click();
}

function exportMinutesJSON() {
    if (!currentMeeting) return;
    const jsonStr = JSON.stringify(currentMeeting, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Manent_${currentMeeting.meeting_id}.json`;
    a.click();
}
