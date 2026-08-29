#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd "${script_dir}/.." && pwd)"
api_log="${TMPDIR:-/tmp}/ace-pitch-api.log"
web_log="${TMPDIR:-/tmp}/ace-pitch-web.log"
api_pid=""
web_pid=""

cleanup() {
  if [[ -n "${web_pid}" ]]; then
    kill "${web_pid}" 2>/dev/null || true
  fi
  if [[ -n "${api_pid}" ]]; then
    kill "${api_pid}" 2>/dev/null || true
  fi
  wait "${web_pid}" 2>/dev/null || true
  wait "${api_pid}" 2>/dev/null || true
}

stop_demo() {
  trap - EXIT
  cleanup
  echo
  echo "Pitch demo stopped cleanly."
  exit 0
}

trap cleanup EXIT
trap stop_demo INT TERM

cd "${repository_root}"

echo "Building the pitch interface..."
npm --prefix apps/web run build

echo "Starting the verified development-artifact runtime..."
ACE_MODEL_MODE=development_artifact \
ACE_CORS_ORIGINS=http://127.0.0.1:3000 \
PYTHONPATH=services/api \
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >"${api_log}" 2>&1 &
api_pid=$!

echo "Starting the production web interface..."
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 \
npm --prefix apps/web run start -- --hostname 127.0.0.1 --port 3000 >"${web_log}" 2>&1 &
web_pid=$!

for _ in $(seq 1 90); do
  if ! kill -0 "${api_pid}" 2>/dev/null; then
    echo "API startup failed. See ${api_log}." >&2
    tail -n 30 "${api_log}" >&2
    exit 1
  fi
  if ! kill -0 "${web_pid}" 2>/dev/null; then
    echo "Web startup failed. See ${web_log}." >&2
    tail -n 30 "${web_log}" >&2
    exit 1
  fi
  if curl --silent --fail --max-time 1 http://127.0.0.1:8000/v1/runtime/status >/dev/null \
    && curl --silent --fail --max-time 1 http://127.0.0.1:3000 >/dev/null; then
    break
  fi
  sleep 1
done

runtime_status="$(curl --silent --fail --max-time 5 http://127.0.0.1:8000/v1/runtime/status)"
if ! curl --silent --fail --max-time 5 http://127.0.0.1:3000 >/dev/null; then
  echo "Pitch demo did not become ready. API log: ${api_log}; web log: ${web_log}." >&2
  exit 1
fi

echo
echo "ACE Mandate Assurance is ready: http://127.0.0.1:3000"
echo "Runtime contract: ${runtime_status}"
echo "Press Ctrl+C to stop both services."

while kill -0 "${api_pid}" 2>/dev/null && kill -0 "${web_pid}" 2>/dev/null; do
  sleep 1
done

echo "A pitch service stopped unexpectedly. API log: ${api_log}; web log: ${web_log}." >&2
exit 1
