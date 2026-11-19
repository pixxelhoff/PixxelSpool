#!/usr/bin/env bash
# Local test server with mock data (no printer, reader or Home Assistant needed). Usage: tools/dev/mock.sh [port]
# Creates a throw-away Python environment in .devenv/ and a throw-away data folder in .devdata/ (both git-ignored).
# Stop it with: pkill -f "uvicorn filament_tool.main"
set -e
cd "$(dirname "$0")/../.."
PORT="${1:-8135}"
if [ ! -x .devenv/bin/python ]; then
  python3 -m venv .devenv
  # pyscard needs system libraries and is not needed for the mock server
  grep -v '^pyscard' requirements.txt > .devenv/req.txt
  .devenv/bin/pip install -q -r .devenv/req.txt
fi
mkdir -p .devdata
export PIXXELSPOOL_DATA="$PWD/.devdata" FILAMENT_MOCK=1
nohup .devenv/bin/python -m uvicorn filament_tool.main:app --port "$PORT" > .devdata/server.log 2>&1 &
sleep 3
echo "PixxelSpool mock server: http://localhost:$PORT   (log: .devdata/server.log)"
