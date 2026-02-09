FROM python:3.12-slim

# System aktualisieren und WeasyPrint Dependencies installieren
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    libcairo2 \
    libglib2.0-0 \
    libharfbuzz0b \
    fonts-dejavu-core \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code kopieren
COPY . .

# Port
ENV PORT=8000
EXPOSE 8000

# Start mit Migration - OPTIMIERT für 8 vCPU / 8 GB RAM
CMD python manage.py migrate && python manage.py collectstatic --no-input && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --threads 2 --worker-class sync --max-requests 1000 --max-requests-jitter 50 --worker-tmp-dir /dev/shm --timeout 3600 --graceful-timeout 900 --keep-alive 5 --env LANG=de_DE.UTF-8 --env LC_ALL=de_DE.UTF-8