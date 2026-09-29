# Debian base with s6-init (PyTorch / RF-DETR). Supervisor passes BUILD_ARCH.
ARG BUILD_ARCH=amd64
FROM ghcr.io/hassio-addons/debian-base/${BUILD_ARCH}:9.5.0

ENV PIP_BREAK_SYSTEM_PACKAGES=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    MODELS_DIR=/models

# RF-DETR / OpenCV runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 \
      python3-pip \
      libgl1 \
      libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
# Install NumPy 1.26 first — NumPy 2.x manylinux wheels need x86-64-v2 (breaks QNAP/QEMU VMs).
RUN pip3 install --no-cache-dir "numpy==1.26.4" && \
    pip3 install --no-cache-dir -r /tmp/requirements.txt && \
    pip3 install --no-cache-dir --force-reinstall --no-deps "numpy==1.26.4"

RUN mkdir -p /models

COPY main.py .
COPY static/ static/
COPY run.sh /
RUN chmod a+x /run.sh

# Do NOT add a Docker HEALTHCHECK here.
# Home Assistant Supervisor manages add-on health. A strict HEALTHCHECK fails on
# slow NAS hardware while RF-DETR weights load, even though the add-on is fine.

CMD [ "/run.sh" ]
