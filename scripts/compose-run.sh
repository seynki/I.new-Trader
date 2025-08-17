#!/usr/bin/env bash
set -e

# Ensure docker compose is available
if ! command -v docker &> /dev/null; then
  echo "Docker não encontrado. Instale Docker Desktop/Engine."
  exit 1
fi

# Bring up services
export COMPOSE_PROJECT_NAME=typeia
docker compose up --build
