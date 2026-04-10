FROM python:3.11-slim

# Python runtime settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# Set the application directory
WORKDIR /app

# Install build tools and common native dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency list first for better layer caching
COPY requirements.txt ./requirements.txt

# Install Python dependencies
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the full project into the image
COPY . .

# Create and use a non-root user for better security
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose the default application port
EXPOSE 8000

# Start FastAPI with Uvicorn on the Render-provided PORT when available
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]

