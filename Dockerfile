FROM python:3.11-slim

# WeasyPrint System-Dependencies installieren
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    libcairo2 \
    libgobject-2.0-0 \
    libharfbuzz0b \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code kopieren
COPY . .

# Django Setup
RUN python manage.py collectstatic --no-input
RUN python manage.py migrate

# Port
ENV PORT=8000
EXPOSE 8000

# Start
CMD gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 2 --worker-tmp-dir /dev/shm --timeout 120 --graceful-timeout 30 --env LANG=de_DE.UTF-8 --env LC_ALL=de_DE.UTF-8