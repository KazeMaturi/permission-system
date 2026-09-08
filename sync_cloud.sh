#!/usr/bin/env bash
# 云端端一键同步脚本：在 PythonAnywhere 的 Bash console 中运行
# 作用：拉取 GitHub 最新代码；若设置了 PA_API_TOKEN 则自动触发 Web app Reload
# 用法：
#   仅拉取：                bash sync_cloud.sh
#   拉取并自动 Reload：      PA_API_TOKEN=你的PA_API令牌 bash sync_cloud.sh
#
# 说明：permission.db 是 git 忽略的未跟踪文件，git pull 不会动它，云端真实数据始终安全。
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/permission-system}"
PA_USER="${PA_USER:-KazeMaturi}"            # 改成你的 PythonAnywhere 用户名
PA_DOMAIN="${PA_DOMAIN:-${PA_USER}.pythonanywhere.com}"
PA_API_TOKEN="${PA_API_TOKEN:-}"           # 留空则仅拉取，需手动 Reload

if [ ! -d "$PROJECT_DIR/.git" ]; then
  echo "错误： $PROJECT_DIR 不是 git 仓库。请先按『云端一次性初始化』步骤 git clone 后再用本脚本。" >&2
  exit 1
fi

cd "$PROJECT_DIR"

echo "==> 拉取最新代码（快进合并）"
git pull --ff-only

echo "==> 同步完成。permission.db 为未跟踪文件，已原样保留。"

if [ -n "$PA_API_TOKEN" ]; then
  echo "==> 调用 PythonAnywhere API 自动 Reload： $PA_DOMAIN"
  curl -s -X POST \
    -H "Authorization: Token $PA_API_TOKEN" \
    "https://www.pythonanywhere.com/api/v0/user/$PA_USER/webapps/$PA_DOMAIN/reload/"
  echo
  echo "==> 已触发 Reload，稍候数秒即可访问 https://$PA_DOMAIN"
else
  echo "==> 未设置 PA_API_TOKEN，请到 Web 页手动点 Reload 使改动生效。"
  echo "    获取 PA API Token： Dashboard → Account → API token"
fi
