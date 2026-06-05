# Use a standard Python slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies, including libraries for audio/AI and Piper compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    tar \
    ffmpeg \
    libavdevice-dev \
    libavfilter-dev \
    libavformat-dev \
    libavcodec-dev \
    libswresample-dev \
    libswscale-dev \
    libavutil-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Piper TTS
RUN curl -L https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz | tar -xzf - -C /usr/local/bin --strip-components=1

# Create workspace directory
WORKDIR /workspace

# Pre-download default Piper Voice model and config
RUN mkdir -p /workspace/voices && \
    curl -L https://github.com/rhasspy/piper/releases/download/v0.0.2/en_US-lessac-medium.onnx -o /workspace/voices/en_US-lessac-medium.onnx && \
    curl -L https://github.com/rhasspy/piper/releases/download/v0.0.2/en_US-lessac-medium.onnx.json -o /workspace/voices/en_US-lessac-medium.onnx.json

# Copy and install python dependencies
COPY requirements.txt /workspace/
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . /workspace/

# Expose port
EXPOSE 8000

# Set entry point command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
