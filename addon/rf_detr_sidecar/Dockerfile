ARG BUILD_FROM
FROM ${BUILD_FROM}

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
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

RUN mkdir -p /models

COPY main.py .
COPY static/ static/
COPY run.sh /
RUN chmod a+x /run.sh

# Do NOT add a Docker HEALTHCHECK here.
# Home Assistant Supervisor manages add-on health. A strict HEALTHCHECK fails on
# slow NAS hardware while RF-DETR weights load, even though the add-on is fine.

CMD [ "/run.sh" ]
