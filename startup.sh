#!/bin/bash 

export ACCEPT_EULA=Y 

apt-get update 

apt-get install -y --no-install-recommends \
unixodbc \
unixodbc-dev \
msodbcsql18

python -m pip install --upgrade pip
pip install -r requirements.txt

gunicorn main:app --bind=0.0.0.0:${PORT:-8000} --timeout 60