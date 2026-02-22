#!/usr/bin/env bashio
# shellcheck shell=bash

YOLO_MODEL=$(bashio::config 'model' 'yolov8n.pt')
CONFIDENCE_THRESHOLD=$(bashio::config 'confidence_threshold' '0.5')
LOG_LEVEL=$(bashio::config 'log_level' 'info')

export YOLO_MODEL
export CONFIDENCE_THRESHOLD
export LOG_LEVEL

bashio::log.info "Starting YOLO sidecar — model=${YOLO_MODEL}, threshold=${CONFIDENCE_THRESHOLD}"

exec python3 /app/main.py
