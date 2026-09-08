#!/usr/bin/env bash
# 启动线上测试版权限系统。
# 后台常驻： nohup ./start.sh > server.log 2>&1 &
# 或交给 systemd / supervisor 守护。
set -e
cd "$(dirname "$0")"
PORT="${PORT:-8000}"
echo "启动权限系统，监听 0.0.0.0:$PORT ..."
exec python3 app.py
