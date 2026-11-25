# PixxelSpool as a Docker image (amd64 and arm64, e.g. a NAS, a home server or a Raspberry Pi with Docker).
# Data lives in the volume /data. Updates: pull the new image (docker compose pull && docker compose up -d).
# See docker/README.md and docker-compose.yml.

# --- build stage: pyscard (USB NFC readers) is compiled against the PC/SC library
FROM python:3.12-slim-bookworm AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libc6-dev swig libpcsclite-dev \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# --- runtime
FROM python:3.12-slim-bookworm
LABEL org.opencontainers.image.title="PixxelSpool" \
      org.opencontainers.image.description="Filament storage for Bambu Lab printers: NFC, AMS sync, statistics" \
      org.opencontainers.image.source="https://github.com/pixxelhoff/PixxelSpool" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
# pcscd + libccid: USB NFC readers (ACR122U, ACR1252U …); the reader is passed in with the device list in compose
RUN apt-get update \
 && apt-get install -y --no-install-recommends pcscd libccid libpcsclite1 tini tzdata \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY filament_tool ./filament_tool
COPY run.py VERSION LICENSE NOTICE CHANGELOG.md CHANGELOG.de.md ./
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /data
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PIXXELSPOOL_DOCKER=1 \
    PIXXELSPOOL_DATA=/data \
    PIXXELSPOOL_PORT=8000 \
    TZ=Europe/Berlin
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/static/favicon-32.png' % os.environ.get('PIXXELSPOOL_PORT','8000'), timeout=4)"
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
