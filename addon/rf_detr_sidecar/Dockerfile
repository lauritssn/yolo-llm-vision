FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RFDETR_MODEL=nano \
    CONFIDENCE_THRESHOLD=0.5 \
    PORT=8000 \
    MODELS_DIR=/models

RUN apt-get update && \
    apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download default RF-DETR-Seg Nano weights (~128 MB) at build time
RUN python -c "from rfdetr import RFDETRSegNano; RFDETRSegNano()"

RUN mkdir -p /models

COPY main.py .
COPY static/ static/

RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app /models
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
