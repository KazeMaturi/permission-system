#!/usr/bin/env bash
# 云端账号数据同步脚本（"区分口"核心）：把账号数据变更应用到指定环境的数据库。
# 在 PythonAnywhere 的 Bash console 中运行。
#
# 用法：
#   bash sync_cloud_db.sh test     # 应用到【对外测试库】permission_test.db
#   bash sync_cloud_db.sh prod     # 应用到【生产库】permission.db
#
# 设计要点（避免直接上线）：
#   1. 必须显式传入 test 或 prod，无参数/错误参数直接退出；
#   2. 执行前强制二次确认（输入环境名回车确认），防止误触生产；
#   3. 数据变更以 data/patches/*.sql 形式进 git（可审阅、可回滚），本脚本按顺序幂等应用；
#   4. 若目录下存在 permission_upload.db（经 PA Files 上传的整库快照），可选择整库落地。
#
# 依赖：python3（PA 自带）。需先 git pull 确保补丁为最新。
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/permission-system}"
PATCH_DIR="$PROJECT_DIR/data/patches"

# ---- 1. 参数校验（区分口第一道闸）----
TARGET="${1:-}"
case "$TARGET" in
  test) DB_FILE="permission_test.db" ;;
  prod) DB_FILE="permission.db" ;;
  *)
    echo "用法： bash sync_cloud_db.sh <test|prod>" >&2
    echo "  test -> 对外测试库 permission_test.db" >&2
    echo "  prod -> 生产库 permission.db（请谨慎）" >&2
    exit 1 ;;
esac

DB_PATH="$PROJECT_DIR/$DB_FILE"
if [ ! -f "$DB_PATH" ]; then
  echo "错误：目标数据库不存在：$DB_PATH" >&2
  echo "      请先初始化该环境数据库，例如从生产库复制一份：" >&2
  echo "      cp permission.db permission_test.db" >&2
  exit 1
fi

# ---- 2. 二次确认（区分口第二道闸，防误触生产）----
echo "**********************************************"
echo " 即将把账号数据变更应用到【$TARGET】环境"
echo " 目标库：$DB_PATH"
echo "**********************************************"
read -r -p "请输入环境名 ($TARGET) 以确认，其他输入将取消： " CONFIRM
if [ "$CONFIRM" != "$TARGET" ]; then
  echo "已取消。"
  exit 0
fi

# ---- 3. 应用 git 跟踪的 SQL 补丁（幂等、可审阅）----
if [ -d "$PATCH_DIR" ]; then
  echo "==> 应用 data/patches 中的补丁（按文件名排序）"
  for f in $(ls "$PATCH_DIR"/*.sql 2>/dev/null | sort); do
    echo "    -> 应用 $(basename "$f")"
    python3 - "$DB_PATH" "$f" <<'PY'
import sys, sqlite3
db, sql = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(db, timeout=30)
try:
    conn.executescript(open(sql, encoding="utf-8").read())
    conn.commit()
finally:
    conn.close()
PY
  done
else
  echo "（无 data/patches 目录，跳过 SQL 补丁）"
fi

# ---- 4. 可选：整库快照落地 ----
if [ -f "$PROJECT_DIR/permission_upload.db" ]; then
  echo "==> 检测到 permission_upload.db（整库快照）"
  read -r -p "是否用上传的整库覆盖【$TARGET】库？(yes/no) " OVER
  if [ "$OVER" = "yes" ]; then
    cp "$PROJECT_DIR/permission_upload.db" "$DB_PATH"
    echo "    已用上传快照覆盖 $DB_PATH"
  fi
fi

echo "==> 数据同步完成。若需对外生效请 Reload Web app（sync_cloud.sh 已含 Reload）。"
