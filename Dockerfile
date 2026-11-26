FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend/ /app/backend/
COPY data/raw/healthcare-dataset-stroke-data.csv /app/data/raw/healthcare-dataset-stroke-data.csv
COPY --from=frontend /build/dist /app/frontend/dist
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 Q_SMARTSTROKE_WORKBOOK_PATH=/app/state/q_smartstroke_workbook.xlsx
EXPOSE 8000
WORKDIR /app/backend
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
