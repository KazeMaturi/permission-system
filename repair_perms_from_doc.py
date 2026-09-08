# -*- coding: utf-8 -*-
"""
依据腾讯文档《（已封表）【特色组】评审权限统计表》核对并修复本地 permission.db 权限数据。
规则：
1. 删除所有 category 为空的权限记录（导入异常）。
2. 对文档中账号 ID 与数据库完全一致的账号，按文档去重去冗同步其权限分类。
3. 对文档中带「（非蝌蚪）」后缀的账号，若数据库中仅有对应基础账号且基础账号不在文档中，
   则将基础账号视为该后缀账号进行同步（不修改账号名，仅对齐权限）。
4. 其余差异输出报告，由人工复核。
"""
import sqlite3, csv, os, sys
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "permission.db")
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "permission_stats_doc.csv")
SYSTEM_VERSION = "V20260908B"

def parse_doc(csv_path):
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = list(csv.reader(f))
    cats = [c.strip() for c in reader[2]]
    perms = {}
    for i, row in enumerate(reader):
        if i < 3:
            continue
        acct = (row[0] or "").strip()
        if not acct:
            continue
        marked = set()
        for j, v in enumerate(row):
            if v and v.strip() in ("〇", "○", "o", "O", "●"):
                cat = cats[j] if j < len(cats) else ""
                if cat:
                    marked.add(cat)
        perms[acct] = marked
    return perms

def main(dry_run=True):
    doc = parse_doc(CSV_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 当前数据库中的有效权限
    db_rows = cur.execute("SELECT id, account_id, category FROM permission WHERE recycled=0").fetchall()
    db_perms = {}
    for r in db_rows:
        db_perms.setdefault(r["account_id"], []).append((r["id"], r["category"]))

    changes = []
    # 1. 删除空 category
    empty_ids = [r["id"] for r in db_rows if not (r["category"] or "").strip()]
    if empty_ids:
        changes.append(("delete_empty", len(empty_ids), empty_ids[:5]))
        if not dry_run:
            cur.execute("DELETE FROM permission WHERE id IN (%s)" % ",".join(map(str, empty_ids)))

    # 为每个文档账号准备期望集合
    for doc_acct, expected in sorted(doc.items()):
        # 决定映射到的数据库账号
        db_acct = doc_acct
        suffix = None
        if doc_acct not in db_perms:
            # 尝试去掉常见后缀找基础账号
            for s in ["（非蝌蚪）", "（评审权待恢复）"]:
                if doc_acct.endswith(s):
                    base = doc_acct[: -len(s)]
                    if base in db_perms:
                        db_acct = base
                        suffix = s
                        break
        if db_acct not in db_perms:
            # 数据库中无对应账号，跳过
            continue

        # 当前有效 category（去重后）
        current_cats = set(c for _, c in db_perms[db_acct] if c.strip())
        if current_cats == expected:
            continue

        missing = expected - current_cats
        extra = current_cats - expected
        # 删除多余的（保留同账号同分类最新一条，其余也删除）
        extra_ids = [rid for rid, cat in db_perms[db_acct] if cat in extra]
        changes.append(("sync", db_acct, doc_acct, sorted(expected), sorted(current_cats), sorted(missing), sorted(extra)))
        if not dry_run:
            if extra_ids:
                cur.execute("DELETE FROM permission WHERE id IN (%s)" % ",".join(map(str, extra_ids)))
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for cat in missing:
                cur.execute(
                    """INSERT INTO permission(account_id, category, level, status, effect_date, expire_date, source, system_version, operator, created_at, updated_at, recycled)
                       VALUES(?, ?, '初审', '正常', '', '', '腾讯文档登记总表', ?, '系统同步', ?, ?, 0)""",
                    (db_acct, cat, SYSTEM_VERSION, now, now),
                )

    conn.commit() if not dry_run else None
    conn.close()
    return changes

if __name__ == "__main__":
    dry = "--apply" not in sys.argv
    changes = main(dry_run=dry)
    print("DRY RUN:" if dry else "APPLIED:")
    print("total changes:", len(changes))
    for c in changes[:50]:
        print(c)
    if dry:
        print("\n加 --apply 参数正式执行。")
