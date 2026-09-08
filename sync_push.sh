#!/usr/bin/env bash
# 本地端一键推送脚本：将当前改动提交并推送到 GitHub（云端再跑 sync_cloud.sh 生效）
# 用法： bash sync_push.sh "本次改动说明"
set -euo pipefail

cd "$(dirname "$0")"   # 切换到脚本所在目录（permission-system 仓库根）

MSG="${1:-更新}"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"

echo "==> 添加所有改动"
git add -A

if git diff --cached --quiet; then
  echo "==> 没有需要提交的改动，跳过"
  exit 0
fi

echo "==> 提交： $MSG"
git commit -m "$MSG"

echo "==> 推送到 origin/$BRANCH"
git push origin "$BRANCH"

echo "==> 已推送。到 PythonAnywhere 的 Bash console 执行： bash sync_cloud.sh"
