web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 2 --worker-tmp-dir /dev/shm --timeout 120 --graceful-timeout 30 --env LANG=de_DE.UTF-8 --env LC_ALL=de_DE.UTF-8
