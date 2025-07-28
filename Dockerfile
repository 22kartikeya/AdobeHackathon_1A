# Explicitly specify AMD64 platform for cross-platform compatibility
FROM --platform=linux/amd64 python:3.10

# Set working directory
WORKDIR /app

# Install system dependencies for PyMuPDF and pdfplumber
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create input and output directories
RUN mkdir -p /app/input /app/output

# Copy requirements first (for better Docker layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code
COPY process_pdfs.py .

# Set the command to run your application
CMD ["python", "process_pdfs.py"]
