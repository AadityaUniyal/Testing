# AWS Production Deployment & Architectural Guide

This guide details how to deploy the Manent Meeting Intelligence platform on **Amazon Web Services (AWS)** with GPU acceleration, dynamic decision revision tracking, and speaker-segregated audio playback.

---

## 1. Recommended AWS Infrastructure

The Manent pipeline utilizes local, offline-capable models (Whisper Large-v3 Turbo, Pyannote Community-1, Qwen 2.5 0.8B, Silero VAD v5). To run sub-second streaming inference and batch diarization at production scale, GPU compute is recommended:

| Instance Type | GPU / Accelerator | vCPU | RAM | Typical Cost (Spot / On-Demand) | Best For |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`g4dn.xlarge`** *(Recommended)* | 1x NVIDIA T4 (16 GB VRAM) | 4 | 16 GB | **~$0.16 / hr (Spot)**<br>~$0.526 / hr (On-Demand) | High-volume production at lowest cost. 420ms Whisper streaming. |
| **`g5.xlarge`** | 1x NVIDIA A10G (24 GB VRAM) | 4 | 16 GB | **~$0.31 / hr (Spot)**<br>~$1.006 / hr (On-Demand) | Maximum concurrency, ultra-low latency. |
| **`t4g.xlarge` / `c6i.2xlarge`** | CPU-Only (Graviton / Intel) | 4-8 | 16 GB | **~$0.13 / hr** | Dev/Testing fallback (Whisper ~4s, Pyannote ~45s). |

---

## 2. Step-by-Step AWS EC2 Deployment

### Step 1: Launch EC2 Instance
1. In the **AWS EC2 Console**, click **Launch Instance**.
2. **Name**: `manent-intelligence-prod`.
3. **AMI**: Choose **Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)** or standard **Ubuntu 22.04 LTS**.
4. **Instance Type**: Select `g4dn.xlarge`.
5. **Storage**: Allocate **50 GB GP3 SSD** (accommodates Docker, OS, models, and audio cache).
6. **Security Group**:
   - Inbound `SSH (22)`: Your IP.
   - Inbound `HTTP (80)`: `0.0.0.0/0`.
   - Inbound `HTTPS (443)`: `0.0.0.0/0`.
   - Inbound `Custom TCP (8000)`: Application port (or reverse-proxied via Nginx).

---

### Step 2: Install NVIDIA Container Toolkit (If using standard Ubuntu)
```bash
# Add NVIDIA container repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit docker.io docker-compose-plugin
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

---

### Step 3: Clone Repository & Deploy Container
```bash
# 1. Clone repository
git clone https://github.com/AadityaUniyal/Testing.git /opt/manent
cd /opt/manent

# 2. Configure Environment (.env)
cat <<EOF > .env
SUPABASE_URL=https://wiwkyjwhymkvhtribakw.supabase.co
SUPABASE_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY
LLM_HOST=127.0.0.1
LLM_PORT=8081
EOF

# 3. Launch via Docker Compose with GPU passthrough
docker compose up -d --build
```

---

### Step 4: Configure Nginx & SSL (Let's Encrypt HTTPS)
To enable microphone access from iOS and web browsers, **HTTPS is required**.

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx

# Configure Nginx reverse proxy (/etc/nginx/sites-available/manent)
sudo tee /etc/nginx/sites-available/manent <<'EOF'
server {
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/manent /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Issue free SSL Certificate
sudo certbot --nginx -d api.yourdomain.com --non-interactive --agree-tos -m admin@yourdomain.com
```

---

## 3. Dynamic Decision Override & Revision Tracking

### The Problem:
In real discussions, participants frequently propose ideas, debate them, and then explicitly reject or supersede them late in the meeting (e.g., at minute 45: *"Actually, scratch that earlier plan, we are NOT doing X, we decided Y instead"*).

### How Manent Solves This:
1. **Chronological State Tracking**:
   The Qwen extraction prompt enforces chronological resolution:
   - Intermediate suggestions that were cancelled or altered are filtered out.
   - Only the **FINAL authoritative decision** and **FINAL agreed deadline/assignee** are extracted into `decisions` and `action_items`.
2. **Re-Alignment & Dynamic Update**:
   - The stored records in SQLite and Supabase reflect the final truth.
   - If a user manually renames a participant or edits an outcome via `/api/meetings/{id}/speakers/rename`, the entire database (transcripts, speaker stats, action items, and Supabase cloud tables) updates dynamically.

---

## 4. "Who Spoke What" — Segregated Audio Breakdown

The platform provides dedicated speaker breakdown and excerpt playback:

1. **API Endpoint**: `GET /api/meetings/{meeting_id}/speakers-grouped`
   - Returns every participant with their talk time (`total_seconds`, `percentage`, `turn_count`).
   - Grouped statements list: Each statement includes `start`, `end`, formatted timestamp (`MM:SS`), and exact transcript quote.
2. **Audio Streaming Endpoint**: `GET /api/meetings/{meeting_id}/audio`
   - Streams the raw or normalized meeting audio file with seek range support.
3. **Minutes Studio UI ("👥 Who Spoke What" Tab)**:
   - Displays each speaker's dossier card.
   - Next to every individual sentence spoken, a **"▶️ Play"** button immediately jumps the integrated audio player to that exact millisecond.
