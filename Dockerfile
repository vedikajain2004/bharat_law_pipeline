# Dockerfile — Bharat Law Pipeline
# Build:   docker build -t bharat-law-pipeline .
# Run:     docker run --rm bharat-law-pipeline
# With mounted output:
#   docker run --rm -v $(pwd)/output:/app/output bharat-law-pipeline

FROM python:3.11-slim

# System deps for Playwright Chromium + PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl ca-certificates fonts-liberation \
    libglib2.0-0 libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && python -m spacy download en_core_web_sm \
 && python -m playwright install chromium --with-deps

COPY . .

# Create output directories
RUN mkdir -p raw normalized chunks ner_out

# Default: full pipeline
CMD ["bash", "run.sh", "--skip-install"]
