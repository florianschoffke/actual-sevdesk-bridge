FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1

# The .env file will be mounted at runtime to /app/.env
# Default command runs the sync loop
CMD ["sh", "-c", "echo '🚀 Starting Actual-SevDesk Bridge...' && echo '📅 Current time:' $(date) && echo '📁 Checking .env file...' && ls -la /app/.env 2>/dev/null && echo '✅ .env file found' || echo '⚠️  .env file not found!' && echo '' && while true; do echo '🔄 Starting sync cycle...' && python3 main.py sync-all && python3 verify_sync.py && echo '✅ Sync cycle complete. Sleeping for 1 hour...' && sleep 3600; done"]
