#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
LOG_DIR="$ROOT/.local"
API_LOG="$LOG_DIR/ci-api.log"
API_PID=""

cleanup() {
  if [[ -n "$API_PID" ]]; then
    pkill -TERM -P "$API_PID" 2>/dev/null || true
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if ! command -v docker >/dev/null 2>&1; then
  echo "需要 Docker 启动本地 PostgreSQL" >&2
  exit 1
fi

echo "==> 启动 PostgreSQL"
docker compose -f "$ROOT/compose.yaml" up -d --wait postgres

export NODEPASS_DATABASE_URL="${NODEPASS_DATABASE_URL:-postgresql+psycopg://nodepass:nodepass-local-only@127.0.0.1:55432/nodepass}"
export NODEPASS_TEST_DATABASE_URL="${NODEPASS_TEST_DATABASE_URL:-postgresql://nodepass:nodepass-local-only@127.0.0.1:55432/postgres}"
export NODEPASS_COOKIE_SECURE=false
export NODEPASS_ENVIRONMENT=development
export NODEPASS_WEB_ORIGINS='["http://localhost:5173","http://127.0.0.1:5173"]'
export NODEPASS_SESSION_SECRET="${NODEPASS_SESSION_SECRET:-$(openssl rand -hex 32)}"

echo "==> 安装后端依赖"
cd "$BACKEND"
uv sync --locked

export NODEPASS_CREDENTIALS_KEY="${NODEPASS_CREDENTIALS_KEY:-$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')}"

echo "==> 后端检查"
uv run ruff check .
uv run ruff format --check .
uv run alembic upgrade head
uv run pytest -q
uv run alembic check

echo "==> 前端检查"
cd "$FRONTEND"
pnpm install --frozen-lockfile
pnpm build

if [[ "${RUN_E2E:-1}" == "0" ]]; then
  echo "==> 跳过 e2e（RUN_E2E=0）"
  exit 0
fi

mkdir -p "$LOG_DIR"
if curl -fsS http://127.0.0.1:8000/health/ready >/dev/null 2>&1; then
  echo "8000 端口已有后端在运行，请先停止后再执行 e2e" >&2
  exit 1
fi

echo "==> 启动 API 供 e2e 使用"
cd "$BACKEND"
uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 >"$API_LOG" 2>&1 &
API_PID=$!

echo "==> 等待 API"
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/health/ready >/dev/null; then
    break
  fi
  sleep 1
done
if ! curl -fsS http://127.0.0.1:8000/health/ready >/dev/null; then
  echo "API 未就绪，日志：" >&2
  cat "$API_LOG" >&2
  exit 1
fi

echo "==> 安装 Playwright Chromium（已安装时跳过）"
cd "$FRONTEND"
pnpm exec playwright install chromium

echo "==> 运行 e2e"
pnpm test:e2e
