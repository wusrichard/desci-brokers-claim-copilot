#!/bin/sh
set -eu

cd "$(dirname "$0")"

if [ ! -x .venv-backend/bin/python ]; then
  python3 -m venv .venv-backend
  .venv-backend/bin/python -m pip install -r backend/requirements.txt
fi

.venv-backend/bin/python -m backend.provision_vlei_demo
.venv-backend/bin/python -m backend.seed
exec .venv-backend/bin/python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000
