ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Debian: runtime deps for OpenCV
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download default model and copy to /models
RUN python3 -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" \
    && mkdir -p /models \
    && find /root -name 'yolov8n.pt' -exec cp {} /models/yolov8n.pt \; 2>/dev/null || true

COPY main.py .
COPY run.sh /
RUN chmod a+x /run.sh

EXPOSE 8000

CMD ["/run.sh"]
