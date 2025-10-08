FROM python:3.11-slim

# Instala dependências do sistema necessárias para OpenCV, PyAV/FFmpeg e build
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential \
    ffmpeg \
    pkg-config \
    libsm6 \
    libxext6 \
    libavformat-dev \
    libavdevice-dev \
    libavcodec-dev \
    libavutil-dev \
    libswscale-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia apenas o requirements primeiro para aproveitar cache de camada
COPY requirements.docker.txt ./requirements.docker.txt

# Atualiza pip e instala dependências (inclui streamlit-webrtc e pyav)
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.docker.txt

# Copia o restante do projeto
COPY . /app

EXPOSE 8501

ENV STREAMLIT_SERVER_HEADLESS=true

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
