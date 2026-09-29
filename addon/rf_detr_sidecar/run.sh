#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
# Home Assistant add-on entrypoint — options from /data/options.json via bashio.

bashio::log.info "Starting RF-DETR segmentation sidecar"

export RFDETR_MODEL="$(bashio::config 'model')"
export CONFIDENCE_THRESHOLD="$(bashio::config 'confidence_threshold')"
export LOG_LEVEL="$(bashio::config 'log_level')"
export PORT=8000
export MODELS_DIR=/models

cd /app || bashio::exit.nok "Missing /app directory"

bashio::log.info "Model preset: ${RFDETR_MODEL}, threshold: ${CONFIDENCE_THRESHOLD}"
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}"
