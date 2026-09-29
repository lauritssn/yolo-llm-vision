# hassio debian-base 8.x and 9.x both use Debian 13 (Python 3.13).
# NumPy 1.26 has no cp313 wheel; NumPy 2.x wheels need x86-64-v2 (QNAP/QEMU).
ARG BUILD_ARCH=amd64
FROM ghcr.io/hassio-addons/debian-base/${BUILD_ARCH}:9.5.0

ENV PIP_BREAK_SYSTEM_PACKAGES=1 \
    PIP_PREFER_BINARY=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    MODELS_DIR=/models

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt

# Build NumPy 1.26 from source on Python 3.13 so binaries match the host/VM CPU.
# First install can take 10–20 minutes on a NAS while NumPy compiles.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      python3 \
      python3-pip \
      python3-dev \
      build-essential \
      gfortran \
      libopenblas-dev \
      libgl1 \
      libglib2.0-0 \
    && pip3 install --no-cache-dir "numpy==1.26.4" && \
    pip3 install --no-cache-dir -r /tmp/requirements.txt && \
    pip3 install --no-cache-dir --force-reinstall --no-deps "numpy==1.26.4" && \
    apt-get purge -y --auto-remove \
      build-essential \
      gfortran \
      libopenblas-dev \
      python3-dev \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /models

COPY main.py .
COPY static/ static/
COPY run.sh /
RUN chmod a+x /run.sh

# Do NOT add a Docker HEALTHCHECK here.
# Home Assistant Supervisor manages add-on health. A strict HEALTHCHECK fails on
# slow NAS hardware while RF-DETR weights load, even though the add-on is fine.

CMD [ "/run.sh" ]
