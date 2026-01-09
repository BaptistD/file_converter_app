FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data

# Outils
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    libreoffice \
    ghostscript \
    qpdf \
    poppler-utils \
    tesseract-ocr \
    ocrmypdf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py /app/app.py

RUN pip install --no-cache-dir gradio==4.*

EXPOSE 8080
CMD ["python", "app.py"]