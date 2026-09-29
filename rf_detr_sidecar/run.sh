#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
# Home Assistant add-on entrypoint — options from /data/options.json via bashio.

bashio::log.info "Starting RF-DETR segmentation sidecar"

export RFDETR_MODEL="$(bashio::config 'model')"
export CONFIDENCE_THRESHOLD="$(bashio::config 'confidence_threshold')"
export LOG_LEVEL="$(bashio::config 'log_level')"
export PORT=8000
export MODELS_DIR=/models

# Disable oneDNN on older/QEMU CPUs (PyTorch conv "could not create a primitive").
export TORCH_USE_ONEDNN=0
export DNNL_MAX_CPU_ISA=SSE41
export ATEN_CPU_CAPABILITY=DEFAULT
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-2}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-2}"
export TORCH_NUM_THREADS="${TORCH_NUM_THREADS:-2}"

cd /app || bashio::exit.nok "Missing /app directory"

bashio::log.info "Model preset: ${RFDETR_MODEL}, threshold: ${CONFIDENCE_THRESHOLD}"
exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT}"
