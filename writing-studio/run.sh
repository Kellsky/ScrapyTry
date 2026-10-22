#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m uvicorn app:app --host "${WRITING_STUDIO_HOST:-127.0.0.1}" --port "${WRITING_STUDIO_PORT:-8000}"
