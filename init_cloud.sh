#!/usr/bin/env bash
# 云端一次性初始化脚本：在 PythonAnywhere 的 Bash console 运行【仅一次】
# 作用：把现有 zip 部署目录备份 → git clone 最新代码 → 把云端真实数据库搬回 → 可选自动 Reload
# 用法：
#   bash init_cloud.sh
#   私有仓库 / 想自动 Reload： GITHUB_TOKEN=xxx PA_API_TOKEN=yyy bash init_cloud.sh
#
# 说明：permission.db 是 git 忽略文件，clone 下来没有它；本脚本把它从旧目录搬回，云端数据不丢失。
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/permission-system}"
PA_USER="${PA_USER:-KazeMaturi}"
PA_DOMAIN="${PA_DOMAIN:-${PA_USER}.pythonanywhere.com}"
PA_API_TOKEN="${PA_API_TOKEN:-}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

if [ -n "$GITHUB_TOKEN" ]; then
  CLONE_URL="https://${GITHUB_TOKEN}@github.com/KazeMaturi/permission-system.git"
else
  CLONE_URL="https://github.com/KazeMaturi/permission-system.git"
fi

echo "==> 云端一次性初始化开始： $PROJECT_DIR"

TMPDB=""
if [ -d "$PROJECT_DIR" ]; then
  OLD="$PROJECT_DIR.old.$(date +%Y%m%d%H%M%S)"
  echo "==> 备份现有目录为 $OLD"
  mv "$PROJECT_DIR" "$OLD"
  if [ -f "$OLD/permission.db" ]; then
    TMPDB="$(mktemp)"
    cp "$OLD/permission.db" "$TMPDB"
    echo "==> 已暂存现有数据库"
  fi
else
  echo "==> 当前无 $PROJECT_DIR，直接克隆"
fi

echo "==> git clone 最新代码"
git clone "$CLONE_URL" "$PROJECT_DIR"

if [ -n "$TMPDB" ] && [ -f "$TMPDB" ]; then
  echo "==> 把云端真实数据库搬回新目录"
  cp "$TMPDB" "$PROJECT_DIR/permission.db"
  rm -f "$TMPDB"
fi

echo "==> 完成。请确认 PA 的 WSGI 配置文件指向 $PROJECT_DIR/wsgi.py（首次 zip 部署时已设好，通常无需改动）。"

if [ -n "$PA_API_TOKEN" ]; then
  echo "==> 自动 Reload： $PA_DOMAIN"
  curl -s -X POST \
    -H "Authorization: Token $PA_API_TOKEN" \
    "https://www.pythonanywhere.com/api/v0/user/$PA_USER/webapps/$PA_DOMAIN/reload/"
  echo
  echo "==> 稍候访问 https://$PA_DOMAIN"
else
  echo "==> 未设 PA_API_TOKEN，请到 Web 页手动点 Reload 使改动生效。"
fi

echo "==> 以后日常同步：本地 bash sync_push.sh \"说明\"；云端 bash sync_cloud.sh"
