# -*- coding: utf-8 -*-
"""
处理文档中带后缀的账号与数据库中基础账号的对应关系：
- （非蝌蚪）：将数据库中的基础账号重命名为带后缀的账号（各表 account_id 联动更新）。
- （评审权待恢复）：不改名，仅将账号状态与权限状态改为「待复权」。
- ceshi2 为测试账号且文档无权限，删除其权限记录。
"""
import sqlite3, os, sys

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "permission.db")

RENAME_MAP = {
    "knox1006": "knox1006（非蝌蚪）",
    "唯一的明帝": "唯一的明帝（非蝌蚪）",
    "小新533": "小新533（非蝌蚪）",
    "长安梦客": "长安梦客（非蝌蚪）",
    "放着我来147": "放着我来147（评审权待恢复）",
}

PENDING_RECOVER = []
TEST_DELETE_PERM = ["ceshi2"]

TABLES_WITH_ACCOUNT_ID = [
    "permission", "assess_record", "change_log", "assess_exemption", "upgrade_apply",
    "category_expand", "official_list_legacy", "leader_record", "assess_category_detail",
    "violation_record", "appeal_record", "spot_check", "reinstate_apply", "account_capability",
    "official_task_member", "message_recipient", "upgrade_apply_eval", "eval_role_assign",
    "category_expand_eval", "login_log", "password_reset_request",
]

def main(dry_run=True):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    changes = []

    # 1. 删除测试账号的孤立权限
    for acct in TEST_DELETE_PERM:
        ids = [r[0] for r in cur.execute("SELECT id FROM permission WHERE account_id=? AND recycled=0", (acct,)).fetchall()]
        if ids:
            changes.append(("delete_test_perm", acct, len(ids)))
            if not dry_run:
                cur.execute("DELETE FROM permission WHERE id IN (%s)" % ",".join(map(str, ids)))

    # 2. 重命名非蝌蚪账号
    for old, new in RENAME_MAP.items():
        exists = cur.execute("SELECT 1 FROM account WHERE account_id=?", (old,)).fetchone()
        if not exists:
            continue
        new_exists = cur.execute("SELECT 1 FROM account WHERE account_id=?", (new,)).fetchone()
        if new_exists:
            changes.append(("skip_rename_target_exists", old, new))
            continue
        changes.append(("rename", old, new))
        if not dry_run:
            for tbl in TABLES_WITH_ACCOUNT_ID:
                try:
                    cur.execute("UPDATE %s SET account_id=? WHERE account_id=?" % tbl, (new, old))
                except sqlite3.OperationalError:
                    pass  # 表无该列
            cur.execute("UPDATE account SET account_id=? WHERE account_id=?", (new, old))

    # 3. 评审权待恢复：账号状态与有效权限状态改为待复权
    for acct in PENDING_RECOVER:
        arow = cur.execute("SELECT status FROM account WHERE account_id=?", (acct,)).fetchone()
        if not arow:
            continue
        changes.append(("pending_recover", acct))
        if not dry_run:
            if arow["status"] in ("正常", "考核期"):
                cur.execute("UPDATE account SET status='待复权' WHERE account_id=?", (acct,))
            cur.execute("UPDATE permission SET status='待复权' WHERE account_id=? AND recycled=0 AND status IN ('正常','考核期')", (acct,))

    if not dry_run:
        conn.commit()
    conn.close()
    return changes

if __name__ == "__main__":
    # 已弃用：此脚本会把括号标记并入 account_id，会造成重复账号（已被 repair_markers.py 纠正）。
    # 仅保留 --legacy 以兼容历史回放，默认拒绝执行以免重新污染数据。
    if "--legacy" not in sys.argv:
        print("⚠️ 已弃用：括号是标记不是名字，请用 repair_markers.py 做数据清洗。")
        print("如需强制运行旧逻辑，加 --legacy 参数。")
        raise SystemExit(0)
    dry = "--apply" not in sys.argv
    changes = main(dry_run=dry)
    print("DRY RUN:" if dry else "APPLIED:")
    for c in changes:
        print(c)
    if dry:
        print("\n加 --apply 参数正式执行。")
