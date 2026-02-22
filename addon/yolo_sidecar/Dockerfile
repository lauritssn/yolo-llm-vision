ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apk add --no-cache \
        libstdc++ \
        libgcc \
        libjpeg-turbo \
        zlib \
        libffi \
    && apk add --no-cache --virtual .build-deps \
        python3-dev \
        build-base \
        musl-dev \
        jpeg-dev \
        zlib-dev \
        libffi-dev \
    && pip3 install --no-cache-dir --break-system-packages \
        ultralytics \
        fastapi \
        "uvicorn[standard]" \
        opencv-python-headless \
        httpx \
        python-multipart \
        Pillow \
        numpy \
    && apk del .build-deps

RUN python3 -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" \
    && mkdir -p /models \
    && find /root -name 'yolov8n.pt' -exec cp {} /models/yolov8n.pt \; 2>/dev/null || true

WORKDIR /app
COPY main.py .
COPY run.sh /
RUN chmod a+x /run.sh

EXPOSE 8000

CMD ["/run.sh"]
