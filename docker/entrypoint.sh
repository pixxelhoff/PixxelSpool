#!/bin/sh
# Start the PC/SC service for USB NFC readers (only useful when a reader is passed in), then PixxelSpool.
set -e
if [ "${PIXXELSPOOL_PCSCD:-1}" = "1" ] && command -v pcscd >/dev/null 2>&1; then
  mkdir -p /run/pcscd
  pcscd 2>/dev/null || echo "pcscd did not start (no USB reader passed in?)"
fi
exec python run.py --lan --no-browser --port "${PIXXELSPOOL_PORT:-8000}"
