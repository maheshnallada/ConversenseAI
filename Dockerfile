FROM python:3.12-slim

WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/pyproject.toml /app/backend/
RUN pip install --no-cache-dir -e /app/backend

# Copy source code and scripts
COPY backend /app/backend
COPY data /app/data
COPY scripts /app/scripts

ENV PYTHONPATH=/app/backend
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

