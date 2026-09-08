#!/usr/bin/env bash
# ============================================================================
#  权限统计与考核系统 —— 一键生产部署脚本（Debian/Ubuntu/CentOS）
#  作用：部署到 /opt/permission-system，注册 systemd 守护，前置 nginx 反代 + HTTPS。
#  用法：
#     sudo ./install.sh                                  # 交互式输入域名
#     sudo ./install.sh your.domain.com                  # 指定域名（自动签发 HTTPS）
#     sudo ./install.sh your.domain.com --no-ssl         # 仅 HTTP（无证书，内网/临时测试用）
#  说明：
#     - 应用进程仅监听 127.0.0.1:PORT（由本脚本写死），外部只能通过 nginx 的 80/443 访问，8000 端口不暴露公网。
#     - 运行账户 www-data 需对 permission.db 与 data/ 有写权限（WAL 需写库）。
# ============================================================================
set -euo pipefail

APP_USER="www-data"
APP_DIR="/opt/permission-system"
PORT="${PORT:-8000}"
DOMAIN=""
NO_SSL=0

# ---- 解析参数 ----
for a in "$@"; do
  case "$a" in
    --no-ssl) NO_SSL=1 ;;
    -*) echo "未知参数: $a" >&2; exit 1 ;;
    *) DOMAIN="$a" ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 root 运行： sudo $0" >&2; exit 1
fi

# 若在本目录运行，则把当前目录作为部署目录
if [ -f "./app.py" ]; then
  SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
else
  SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
fi

echo "==> 部署目录: $SRC_DIR"

# ---- 包管理器 ----
if command -v apt-get >/dev/null 2>&1; then
  PKG="apt"; INSTALL="apt-get install -y"
elif command -v dnf >/dev/null 2>&1; then
  PKG="dnf"; INSTALL="dnf install -y"
elif command -v yum >/dev/null 2>&1; then
  PKG="yum"; INSTALL="yum install -y"
else
  echo "未识别的包管理器，请手动安装 python3 / nginx / certbot" >&2; exit 1
fi

# ---- 依赖 ----
echo "==> 安装依赖 (python3, nginx, certbot)…"
if [ "$PKG" = "apt" ]; then
  apt-get update -y
  DEBIAN_FRONTEND=noninteractive $INSTALL python3 python3-venv nginx certbot python3-certbot-nginx ufw
else
  $INSTALL python3 nginx certbot
fi

# ---- 复制/就位代码 ----
echo "==> 部署代码到 $APP_DIR …"
mkdir -p "$APP_DIR"
cp -r "$SRC_DIR"/. "$APP_DIR"/ 2>/dev/null || true
# 不复制开发态产物
rm -f "$APP_DIR"/server.log "$APP_DIR"/*.bak_20* 2>/dev/null || true
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
# 保证库与数据目录可写
chmod 664 "$APP_DIR"/permission.db 2>/dev/null || true
chmod -R u+rwX,g+rwX,o-rwx "$APP_DIR"/data 2>/dev/null || true
touch "$APP_DIR"/permission.db-wal "$APP_DIR"/permission.db-shm 2>/dev/null || true
chown "$APP_USER":"$APP_USER" "$APP_DIR"/permission.db* 2>/dev/null || true

# ---- systemd 服务（仅监听 127.0.0.1）----
echo "==> 注册 systemd 服务…"
cat > /etc/systemd/system/permission.service <<EOF
[Unit]
Description=Permission System (考核/权限统计)
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment=PORT=$PORT
Environment=HOST=127.0.0.1
ExecStart=/usr/bin/python3 $APP_DIR/app.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now permission.service
sleep 2
if systemctl is-active --quiet permission.service; then
  echo "    ✓ 服务已启动 (127.0.0.1:$PORT)"
else
  echo "    ✗ 服务启动失败，查看: journalctl -u permission -n 50" >&2
  exit 1
fi

# ---- nginx ----
echo "==> 配置 nginx 反代…"
NGINX_AVAILABLE="/etc/nginx/sites-available/permission"
NGINX_ENABLED="/etc/nginx/sites-enabled/permission"
[ -d /etc/nginx/conf.d ] && NGINX_AVAILABLE="/etc/nginx/conf.d/permission.conf" && NGINX_ENABLED="$NGINX_AVAILABLE"

if [ -z "$DOMAIN" ]; then
  read -r -p "请输入对外域名（如 perm.example.com，留空则用 _ 占位）: " DOMAIN
fi

if [ -n "$DOMAIN" ]; then
  cat > "$NGINX_AVAILABLE" <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    client_max_body_size 20m;
    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
    }
}
EOF
  if [ "$NGINX_AVAILABLE" != "$NGINX_ENABLED" ]; then
    ln -sf "$NGINX_AVAILABLE" "$NGINX_ENABLED"
  fi
  nginx -t && systemctl reload nginx
fi

# ---- HTTPS ----
if [ "$NO_SSL" -eq 0 ] && [ -n "$DOMAIN" ]; then
  echo "==> 通过 certbot 签发 HTTPS 并强制跳转 443…"
  if command -v certbot >/dev/null 2>&1; then
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN" --redirect || \
      echo "    ⚠ certbot 失败（域名解析/80端口未就绪？），可稍后手动运行: certbot --nginx -d $DOMAIN"
  fi
fi

# ---- 防火墙：只暴露 80/443 ----
if command -v ufw >/dev/null 2>&1; then
  echo "==> 配置 ufw（仅放行 80/443）…"
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw --force enable || true
fi

echo ""
echo "=========================================================="
echo "部署完成。"
echo "  应用监听: 127.0.0.1:$PORT (仅本机，nginx 反代后对外)"
echo "  访问地址: ${DOMAIN:+https://$DOMAIN}  (无域名则 http://服务器IP，需手动放行进站 80)"
echo "  日志查看: journalctl -u permission -f"
echo "  重启服务: systemctl restart permission"
echo "=========================================================="
