#!/usr/bin/env bash
# =============================================================================
# 权限系统 · 自动化部署脚本（幂等、可重复执行）
# 流程：自动拉取最新代码 → 构建校验（编译/语法检查，不改业务代码）→ 启动服务 → 基础健康检查 → 失败告警
# 模式：
#   local-test  本地验证模式：在独立端口启动并自检（不触碰生产端口 8000）
#   render      Render 模式：拉取/构建校验后，由 Render Blueprint 接管发布，仅做发布后健康检查
# 不破坏现有系统：local-test 使用独立端口与独立 pid 文件；render 由平台隔离运行。
# =============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ---- 可配置环境变量（CI / 命令行均可覆盖）--------------------------------
DEPLOY_MODE="${DEPLOY_MODE:-local-test}"
PORT="${PORT:-9099}"
HOST="${HOST:-127.0.0.1}"
DEPLOY_URL="${DEPLOY_URL:-http://$HOST:$PORT}"
ALERT_WEBHOOK="${ALERT_WEBHOOK:-}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-4}"
PY="${PYTHON:-python3}"

log()  { echo "[$(date '+%F %T')] $*"; }
die()  { alert "$1"; exit 1; }
alert(){
  local msg="$1"
  log "ALERT: $msg"
  if [ -n "$ALERT_WEBHOOK" ]; then
    curl -fsS -X POST "$ALERT_WEBHOOK" -H 'Content-Type: application/json' \
      -d "{\"text\":\"[权限系统部署告警] $msg\"}" || log "（webhook 不可达，告警未发出）"
  fi
}

# ---------------------------------------------------------------------------
# 步骤 1/4：自动拉取最新代码（无 remote 时跳过，避免本地仓库误报失败）
# ---------------------------------------------------------------------------
log "步骤1/4 自动拉取最新代码…"
if [ -d .git ] && git remote 2>/dev/null | grep -q .; then
  git pull --ff-only || die "git pull 失败，请检查仓库状态/冲突"
else
  log "（无 git remote，跳过拉取 — 使用当前工作区代码）"
fi

# ---------------------------------------------------------------------------
# 步骤 2/4：构建校验（仅做编译/语法检查，不修改任何业务代码）
# ---------------------------------------------------------------------------
log "步骤2/4 构建校验…"
"$PY" -m py_compile app.py || die "Python 编译失败：app.py 存在语法错误"
if command -v node >/dev/null 2>&1; then
  node --check static/app.js || die "前端语法检查失败：static/app.js"
else
  log "（未检测到 node，跳过前端语法检查）"
fi
log "构建校验通过"

# ---------------------------------------------------------------------------
# 步骤 3/4：启动服务
# ---------------------------------------------------------------------------
log "步骤3/4 启动服务（模式=$DEPLOY_MODE）…"
if [ "$DEPLOY_MODE" = "local-test" ]; then
  # 先清理上一次 local-test 实例（仅限本脚本自己记录的 pid），保证可重复执行
  if [ -f .deploy.pid ]; then
    OLD=$(cat .deploy.pid 2>/dev/null || true)
    if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then kill "$OLD" 2>/dev/null || true; fi
    rm -f .deploy.pid
  fi
  PORT="$PORT" HOST="$HOST" nohup "$PY" app.py > deploy_runtime.log 2>&1 &
  echo $! > .deploy.pid
  log "本地测试服务已启动 PID=$(cat .deploy.pid) → http://$HOST:$PORT"
elif [ "$DEPLOY_MODE" = "render" ]; then
  log "Render 由 Blueprint 在 git push 后自动拉取/构建/启动；此处仅做发布后健康检查"
else
  die "未知 DEPLOY_MODE=$DEPLOY_MODE（应为 local-test 或 render）"
fi

# ---------------------------------------------------------------------------
# 步骤 4/4：基础健康检查（HTTP 200 + /api/accounts 返回合法 JSON）
# 容错：免费套餐 Render 重启后库可能为空，故只校验接口可用，不校验数据条数
# ---------------------------------------------------------------------------
log "步骤4/4 健康检查（目标 $DEPLOY_URL）…"
# 启动宽限：冷启动需完成迁移+索引创建，先给 3 秒再开始轮询
sleep 3
ok=0
for i in $(seq 1 "$HEALTH_RETRIES"); do
  if curl -fsS "$DEPLOY_URL/" -o /dev/null 2>/dev/null && \
     curl -fsS "$DEPLOY_URL/api/accounts" 2>/dev/null | "$PY" -c "import sys,json;d=json.load(sys.stdin);assert 'rows' in d" 2>/dev/null; then
    ok=1; break
  fi
  sleep "$HEALTH_INTERVAL"
done

if [ "$ok" -eq 1 ]; then
  log "✅ 部署成功，系统可访问：$DEPLOY_URL"
  echo "$DEPLOY_URL" > .deploy.url
  exit 0
else
  die "健康检查失败：服务在 $DEPLOY_URL 未就绪（详见 deploy_runtime.log）"
fi
