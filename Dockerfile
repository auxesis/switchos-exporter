# Use Python 3.11 slim image for smaller footprint
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash exporter && \
    chown -R exporter:exporter /app
USER exporter

# Expose Prometheus metrics port and health check port
EXPOSE 9000 9001

# Health check - verifies collection is happening, not just HTTP server is up
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:9001/health || exit 1

# Run the SwitchOS exporter
CMD ["python3", "switchos_exporter.py"]