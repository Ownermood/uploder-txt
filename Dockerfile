# ── Golden Eagle Bot v2 ── Production Build ────────────────────────────────────
FROM python:3.12-slim-bookworm

# Env — no .pyc files, unbuffered stdout for live logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ── System packages ─────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        aria2 \
        wget \
        curl \
        unzip \
        gcc \
        g++ \
        cmake \
        make \
        libssl-dev \
        ca-certificates \
        supervisor \
    && rm -rf /var/lib/apt/lists/*

# ── Bento4 (mp4decrypt) ─────────────────────────────────────────────────────────
RUN wget -q https://github.com/axiomatic-systems/Bento4/archive/v1.6.0-639.zip \
    && unzip -q v1.6.0-639.zip \
    && cd Bento4-1.6.0-639 \
    && mkdir build && cd build \
    && cmake .. -DCMAKE_BUILD_TYPE=Release \
    && make -j$(nproc) \
    && cp mp4decrypt /usr/local/bin/ \
    && cd ../.. \
    && rm -rf Bento4-1.6.0-639 v1.6.0-639.zip

# ── Python deps ─────────────────────────────────────────────────────────────────
COPY sainibots.txt .
RUN pip install --upgrade pip \
    && pip install -r sainibots.txt \
    && pip install -U yt-dlp psutil

# ── App files ────────────────────────────────────────────────────────────────────
COPY . .

# Create persistent downloads dir
RUN mkdir -p downloads /var/log/supervisor

# ── Supervisor config ────────────────────────────────────────────────────────────
RUN cat > /etc/supervisor/conf.d/golden_eagle.conf << 'EOF'
[supervisord]
nodaemon=true
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid

[program:flask]
command=gunicorn app:app --bind 0.0.0.0:%(ENV_PORT)s --workers 1 --timeout 120
directory=/app
autostart=true
autorestart=true
stderr_logfile=/var/log/supervisor/flask.err.log
stdout_logfile=/var/log/supervisor/flask.out.log
environment=PORT="%(ENV_PORT)s"

[program:bot]
command=python3 modules/main.py
directory=/app
autostart=true
autorestart=true
startsecs=5
stderr_logfile=/var/log/supervisor/bot.err.log
stdout_logfile=/var/log/supervisor/bot.out.log
EOF

EXPOSE 8080

# ── Run via supervisor (manages both gunicorn + bot with proper signal handling) ─
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
