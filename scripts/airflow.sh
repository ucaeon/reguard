#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose --env-file .env -f orchestration/airflow/compose.yml)
case "${1:-status}" in
  up)
    .venv/bin/python scripts/prepare_airflow.py
    "${compose[@]}" build
    "${compose[@]}" up -d metadata
    "${compose[@]}" run --rm permissions
    "${compose[@]}" run --rm init
    "${compose[@]}" up -d api-server scheduler dag-processor spark
    ;;
  stop) "${compose[@]}" stop api-server scheduler dag-processor spark ;;
  status) "${compose[@]}" ps ;;
  *) echo 'Usage: bash scripts/airflow.sh {up|stop|status}'; exit 2 ;;
esac
