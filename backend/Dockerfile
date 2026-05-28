FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# Install Chromium system deps manually (Debian Bookworm package names)
# then install Python deps and the browser binary separately — avoids
# playwright --with-deps trying to install ttf-unifont/ttf-ubuntu-font-family
# which don't exist in Debian Bookworm.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdbus-1-3 libdrm2 libgbm1 libxcb1 libxkbcommon0 libx11-6 \
    libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 \
    libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 libwayland-client0 \
    fonts-liberation fonts-unifont fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
