# ── Stage 1: Build the React frontend ─────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./
RUN npx vite build

# ── Stage 2: Python backend + serve frontend ───────────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

COPY --from=frontend-builder /frontend/dist ./dist

RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
