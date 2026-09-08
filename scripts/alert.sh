#!/usr/bin/env bash
# =============================================================================
# 失败告警脚本（供 CI / 部署失败时调用）
# 用法：bash scripts/alert.sh "告警内容"
# 行为：打印到日志；若设置了 ALERT_WEBHOOK（Slack/Discord/飞书 通用入站 webhook），
#       则额外 POST 一条 JSON 消息。未配置 webhook 时仅本地提示，不报错退出。
# =============================================================================
set -uo pipefail
msg="${1:-部署失败（无详细信息）}"
echo "[$(date '+%F %T')] ALERT: $msg"
if [ -n "${ALERT_WEBHOOK:-}" ]; then
  curl -fsS -X POST "$ALERT_WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "{\"text\":\"[权限系统部署告警] $msg\"}" \
    || echo "（webhook 不可达，告警未发出）"
fi
