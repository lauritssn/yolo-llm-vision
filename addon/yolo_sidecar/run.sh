#!/usr/bin/env bash
# shellcheck shell=bash
# Reads addon options from /data/options.json (Supervisor) or uses defaults.

set -e

read_options() {
  if [ -f /data/options.json ]; then
    python3 -c "
import json
o = json.load(open('/data/options.json'))
m = o.get('model', 'yolov8n.pt')
c = o.get('confidence_threshold', 0.5)
l = o.get('log_level', 'info')
print(f'export YOLO_MODEL=\"{m}\"')
print(f'export CONFIDENCE_THRESHOLD=\"{c}\"')
print(f'export LOG_LEVEL=\"{l}\"')
"
  else
    echo 'export YOLO_MODEL="yolov8n.pt"'
    echo 'export CONFIDENCE_THRESHOLD="0.5"'
    echo 'export LOG_LEVEL="info"'
  fi
}

eval "$(read_options)"

echo "[INFO] Starting YOLO sidecar — model=${YOLO_MODEL}, threshold=${CONFIDENCE_THRESHOLD}"
exec python3 /app/main.py
