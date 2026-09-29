# Debian 13 (hassio debian-base) ships Python 3.13 — no NumPy 1.26 wheel, and NumPy 2.x
# needs x86-64-v2 (breaks QNAP/QEMU). Use standalone CPython 3.12 + binary wheels instead.
ARG BUILD_ARCH=amd64
FROM ghcr.io/hassio-addons/debian-base/${BUILD_ARCH}:9.5.0

ARG BUILD_ARCH
ARG PBS_RELEASE=20251010
ARG PYTHON_VERSION=3.12.12

ENV PIP_BREAK_SYSTEM_PACKAGES=1 \
    PIP_PREFER_BINARY=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    MODELS_DIR=/models \
    PATH="/opt/python/bin:${PATH}" \
    CUDA_VISIBLE_DEVICES=""

# OpenCV / PyTorch runtime libs (NumPy wheel bundles its own BLAS — no libopenblas.so.0 needed).
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      libgl1 \
      libglib2.0-0 \
      libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Baseline x86_64 (not x86_64_v2) for QEMU / older NAS CPUs.
RUN case "${BUILD_ARCH}" in \
      amd64) PBS_TRIPLE="x86_64-unknown-linux-gnu" ;; \
      aarch64) PBS_TRIPLE="aarch64-unknown-linux-gnu" ;; \
      *) echo "Unsupported BUILD_ARCH=${BUILD_ARCH}" >&2; exit 1 ;; \
    esac && \
    curl -fsSL \
      "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/cpython-${PYTHON_VERSION}+${PBS_RELEASE}-${PBS_TRIPLE}-install_only.tar.gz" \
      | tar xz -C /opt && \
    /opt/python/bin/python3 -m pip install --no-cache-dir --upgrade pip

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt

# CPU-only PyTorch (QNAP has no GPU). Install before rfdetr so pip does not pull CUDA wheels.
RUN pip install --no-cache-dir "numpy==1.26.4" && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r /tmp/requirements.txt && \
    pip install --no-cache-dir --force-reinstall --no-deps "numpy==1.26.4" && \
    pip install --no-cache-dir --force-reinstall --no-deps torch torchvision \
      --index-url https://download.pytorch.org/whl/cpu

RUN mkdir -p /models

COPY main.py .
COPY static/ static/
COPY run.sh /
RUN chmod a+x /run.sh

# Do NOT add a Docker HEALTHCHECK here.
# Home Assistant Supervisor manages add-on health. A strict HEALTHCHECK fails on
# slow NAS hardware while RF-DETR weights load, even though the add-on is fine.

CMD [ "/run.sh" ]
