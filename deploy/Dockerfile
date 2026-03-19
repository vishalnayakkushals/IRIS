# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app
ARG IRIS_ENABLE_YOLO=0
COPY deploy/requirements.docker.txt ./requirements.docker.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxcb1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.docker.txt && \
    if [ "$IRIS_ENABLE_YOLO" = "1" ]; then \
      pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision && \
      pip install "ultralytics>=8.3,<9.0" && \
      pip install "numpy<2" "pyarrow>=15.0,<16.0"; \
    fi
COPY . .

EXPOSE 8765
CMD ["streamlit", "run", "src/run_dashboard.py", "--server.address=0.0.0.0", "--server.port=8765", "--browser.serverAddress=localhost"]
