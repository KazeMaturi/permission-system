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

# 括号是标记，不是名字的一部分
MARKER_LIFECYCLE = {"（非蝌蚪）": "退出", "（评审权待恢复）": "待复权", "（待确认）": "待确认"}
# 仅普通评审 / 普通评审 / 初审 = 初审账号（无所属分类组）
INITIAL_MARKERS = {"仅普通评审", "普通评审", "初审"}

def strip_marker(name):
    for suf, lc in MARKER_LIFECYCLE.items():
        if name.endswith(suf):
            return name[: -len(suf)], lc
    return name, None

def parse_doc(csv_path):
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = list(csv.reader(f))
    cats = [c.strip() for c in reader[2]]
    perms, lifecycles, initial = {}, {}, {}
    for i, row in enumerate(reader):
        if i < 3:
            continue
        raw = (row[0] or "").strip()
        if not raw:
            continue
        acct, lc = strip_marker(raw)
        marked = set()
        is_chu = False
        for j, v in enumerate(row):
            vv = (v or "").strip()
            if vv in INITIAL_MARKERS:
                is_chu = True
            if vv in ("〇", "○", "o", "O", "●"):
                cat = cats[j] if j < len(cats) else ""
                if cat:
                    marked.add(cat)
        perms[acct] = marked
        if lc:
            lifecycles[acct] = lc
        if is_chu:
            initial[acct] = True
    return perms, lifecycles, initial

def main(dry_run=True):
    doc, lifecycles, initial = parse_doc(CSV_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 当前数据库中的有效权限
    db_rows = cur.execute("SELECT id, account_id, category FROM permission WHERE recycled=0").fetchall()
    db_perms = {}
    for r in db_rows:
        db_perms.setdefault(r["account_id"], []).append((r["id"], r["category"]))

    changes = []
    # 1. 删除空 category（导入异常产生的重复空信息；初审的空分类为合法，不删）
    empty_ids = [r["id"] for r in db_rows if not (r["category"] or "").strip() and r["level"] != "初审"]
    if empty_ids:
        changes.append(("delete_empty", len(empty_ids), empty_ids[:5]))
        if not dry_run:
            cur.execute("DELETE FROM permission WHERE id IN (%s)" % ",".join(map(str, empty_ids)))

    # 为每个文档账号准备期望集合（doc_acct 已剥标记 → 干净名）
    for doc_acct, expected in sorted(doc.items()):
        db_acct = doc_acct
        if db_acct not in db_perms:
            # 数据库中无对应账号，跳过
            continue
        # 同步生命周期标记（非蝌蚪→退出等）
        if doc_acct in lifecycles:
            changes.append(("lifecycle", db_acct, lifecycles[doc_acct]))
            if not dry_run:
                cur.execute("UPDATE account SET lifecycle=?, status=? WHERE account_id=?", (lifecycles[doc_acct], lifecycles[doc_acct], db_acct))

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

    # 2. 初审（仅普通评审）去重保护：每账号仅保留一条 category 为空的初审记录
    chu = cur.execute(
        "SELECT account_id, MIN(id) keep_id FROM permission WHERE level='初审' AND (category IS NULL OR category='') GROUP BY account_id"
    ).fetchall()
    for d in chu:
        n = cur.execute(
            "DELETE FROM permission WHERE account_id=? AND level='初审' AND (category IS NULL OR category='') AND id<>?",
            (d["account_id"], d["keep_id"]),
        ).rowcount
        if n:
            changes.append(("dedup_初审", d["account_id"], "removed", n))

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
