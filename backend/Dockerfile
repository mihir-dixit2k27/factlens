# FactLens Backend Dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps for PyMuPDF and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    libffi-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Non-root user
RUN useradd -m -u 1000 factlens && chown -R factlens:factlens /app
USER factlens

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
