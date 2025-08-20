FROM python:3.12-slim

LABEL org.opencontainers.image.title="GitHub API Mock Server"
LABEL org.opencontainers.image.description="Mock GitHub API server for testing without real tokens"
LABEL org.opencontainers.image.source="https://github.com/feddericovonwernich/agentic-coding-workflow"

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the mock server and responses
COPY mock_server.py .
COPY responses/ responses/

# Expose the port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Run the server
CMD ["python", "mock_server.py", "--host", "0.0.0.0", "--port", "8080"]