#!/bin/bash
set -e

if ! command -v sqlcmd >/dev/null 2>&1; then
  apt-get update
  ACCEPT_EULA=Y apt-get install -y curl gnupg unixodbc unixodbc-dev
  curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
  curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list > /etc/apt/sources.list.d/mssql-release.list
  apt-get update
  ACCEPT_EULA=Y apt-get install -y msodbcsql18 mssql-tools18
fi

chmod +x startup.sh
exec gunicorn app:app --bind=0.0.0.0:${PORT:-8000} --timeout 120
