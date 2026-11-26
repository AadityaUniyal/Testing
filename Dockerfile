# Multi-stage GPU-accelerated Dockerfile for Manent Meeting Intelligence Platform
# Base: NVIDIA CUDA 12.2 on Ubuntu 22.04
FROM nvidia/cuda:12.2.2-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH"

# 1. Install system dependencies & audio tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    ffmpeg \
    libsndfile1 \
    git \
    curl \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3.11 /usr/bin/python

# 2. Set working directory
WORKDIR /app

# 3. Install PyTorch with CUDA 12.1 support
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 4. Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir onnxruntime-gpu silero-vad scipy soundfile httpx

# 5. Copy project source code
COPY . .

# 6. Expose web server and model ports
EXPOSE 8000 8081 8082

# 7. Default startup
CMD ["python", "run.py"]
