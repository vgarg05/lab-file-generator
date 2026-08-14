# ── Base image ────────────────────────────────────────────────
FROM python:3.12-slim

# ── System dependencies ───────────────────────────────────────
# GCC/G++ for C/C++, Java, Node.js for JS, Rust
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    default-jdk \
    nodejs \
    npm \
    curl \
    wget \
    gnupg \
    # Playwright/Chromium system libraries
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# ── Install Rust ──────────────────────────────────────────────
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# ── Set working directory ─────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies ───────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Install Playwright Chromium browser ───────────────────────
RUN python -m playwright install chromium

# ── Copy project files ────────────────────────────────────────
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# ── Hugging Face Spaces requires port 7860 ───────────────────
EXPOSE 7860

# ── Start the FastAPI server ──────────────────────────────────
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
