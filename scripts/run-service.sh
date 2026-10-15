#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in member|safety|notification) service="$1";; *) echo "Usage: $0 member|safety|notification"; exit 2;; esac
exec .venv/bin/python scripts/run_service.py "$service"
