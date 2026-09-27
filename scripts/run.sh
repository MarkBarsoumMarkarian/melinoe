#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8787}"

if curl --silent --fail "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
    printf 'Melinoë is already running at http://127.0.0.1:%s\n' "$PORT"
    exit 0
fi

if command -v ss >/dev/null 2>&1 \
    && ss --no-header --listening --tcp "sport = :${PORT}" | grep -q .; then
    printf 'Port %s is occupied by another application.\n' "$PORT" >&2
    printf 'Run ./scripts/run.sh 8788 to use a different port.\n' >&2
    exit 1
fi

cd "$PROJECT_DIR"
uv sync --extra dev --locked

if [[ ! -f "$PROJECT_DIR/src/melinoe/web/index.html" ]]; then
    cd "$PROJECT_DIR/ui"
    pnpm install --frozen-lockfile
    pnpm build
    cd "$PROJECT_DIR"
fi

printf 'Opening Melinoë at http://127.0.0.1:%s\n' "$PORT"
exec uv run melinoe serve --host 127.0.0.1 --port "$PORT"
