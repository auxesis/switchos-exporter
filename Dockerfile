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

# Copy .env file if it exists (for standalone builds)
COPY .env* ./

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash exporter && \
    chown -R exporter:exporter /app
USER exporter

# Expose Prometheus metrics port
EXPOSE 9000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:9000/metrics || exit 1

# Run the SwitchOS exporter
CMD ["python3", "switchos_exporter.py"]