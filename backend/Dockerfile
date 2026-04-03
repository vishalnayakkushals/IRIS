# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json ./
RUN npm install --silent
COPY frontend/ ./
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 2: Python backend (FastAPI + Celery)
FROM python:3.11-slim AS backend
WORKDIR /app

# System deps for opencv/numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# Install existing project deps first (layer cache)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install backend-specific deps
COPY backend/requirements.txt /app/backend_requirements.txt
RUN pip install --no-cache-dir -r backend_requirements.txt

# Copy project source
COPY . /app

# Embed React build into FastAPI static directory
COPY --from=frontend-build /frontend/dist /app/backend/app/static

ENV PYTHONPATH=/app
ENV OMP_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV NUMEXPR_NUM_THREADS=1

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8766"]
