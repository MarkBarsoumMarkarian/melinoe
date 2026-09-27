#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_DIR"
uv sync --extra dev --locked
uv run ruff format --check src tests
uv run ruff check src tests
uv run pytest
uv run melinoe system >/dev/null

if [[ "${MELINOE_SKIP_SANDBOX_INTEGRATION:-0}" == "1" ]]; then
  printf 'Live sandbox integration skipped: hosted runner cannot configure loopback in a network namespace.\n'
else
  SANDBOX_PROBE="$(mktemp -d)"
  trap 'rm -rf "$SANDBOX_PROBE"' EXIT
  uv run melinoe isolate "$SANDBOX_PROBE" -- /bin/sh -c 'printf isolated > sandbox-proof.txt'
  test "$(cat "$SANDBOX_PROBE/sandbox-proof.txt")" = "isolated"
  uv run melinoe ledger verify "$SANDBOX_PROBE/.melinoe/ledger.jsonl" >/dev/null
fi

cd "$PROJECT_DIR/ui"
pnpm install --frozen-lockfile
pnpm build

cd "$PROJECT_DIR"
uv build --clear

printf 'Melinoë verification passed.\n'
