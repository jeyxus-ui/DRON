FROM python:3.11-slim
WORKDIR /app

# ── Dependencias del sistema ─────────────────────────────────
RUN apt-get update && apt-get install -y \
    git cmake build-essential \
    libusb-1.0-0-dev libssl-dev \
    libglfw3-dev libgl1-mesa-dev \
    libglu1-mesa-dev libgtk-3-dev \
    libglib2.0-0 libgl1 \
    pkg-config udev \
    && rm -rf /var/lib/apt/lists/*

# ── Compilar librealsense + wrapper Python ───────────────────
RUN git clone https://github.com/IntelRealSense/librealsense.git /librealsense

RUN cd /librealsense && \
    mkdir build && cd build && \
    cmake .. \
      -DBUILD_PYTHON_BINDINGS=ON \
      -DPYTHON_EXECUTABLE=$(which python3) \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_EXAMPLES=OFF && \
    make -j4 && \
    make install && \
    ldconfig && \
    rm -rf /librealsense

# ── Dependencias Python del proyecto ────────────────────────
COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── Código fuente ────────────────────────────────────────────
COPY . .

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
