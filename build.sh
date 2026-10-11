#!/usr/bin/env bash
# Render build step: install, collect static files, migrate, seed Lagos, create the admin.
set -o errexit
pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py bootstrap
