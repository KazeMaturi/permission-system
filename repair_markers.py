# -*- coding: utf-8 -*-
"""
清洗「账号名（标记）」数据：括号是标记，不是名字的一部分。
规则（依据用户澄清）：
- 非蝌蚪 = 已退出 → lifecycle=退出
- 评审权待恢复 = 待复权 → lifecycle=待复权
- 待确认不登记 → 不入库（保持现状，本脚本不动）
- 仅普通评审 = 初审，无所属分类组
处理：
1. account 表新增 lifecycle 列（默认正常），回填 = status。
2. 剥离 account_id 的括号标记 → 干净名：
   - 若干净名已存在（重复基础账号）：把括号版的所有子表记录并入干净版，删除括号版账号，干净版 lifecycle 设为标记对应值。
   - 若干净名不存在：括号版改名为干净名，lifecycle 设为标记对应值。
3. 跨所有含 account_id 的表迁移记录（account/permission/assess_record 等）。
4. 初审（level=初审 且 category 为空）按 account_id 去重，每账号仅保留一条。
加 --apply 参数正式执行；默认 dry-run。
"""
import sqlite3, os, sys

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "permission.db")
MARKERS = {"（非蝌蚪）": "退出", "（评审权待恢复）": "待复权"}

def main(dry_run=True):
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    cur = con.cursor()
    changes = []

    # 1. 新增 lifecycle 列
    try:
        cur.execute("ALTER TABLE account ADD COLUMN lifecycle TEXT DEFAULT '正常'")
        changes.append(("add_column", "account.lifecycle"))
    except Exception as e:
        changes.append(("col_exists", str(e)))
    # 回填 lifecycle = status（无条件，确保 ALTER 的 DEFAULT 不掩盖历史值）
    cur.execute("UPDATE account SET lifecycle=COALESCE(status,'正常')")

    # 收集所有含 account_id 的表
    tables = [r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    child_tables = []
    for t in tables:
        cols = [c["name"] for c in con.execute(f"PRAGMA table_info('{t}')")]
        if "account_id" in cols and t != "account":
            child_tables.append(t)

    # 2. 括号账号
    bracketed = cur.execute("SELECT account_id, status FROM account WHERE account_id LIKE '%（%' ORDER BY account_id").fetchall()
    for r in bracketed:
        full = r["account_id"]
        clean, lifecycle = full, (r["status"] or "正常")
        for suf, lc in MARKERS.items():
            if full.endswith(suf):
                clean = full[: -len(suf)]
                lifecycle = lc
                break
        twin = cur.execute("SELECT account_id FROM account WHERE account_id=?", (clean,)).fetchone()
        if twin and twin["account_id"] != full:
            # 合并：子表账户全迁到干净版，删括号版
            for t in child_tables:
                n = cur.execute(f"UPDATE {t} SET account_id=? WHERE account_id=?", (clean, full)).rowcount
                if n: changes.append(("move_child", t, full, clean, n))
            cur.execute("UPDATE account SET lifecycle=?, status=? WHERE account_id=?", (lifecycle, lifecycle, clean))
            cur.execute("DELETE FROM account WHERE account_id=?", (full,))
            changes.append(("merge_delete", full, clean, lifecycle))
        else:
            for t in child_tables:
                n = cur.execute(f"UPDATE {t} SET account_id=? WHERE account_id=?", (clean, full)).rowcount
                if n: changes.append(("rename_child", t, full, clean, n))
            cur.execute("UPDATE account SET account_id=?, lifecycle=?, status=? WHERE account_id=?", (clean, lifecycle, lifecycle, full))
            changes.append(("rename", full, clean, lifecycle))

    # 3. 初审空记录去重（每账号仅一条 category 为空）
    dups = cur.execute(
        "SELECT account_id, MIN(id) keep_id FROM permission WHERE level='初审' AND (category IS NULL OR category='') GROUP BY account_id"
    ).fetchall()
    for d in dups:
        n = cur.execute(
            "DELETE FROM permission WHERE account_id=? AND level='初审' AND (category IS NULL OR category='') AND id<>?",
            (d["account_id"], d["keep_id"]),
        ).rowcount
        if n: changes.append(("dedup_初审", d["account_id"], "removed", n))

    # 4. 复核：仍残留括号
    remain = cur.execute("SELECT account_id FROM account WHERE account_id LIKE '%（%'").fetchall()
    if remain:
        changes.append(("REMAIN_BRACKETED", [x["account_id"] for x in remain]))

    if not dry_run:
        con.commit()
    con.close()
    return changes

if __name__ == "__main__":
    dry = "--apply" not in sys.argv
    ch = main(dry_run=dry)
    print("DRY RUN:" if dry else "APPLIED:")
    for c in ch:
        print(" ", c)
    if dry:
        print("\n加 --apply 参数正式执行。")
