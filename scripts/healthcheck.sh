#!/usr/bin/env bash
# =============================================================================
# 基础健康检查脚本（供 CI / 远端发布后调用）
# 用法：bash scripts/healthcheck.sh <URL> [retries] [interval]
# 判定：首页返回 200 且 /api/accounts 返回含 "rows" 的合法 JSON
# 退出码：0=健康 1=不健康
# =============================================================================
set -uo pipefail
URL="${1:-${DEPLOY_URL:-http://127.0.0.1:8000}}"
RETRIES="${2:-${HEALTH_RETRIES:-15}}"
INTERVAL="${3:-${HEALTH_INTERVAL:-4}}"
PY="${PYTHON:-python3}"

for i in $(seq 1 "$RETRIES"); do
  if curl -fsS "$URL/" -o /dev/null 2>/dev/null && \
     curl -fsS "$URL/api/accounts" 2>/dev/null | "$PY" -c "import sys,json;assert 'rows' in json.load(sys.stdin)" 2>/dev/null; then
    echo "OK   $URL (try $i)"
    exit 0
  fi
  echo "..   $URL 未就绪 (try $i/$RETRIES)"
  sleep "$INTERVAL"
done
echo "FAIL $URL"
exit 1
