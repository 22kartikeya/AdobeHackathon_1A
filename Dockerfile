FROM --platform=linux/amd64 python:3.10-slim

WORKDIR /app
# Install OS-level dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpoppler-cpp-dev \
    python3-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY app/ ./app/

ENTRYPOINT ["python3", "app/main.py"]
