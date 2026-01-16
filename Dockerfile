# FROM python:3.12-slim

# ENV DEBIAN_FRONTEND=noninteractive
# ENV PYTHONUNBUFFERED=1
# ENV DATA_DIR=/data

# # Outils
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     ffmpeg \
#     imagemagick \
#     libreoffice \
#     ghostscript \
#     qpdf \
#     poppler-utils \
#     tesseract-ocr \
#     ocrmypdf \
#     && rm -rf /var/lib/apt/lists/*

# WORKDIR /file_converter_app
# COPY main.py /file_converter_app/main.py

# RUN pip install --no-cache-dir \
#     "huggingface_hub==0.24.7" \
#     "gradio==4.44.1"


# EXPOSE 7000
# CMD ["python", "main.py"]


FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg imagemagick libreoffice ghostscript qpdf poppler-utils tesseract-ocr ocrmypdf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# deps python (pin)
RUN pip install --upgrade pip

RUN pip install --no-cache-dir \
    "huggingface_hub==0.24.7" \
    "gradio==4.44.1" \
    "gradio-client==1.3.0" \
    "fastapi==0.112.2" \
    "pydantic==2.8.2"

# Optionnel: outils dev
RUN pip install --no-cache-dir watchdog

EXPOSE 7000
CMD ["sleep", "infinity"]