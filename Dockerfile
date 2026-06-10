# Use the official lightweight Python 3.13 image for production parities
FROM python:3.13-slim

# Set the working directory inside the container runtime context
WORKDIR /app

# Prevent Python from buffering stdout/stderr to guarantee instant log streaming to AWS CloudWatch
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install OS-level shared libraries needed by PyMuPDF to process canvas layouts in a headless environment
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifests first to maximize Docker layer caching efficiency
COPY requirements.txt .

# Upgrade package manager and install locked production dependencies via pip3 explicitly
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# Recursively copy the local source directory containing core logic and static PDF template assets
COPY src/ ./src/

# Explicit execution endpoint invocation mapping via python3 to avoid ECS routing failures
CMD ["python3", "-m", "src.app"]