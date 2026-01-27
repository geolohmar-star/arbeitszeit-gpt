#!/usr/bin/env bash
set -o errexit

# System-Pakete für ReportLab
apt-get update
apt-get install -y libpangocairo-1.0-0 libpango-1.0-0 libcairo2

# Python Packages
pip install -r requirements.txt

# Django Setup
python manage.py collectstatic --no-input
python manage.py migrate