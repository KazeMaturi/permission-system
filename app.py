# -*- coding: utf-8 -*-
"""
百科任务评审团 · 特色初优方向权限统计与考核系统
后端：Python 标准库 http.server + sqlite3（零第三方依赖）
启动：python app.py  然后浏览器打开 http://127.0.0.1:8000
制度依据：《百科任务评审团「特色/初优」方向评审权限申请与考核制度》V20260904B
"""
import json
import os
import re
import sqlite3
import random
import csv
import datetime
import hashlib
import secrets
import urllib.parse
import email.utils
import email
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_PATH = os.path.join(BASE_DIR, "permission.db")

SYSTEM_VERSION = "V20260904B"

# 枚举口径
LEVELS = ["初审", "中审", "高审"]
LEVEL_RANK = {"初审": 1, "中审": 2, "高审": 3}
PERM_STATUSES = ["正常", "考核期", "见习", "实习", "待复权", "停审", "降级", "已回收", "休眠", "退出", "永封"]
ACCOUNT_LEVELS = ["待转正", "初审", "中审", "高审"]
ACCOUNT_STATUSES = ["正常", "考核期", "见习", "实习", "待复权", "停审", "降级", "已回收", "退出", "永封"]
ACTIVE_PERM = {"正常", "考核期", "见习", "实习", "待复权"}
# 账号状态是否视为“正常有效”
ACTIVE_ACCT = {"正常", "考核期", "见习", "实习", "待复权"}
# 违规等级与严重等级口径
VIOLATION_LEVELS = ["轻微问题", "一般违规", "严重违规", "重大违规"]
SEVERE_LEVELS = ("严重违规", "重大违规")
# 违规导致的权限挂起状态（取自 PERM_STATUSES）
SUSPEND_STATUS = "停审"
# 处分措施枚举（制度 6.x / 7.x）
PENALTY_TYPES = ["警告", "停审", "降级", "取消权限", "永久封禁"]
# 带期限、到期可自动恢复的处分（其余为终态或仅警示）
PENALTY_TERMED = ("停审", "降级")
# 新评审报名：报名条件选项（二选一）
REG_CONDITIONS = [
    "近6个月累计编辑通过版本≥500个",
    "进阶难度任务累计达标≥100个",
]
# 新评审报名评估流程节点（升级中审增加「已公示」节点：3 人全部提交后进入公示，负责人确认发布后进入评估完成）
EVAL_NODES = ["资格待核查", "待授权", "已授权", "待转正评估", "已公示", "评估完成"]
# 新评审报名评估结果
EVAL_RESULTS = ["待评估", "不通过", "通过转正", "实习"]
# 评审三类角色（身份绑定 / 不可跨权）：与升级中审多人评估模态中的角色一致
EVAL_REVIEW_ROLES = ["分类小组长", "所属大团队质量组长", "评审相关负责人"]
# 截图上传目录
SCREENSHOT_DIR = os.path.join(DATA_DIR, "screenshots")

# ---------- 登录 / 会话 / 权限分级 ----------
PW_SALT = "pcs2026#salt"
# 会话：token -> {account_id, expires}；内存态，重启即失效（轻量内部系统可接受）
SESSIONS = {}
SESSION_TTL = 3600 * 8  # 8 小时
# 分组扩充审核权限：仅 分类组长/质量组长/评审委员会成员 中“在任”者具备审核资格
REVIEWER_ROLES = {"分类组长", "质量组长", "评审委员会成员"}
REVIEWER_STATUSES = {"在任"}
# 管理类写操作（台账/账号/指标/组长委员会/申请等）要求 leader_record 在任且属于管理角色
ADMIN_ROLES = {"评审委员会成员", "团队负责人", "质量组长"}
# 管理员管理页可设置的扩展角色：特色小组长（绑定二级组；不计入系统管理能力 has_cap 口径）
EXTRA_ADMIN_ROLE = "特色小组长"
ALL_ADMIN_ROLES = ADMIN_ROLES | {EXTRA_ADMIN_ROLE}
# 需要绑定管辖范围的管理角色：团队负责人/质量组长 → 大团队(domain)；特色小组长 → 二级组(group_name)
SCOPED_ADMIN_ROLES = {"团队负责人": "大团队", "质量组长": "大团队", "特色小组长": "二级组"}
# 见习期（天）：中审新取得分类权限先见习，期满无严重违规转正
PROBATION_DAYS = 30
# 登录失败提示（仅统计，不锁定账号，避免他人恶意操作导致用户无法使用）
LOGIN_FAILS = {}          # account_id -> [fail_count, last_fail_ts]
LOGIN_FAIL_WINDOW = 600   # 秒：窗口内累计
def _login_fail_count(account_id):
    rec = LOGIN_FAILS.get(account_id)
    if not rec: return 0
    if (datetime.datetime.now().timestamp() - rec[1]) >= LOGIN_FAIL_WINDOW:
        LOGIN_FAILS.pop(account_id, None)
        return 0
    return rec[0]
def _login_fail(account_id):
    rec = LOGIN_FAILS.get(account_id)
    now = datetime.datetime.now().timestamp()
    if not rec or (now - rec[1]) >= LOGIN_FAIL_WINDOW:
        LOGIN_FAILS[account_id] = [1, now]
    else:
        LOGIN_FAILS[account_id] = [rec[0] + 1, now]
def _login_ok(account_id):
    LOGIN_FAILS.pop(account_id, None)
def hash_pw(pw):
    return hashlib.sha256((PW_SALT + (pw or "")).encode("utf-8")).hexdigest()
def default_pw(account_id):
    return hash_pw(account_id + "@2026")
def gen_token():
    return secrets.token_hex(18)
def session_get(token):
    s = SESSIONS.get(token)
    if not s: return None
    if s["expires"] < datetime.datetime.now().timestamp():
        SESSIONS.pop(token, None); return None
    return s["account_id"]
def login_account(conn, account_id, password):
    r = conn.execute("SELECT * FROM account WHERE account_id=?", (account_id.strip(),)).fetchone()
    if not r: return None
    stored = r["password"] or ""
    # 账户尚无密码时，按默认规则 account_id@2026 校验
    if not stored:
        return r if password == (account_id.strip() + "@2026") else None
    # 已设密码（含默认初始化散列）：校验传入密码的散列
    return r if stored == hash_pw(password) else None
def is_reviewer(conn, account_id):
    if not account_id: return False
    return bool(conn.execute(
        "SELECT 1 FROM leader_record WHERE account_id=? AND role IN (%s) AND status IN (%s) LIMIT 1"
        % (",".join("?"*len(REVIEWER_ROLES)), ",".join("?"*len(REVIEWER_STATUSES))),
        (account_id,) + tuple(REVIEWER_ROLES) + tuple(REVIEWER_STATUSES)).fetchone())

def is_admin(conn, account_id):
    """管理角色：在任的 评审委员会成员 / 团队负责人 / 质量组长。"""
    if not account_id: return False
    return bool(conn.execute(
        "SELECT 1 FROM leader_record WHERE account_id=? AND role IN (%s) AND status IN (%s) LIMIT 1"
        % (",".join("?"*len(ADMIN_ROLES)), ",".join("?"*len(REVIEWER_STATUSES))),
        (account_id,) + tuple(ADMIN_ROLES) + tuple(REVIEWER_STATUSES)).fetchone())

def is_senior(conn, account_id):
    """高审账号：账号等级为 高审。仅高审可登记违规。"""
    if not account_id: return False
    r = conn.execute("SELECT level FROM account WHERE account_id=?", (account_id,)).fetchone()
    return bool(r) and (r["level"] or "") == "高审"

# 超级管理员（系统最高权限）：默认 Adzwlqxm；可为其余账号设置/取消管理员身份。
# 高于 is_admin，仅在必要时（授权管理）使用的精英账号集合。
SUPER_ADMIN_ACCOUNTS = {"Adzwlqxm"}
def is_super_admin(conn, account_id):
    return bool(account_id) and account_id in SUPER_ADMIN_ACCOUNTS

def get_eval_roles(conn, account_id):
    """返回账号在 eval_role_assign 中绑定的评审角色列表；超级管理员额外隐含「评审相关负责人」权限。"""
    if not account_id:
        return []
    rows = conn.execute("SELECT DISTINCT role FROM eval_role_assign WHERE account_id=?", (account_id,)).fetchall()
    roles = [r["role"] for r in rows if r["role"] in EVAL_REVIEW_ROLES]
    if is_super_admin(conn, account_id) and "评审相关负责人" not in roles:
        roles.append("评审相关负责人")
    return roles


# ---------- 站内信箱（内部消息系统） ----------
# 消息类型：system=系统消息（全局配置类，面向全体） / push=单独推送（定向通知）
MSG_TYPES = {"system": "系统消息", "push": "单独推送"}
# 发布范围：all=全体成员 / user=指定账号（可多个） / group=用户组（群体）
MSG_SCOPES = {"all": "全体成员", "user": "指定账号（可多个）", "group": "用户组 / 群体"}
# 群体维度（动态推导，不落冗余表）
MSG_GROUP_KINDS = {"level": "账号等级", "status": "账号状态", "category": "评审分类", "role": "职务角色"}
ROLE_GROUPS = ["分类组长", "质量组长", "评审委员会成员", "团队负责人"]
# 考核类自动触发规则（source=auto）
AUTO_RULES = {"assess_result": "考核成绩公布", "assess_notice": "月度考核通知", "pwd_reset": "密码恢复申请提醒"}


def list_msg_groups(conn):
    """推导可选用户组/群体：账号等级、账号状态、评审分类（有效权限持有者）、职务角色（在任）。"""
    out = []
    for lv in ACCOUNT_LEVELS:
        n = conn.execute("SELECT COUNT(*) FROM account WHERE level=?", (lv,)).fetchone()[0]
        out.append(dict(key="level:%s" % lv, name="等级 · %s" % lv, kind="level", count=n))
    for st in ["正常", "考核期", "见习", "实习"]:
        n = conn.execute("SELECT COUNT(*) FROM account WHERE status=?", (st,)).fetchone()[0]
        out.append(dict(key="status:%s" % st, name="状态 · %s" % st, kind="status", count=n))
    for (cat,) in conn.execute("SELECT DISTINCT category FROM permission WHERE recycled=0 AND category<>'' ORDER BY category").fetchall():
        n = conn.execute("SELECT COUNT(DISTINCT account_id) FROM permission WHERE category=? AND recycled=0 AND status IN (%s)"
                         % ",".join("?" * len(ACTIVE_PERM)), (cat,) + tuple(ACTIVE_PERM)).fetchone()[0]
        out.append(dict(key="category:%s" % cat, name="分类 · %s" % cat, kind="category", count=n))
    for role in ROLE_GROUPS:
        n = conn.execute("SELECT COUNT(DISTINCT account_id) FROM leader_record WHERE role=? AND status='在任'", (role,)).fetchone()[0]
        out.append(dict(key="role:%s" % role, name="职务 · %s（在任）" % role, kind="role", count=n))
    return out


def _split_targets(raw):
    """把逗号/分号/换行分隔的目标串解析为去重列表。"""
    seen, out = set(), []
    for p in re.split(r"[,，;；\s]+", (raw or "").strip()):
        p = p.strip()
        if p and p not in seen:
            seen.add(p); out.append(p)
    return out


def _accounts_of_group(conn, key):
    """按群体 key（如 level:中审 / category:影视 / role:分类组长）返回账号列表。"""
    if ":" not in key: return []
    kind, val = key.split(":", 1)
    if kind == "level":
        return [r[0] for r in conn.execute("SELECT account_id FROM account WHERE level=? ORDER BY account_id", (val,)).fetchall()]
    if kind == "status":
        return [r[0] for r in conn.execute("SELECT account_id FROM account WHERE status=? ORDER BY account_id", (val,)).fetchall()]
    if kind == "category":
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT account_id FROM permission WHERE category=? AND recycled=0 AND status IN (%s) ORDER BY account_id"
            % ",".join("?" * len(ACTIVE_PERM)), (val,) + tuple(ACTIVE_PERM)).fetchall()]
    if kind == "role":
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT account_id FROM leader_record WHERE role=? AND status='在任' ORDER BY account_id", (val,)).fetchall()]
    return []


def resolve_scope_accounts(conn, scope_type, scope_target):
    """把发布范围解析为接收人账号列表。返回 (accounts, error)。"""
    scope_type = scope_type or "all"
    target = (scope_target or "").strip()
    if scope_type == "all":
        return [r[0] for r in conn.execute("SELECT account_id FROM account ORDER BY account_id").fetchall()], None
    if scope_type == "user":
        if not target: return [], "指定账号不能为空"
        accts = _split_targets(target)
        miss = [a for a in accts if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (a,)).fetchone()]
        if miss: return [], "账号不存在：" + "、".join(miss)
        return accts, None
    if scope_type == "group":
        if not target: return [], "用户组不能为空"
        accounts, seen = [], set()
        for k in _split_targets(target):
            for a in _accounts_of_group(conn, k):
                if a not in seen:
                    seen.add(a); accounts.append(a)
        if not accounts: return [], "用户组无匹配成员：" + target
        return accounts, None
    return [], "发布范围非法：" + scope_type


def create_message(conn, sender, msg_type, title, body, scope_type, scope_target,
                   source="manual", auto_rule="", accounts=None):
    """写入消息并为每个接收人生成已读状态记录。返回 (dict(id,count,accounts), error)。"""
    title = (title or "").strip()
    if not title: return None, "标题不能为空"
    if msg_type not in MSG_TYPES: return None, "消息类型非法：" + str(msg_type)
    if scope_type not in MSG_SCOPES: return None, "发布范围非法：" + str(scope_type)
    if accounts is None:
        accounts, err = resolve_scope_accounts(conn, scope_type, scope_target)
        if err: return None, err
    if not accounts: return None, "接收人为空，请检查发布范围"
    now = _now()
    cur = conn.execute("""INSERT INTO message(msg_type,title,body,sender,scope_type,scope_target,send_time,source,auto_rule,created_at,updated_at)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                       (msg_type, title, body or "", sender or "", scope_type, scope_target or "",
                        now, source or "manual", auto_rule or "", now, now))
    mid = cur.lastrowid
    for a in accounts:
        conn.execute("INSERT OR IGNORE INTO message_recipient(message_id,account_id,is_read,created_at) VALUES(?,?,0,?)", (mid, a, now))
    conn.commit()
    return dict(id=mid, count=len(accounts), accounts=accounts), None


def auto_send_message(conn, auto_rule, title, body, accounts=None, scope_type="user", scope_target="", msg_type="push"):
    """按预设规则自动触发发送（考核类信息）。source 标记为 auto，auto_rule 记录触发规则。"""
    if auto_rule not in AUTO_RULES: return None, "未定义的自动触发规则：" + str(auto_rule)
    return create_message(conn, "系统自动", msg_type, title, body, scope_type, scope_target,
                          source="auto", auto_rule=auto_rule, accounts=accounts)

def _acct_level(conn, account_id):
    if not account_id: return ""
    r = conn.execute("SELECT level FROM account WHERE account_id=?", (account_id,)).fetchone()
    return (r["level"] or "") if r else ""

def is_junior(conn, account_id):
    """初审及以上：账号等级为 初审 / 中审 / 高审。"""
    return _acct_level(conn, account_id) in ("初审", "中审", "高审")

def is_mid(conn, account_id):
    """中审及以上：账号等级为 中审 / 高审。"""
    return _acct_level(conn, account_id) in ("中审", "高审")

def is_mid_or_reviewer(conn, account_id):
    """中审及以上，或担任分类组长/质量组长/评审委员会成员等评审角色（制度中「中审」包含初审权限）。"""
    return is_mid(conn, account_id) or is_reviewer(conn, account_id)

# 分类 -> 部门 映射（依据《评审权限统计表》表头：大文娱 / 人文历史 两大部门），用于“不得跨权”校验。
DEPT_OF_CATEGORY = {
    # 大文娱 · 影视音综
    "影视": "大文娱", "音乐": "大文娱", "古典音乐人、团体": "大文娱", "西方音乐体裁": "大文娱",
    "节目": "大文娱", "演唱会": "大文娱", "戏剧": "大文娱", "戏曲": "大文娱",
    "戏曲曲艺人物": "大文娱", "相声小品": "大文娱", "奖项": "大文娱", "明星": "大文娱",
    "娱乐人物": "大文娱",
    # 大文娱 · 体育
    "体育项目": "大文娱", "赛事": "大文娱", "运动员": "大文娱", "俱乐部/运动队": "大文娱",
    "武术套路": "大文娱", "电子竞技": "大文娱", "奥运标志": "大文娱", "中国象棋术语": "大文娱",
    # 大文娱 · ACGN
    "游戏": "大文娱", "ACG作品": "大文娱", "ACG角色": "大文娱", "ACG组织": "大文娱",
    "ACG物品": "大文娱", "布袋戏": "大文娱",
    # 人文历史 · 地理
    "行政区划": "人文历史", "景点景观": "人文历史", "历史遗迹": "人文历史", "河流": "人文历史",
    "山脉": "人文历史", "湖泊": "人文历史", "地理标志": "人文历史", "气旋": "人文历史",
    "传统村落": "人文历史", "可移动文物": "人文历史", "天文": "人文历史",
    # 人文历史 · 历史
    "历史人物": "人文历史",
}
def dept_of(category):
    return DEPT_OF_CATEGORY.get((category or "").strip(), "")

def _holds_perm_in_category(conn, account_id, category):
    """该账号是否在指定分类持有有效（非回收/停审/降级）权限——用于“按分类”不跨权校验。"""
    return bool(conn.execute(
        "SELECT 1 FROM permission WHERE account_id=? AND category=? AND status NOT IN ('已回收','停审','降级','休眠') AND recycled=0 LIMIT 1",
        (account_id, category)).fetchone())

def _holds_perm_in_dept(conn, account_id, dept):
    """该账号是否在指定部门（任一分类）持有有效权限——用于“按部门”不跨权校验。"""
    if not dept:
        return False
    cats = [c for c, d in DEPT_OF_CATEGORY.items() if d == dept]
    if not cats:
        return False
    q = "SELECT 1 FROM permission WHERE account_id=? AND category IN (%s) AND status NOT IN ('已回收','停审','降级','休眠') AND recycled=0 LIMIT 1" % ",".join("?"*len(cats))
    return bool(conn.execute(q, (account_id,) + tuple(cats)).fetchone())

# ---- 系统功能权限（能力）注册表 ----
# 每一项是一项“系统功能权限”，对应前端“个人权限主页”的亮/暗展示与“权限梳理”总览。
# 默认（无单独覆盖时）由 base 谓词根据账号等级/角色推导；超级管理员可针对某账号单独开通/撤销（account_capability 覆盖）。
TIERS = ["初审", "中审", "高审", "管理员", "超级管理员"]

CAPS = [
    # 初审：基本提交类权限（任何正式评审员均可）
    dict(key="upgrade_submit", name="提交升级申请", tier="初审", desc="发起本人或所管账号的等级晋升申请", base=is_junior),
    dict(key="category_expand_submit", name="提交扩分类申请", tier="初审", desc="发起新增评审分类的权限申请", base=is_junior),
    dict(key="status_strip_submit", name="提交评审状态处置申请", tier="初审", desc="对在某分类持有有效权限的账号发起评审状态处置申请（目标须在该分类有有效权限）", base=is_junior),
    dict(key="appeal_submit", name="提交申诉", tier="初审", desc="就本人被处罚记录提交申诉", base=is_junior),

    # 中审：在初审基础上，额外拥有审核/质量类权限（中审及以上，或担任评审角色）
    dict(key="assess_cat_detail", name="分类评审量录入", tier="中审", desc="录入考核周期内的分类评审量明细", base=is_mid_or_reviewer),
    dict(key="spot_check", name="抽查记录", tier="中审", desc="登记质量抽查结果", base=is_mid_or_reviewer),
    dict(key="reinstate", name="复权申请", tier="中审", desc="就停审/降级账号提交复权申请", base=is_mid_or_reviewer),
    dict(key="retrain", name="再培训", tier="中审", desc="就待培训账号提交再培训记录", base=is_mid_or_reviewer),
    dict(key="upgrade_review", name="审核升级申请", tier="中审", desc="审核他人等级晋升申请（组长/委员会）", base=is_mid_or_reviewer),
    dict(key="category_expand_review", name="审核扩分类申请", tier="中审", desc="审核他人分类扩充申请（组长/委员会）", base=is_mid_or_reviewer),
    dict(key="strip_approve_catlead", name="处置审批·小组长节点", tier="中审", desc="按分类审批评审状态处置申请（不得跨权，须本分类有效权限）", base=is_mid_or_reviewer),

    # 高审：在中审基础上，额外拥有违规登记等权限
    dict(key="violation_register", name="登记违规", tier="高审", desc="登记账号违规记录（仅高审）", base=is_senior),

    # 管理员：管理角色权限（质量负责人/团队负责人/评审委员会成员）
    dict(key="violation_edit", name="修改违规记录", tier="管理员", desc="修改违规记录内容", base=is_admin),
    dict(key="violation_delete", name="删除违规记录", tier="管理员", desc="删除违规记录", base=is_admin),
    dict(key="system_admin", name="系统管理", tier="管理员", desc="进入系统管理（基础数据/变更日志/数据质量）", base=is_admin),
    dict(key="account_manage", name="账号管理", tier="管理员", desc="维护评审员账号信息", base=is_admin),
    dict(key="perm_manage", name="权限台账管理", tier="管理员", desc="维护评审分类权限台账", base=is_admin),
    dict(key="assess_manage", name="考核管理", tier="管理员", desc="配置与维护评审考核", base=is_admin),
    dict(key="registration_manage", name="报名管理", tier="管理员", desc="审核新报名与入团流程", base=is_admin),
    dict(key="official_list_manage", name="官方名单管理", tier="管理员", desc="维护官方名单", base=is_admin),
    dict(key="leader_manage", name="组长委员会管理", tier="管理员", desc="维护组长/委员会任职", base=is_admin),
    dict(key="underperform_exec", name="不胜任执行", tier="管理员", desc="执行不胜任处理", base=is_admin),
    dict(key="liability_manage", name="推荐人连带责任", tier="管理员", desc="处理推荐人连带责任", base=is_admin),
    dict(key="strip_approve_quality", name="处置审批·质量组长节点", tier="管理员", desc="按部门审批评审状态处置申请（不得跨权，须本部门有效权限）", base=is_admin),

    # 超级管理员：评审负责人层级
    dict(key="admin_grant", name="设置/取消管理员", tier="超级管理员", desc="为其余账号开通/取消管理员身份", base=is_super_admin),
    dict(key="strip_approve_review", name="处置审批·评审负责人节点", tier="超级管理员", desc="以评审负责人身份终批评审状态处置", base=is_super_admin),
    dict(key="capability_manage", name="单独开通/撤销账号权限", tier="超级管理员", desc="为任意账号单独开通或撤销某项系统功能权限", base=is_super_admin),
]
CAPS_MAP = {c["key"]: c for c in CAPS}

def cap_override(conn, account_id, key):
    """返回覆盖值：1=已单独开通，0=已单独撤销，None=未设置（按默认推导）。"""
    if not account_id:
        return None
    r = conn.execute("SELECT granted FROM account_capability WHERE account_id=? AND capability=?", (account_id, key)).fetchone()
    return r["granted"] if r else None

def cap_base(conn, account_id, key):
    c = CAPS_MAP.get(key)
    return bool(c and c["base"](conn, account_id))

def has_cap(conn, account_id, key):
    """账号是否拥有某项系统功能权限：单独覆盖优先，否则按默认推导。"""
    ov = cap_override(conn, account_id, key)
    if ov is not None:
        return bool(ov)
    return cap_base(conn, account_id, key)

def tier_of(conn, account_id):
    if has_cap(conn, account_id, "admin_grant"):
        return "超级管理员"
    if has_cap(conn, account_id, "system_admin"):
        return "管理员"
    if has_cap(conn, account_id, "violation_register"):
        return "高审"
    if has_cap(conn, account_id, "upgrade_review"):
        return "中审"
    if has_cap(conn, account_id, "upgrade_submit"):
        return "初审"
    return "无评审权限"

def capability_stats(conn):
    """统计系统现有权限：各系统功能权限当前持有账号数。"""
    accts = [r["account_id"] for r in conn.execute("SELECT account_id FROM account").fetchall()]
    return {c["key"]: sum(1 for a in accts if has_cap(conn, a, c["key"])) for c in CAPS}

# 升级 / 扩分类 / 官方名单 / 组长委员会 通用 CRUD 元数据
GEN = {
    # 升级中审申请：已重构为与报名一致的工作流（apply_id=百科ID；旧 account_id/from_level/to_level/target_category/status/owner 保留不删）
    "upgrade-applies": dict(t="upgrade_apply", f=["apply_id", "qq", "referrer", "category", "screenshot_path", "note", "operator", "apply_time", "eval_node", "eval_node_time", "eval_result", "eval_result_time", "evaluator"]),
    "category-expands": dict(t="category_expand", f=["apply_id", "qq", "referrer", "category", "screenshot_path", "note", "operator", "apply_time", "eval_node", "eval_node_time", "eval_result", "eval_result_time", "evaluator"]),
    "leader-records": dict(t="leader_record", f=["account_id", "role", "status", "time", "owner", "note", "operator"]),
}
# 升级申请 / 分类扩充 工作流共用表映射（复用同一评估流程，按 kind 区分）
KIND_TBL = {"upgrade": "upgrade_apply", "expand": "category_expand"}
KIND_FEAT = {"upgrade": "upgrade_apply_feature", "expand": "category_expand_feature"}
KIND_EVAL = {"upgrade": "upgrade_apply_eval", "expand": "category_expand_eval"}
# 申请管理当前流程节点（对应 图1 评审报名申请流程）
APPLY_NODES = ["推荐确认", "报名提交", "资格核查", "选择评审等级", "授权激活", "授权与学习", "转正考核实施", "数据导出与抽查", "转正评估", "转正归档"]
# 考核指标默认值（成绩构成 5.4）
DEFAULT_ASSESS = [
    ("版本判定准确率", 30, 95, "ge", "percent", "通过/不通过判定准确率"),
    ("任务达标率", 40, 95, "ge", "percent", "特色/初优词条编辑任务达标率"),
    ("官方任务专项错误率", 20, 5, "le", "percent", "判定错误率≤5%即不通过（必考）"),
    ("反馈语规范性", 10, 0, "count0", "count", "违规数，0为合格"),
]
METRIC_COLS = {
    "版本判定准确率": "v_judgment", "任务达标率": "v_task",
    "官方任务专项错误率": "v_official_err", "反馈语规范性": "v_feedback",
}
# 一票否决项（制度 5.5，共 8 项）
VETO_ITEMS = [
    "放行含广告、色情、暴力、反动及其他违法违规内容的版本",
    "给优化量不足的词条授予初优",
    "越权评审（见1.5）",
    "官方任务判定错误（含未按指定参考资料来源、结构模板评审）",
    "考核期内超额评审、跨任务评审或无故中断",
    "出借、共用、租用账号或代他人评审",
    "通过评审索要、接受好处；泄露官方任务内容或内部要求",
    "反馈语存在明显错误误导编辑者，或多次使用不文明用语",
]
# 再训与复权门槛（制度 6.4）
REINSTATE_RULES = {
    "初审": dict(ver_min=300, ver_max=600, main_min=0, accuracy=95.0, need_prior=False, prior_months=0),
    "中审": dict(ver_min=150, ver_max=300, main_min=30, accuracy=95.0, need_prior=True, prior_months=1),
}
# 复权状态流转
REINSTATE_STATUS = ["待审核", "复权中", "已复权", "已失败"]
# 分类休眠判定（制度 3.8）：近 N 个自然月无评审量（无考核记录）即休眠候选
DORMANT_MONTHS = 2
# 指南大版本迭代复训状态（制度 6.6）
RETRAIN_STATUSES = ["待开展", "进行中", "已完成", "未通过"]
# 连续未达标自动执行（制度 6.1）：确认式降级/取消的动作枚举
UNDERPERFORM_ACTIONS = ["降级", "取消评审权"]
# 蝌蚪身份：拥有 实习/见习 权限的账号视为蝌蚪（制度 5.6/4.4③）
TADPOLE_STATUSES = ("实习", "见习")

def spot_quota(total):
    """制度 7.1 抽查配额：自然月内按总评审版本数的 10% 抽查，主分类占抽样量 60%，副分类合计 40%。
    返回 (应抽总量, 主分类应抽, 副分类应抽)"""
    total = int(total or 0)
    need = -(-total // 10)          # ceil(total * 10%)
    main = -(-(need * 6) // 10)     # ceil(need * 60%)
    return need, main, need - main

# ---------------------------------------------------------------- DB
def get_conn():
    # timeout：写锁争用时等待而非立即抛 "database is locked"
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        # WAL：读不阻塞写、写不阻塞读，避免「有人在导入/审批时其他人全部卡住」
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.Error:
        pass
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS category_dict(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT, group_name TEXT, category TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS account(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT UNIQUE,
        display_name TEXT, level TEXT DEFAULT '中审',
        status TEXT DEFAULT '正常', join_date TEXT, note TEXT,
        is_test INTEGER DEFAULT 0,
        last_login_time TEXT, last_login_ip TEXT, last_login_device TEXT);
    CREATE TABLE IF NOT EXISTS permission(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT, category TEXT,
        level TEXT DEFAULT '中审', status TEXT DEFAULT '正常',
        effect_date TEXT, expire_date TEXT, source TEXT DEFAULT '过渡认定',
        system_version TEXT DEFAULT 'V20260904', operator TEXT,
        created_at TEXT, updated_at TEXT, recycled INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS assess_config(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE, weight REAL DEFAULT 0, pass_line REAL DEFAULT 0,
        direction TEXT DEFAULT 'ge', input_type TEXT DEFAULT 'percent', note TEXT, sort_order INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS assess_record(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT, period TEXT, period_type TEXT DEFAULT '月',
        v_judgment REAL, v_task REAL, v_official_err REAL, v_feedback INTEGER,
        official_versions INTEGER, main_cat_versions INTEGER, feature_edits INTEGER,
        veto INTEGER DEFAULT 0, veto_reason TEXT, note TEXT,
        flow_status TEXT DEFAULT '考核中', reject_reason TEXT, reject_time TEXT,
        operator TEXT, created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS change_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        permission_id INTEGER, account_id TEXT, action TEXT,
        operator TEXT, change_time TEXT, detail TEXT);
    CREATE TABLE IF NOT EXISTS assess_exemption(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT, period TEXT,
        kind TEXT DEFAULT '请假',
        mode TEXT DEFAULT '免考核',
        days REAL DEFAULT 0,
        reduce_ratio REAL DEFAULT 0,
        category TEXT, reason TEXT,
        operator TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS registration(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_type TEXT DEFAULT '新报名',
        apply_level TEXT DEFAULT '初审',
        apply_time TEXT, apply_id TEXT, qq TEXT, referrer TEXT,
        category TEXT, condition_type TEXT, screenshot_path TEXT,
        note TEXT, operator TEXT,
        eval_node TEXT, eval_node_time TEXT,
        eval_result TEXT, eval_result_time TEXT, evaluator TEXT,
        created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS upgrade_apply(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        apply_id TEXT, qq TEXT, referrer TEXT,
        category TEXT,
        screenshot_path TEXT, note TEXT, operator TEXT,
        apply_time TEXT,
        eval_node TEXT DEFAULT '资格待核查',
        eval_node_time TEXT,
        eval_result TEXT DEFAULT '待评估',
        eval_result_time TEXT,
        evaluator TEXT,
        created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS upgrade_apply_feature(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        apply_id INTEGER NOT NULL,
        entry_name TEXT, entry_link TEXT, compliant_time TEXT, note TEXT,
        created_at TEXT);
    CREATE TABLE IF NOT EXISTS upgrade_apply_eval(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        apply_id INTEGER NOT NULL,
        evaluator_role TEXT,
        account_id TEXT,
        agree TEXT,
        reason TEXT,
        eval_time TEXT,
        created_at TEXT);
    CREATE TABLE IF NOT EXISTS category_expand(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        apply_id TEXT, qq TEXT, referrer TEXT,
        category TEXT,
        screenshot_path TEXT, note TEXT, operator TEXT,
        apply_time TEXT,
        eval_node TEXT DEFAULT '资格待核查',
        eval_node_time TEXT,
        eval_result TEXT DEFAULT '待评估',
        eval_result_time TEXT,
        evaluator TEXT,
        created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS category_expand_feature(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        apply_id INTEGER NOT NULL,
        entry_name TEXT, entry_link TEXT, compliant_time TEXT, note TEXT,
        created_at TEXT);
    CREATE TABLE IF NOT EXISTS category_expand_eval(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        apply_id INTEGER NOT NULL,
        evaluator_role TEXT,
        account_id TEXT,
        agree TEXT,
        reason TEXT,
        eval_time TEXT,
        created_at TEXT);
    CREATE TABLE IF NOT EXISTS official_task_package(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_name TEXT, task_id TEXT UNIQUE, creator TEXT,
        owner TEXT, note TEXT, operator TEXT,
        created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS official_task_member(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        package_id INTEGER, account_id TEXT, required_level TEXT DEFAULT '',
        note TEXT, operator TEXT,
        created_at TEXT, updated_at TEXT,
        UNIQUE(package_id, account_id));
    CREATE TABLE IF NOT EXISTS leader_record(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT, role TEXT DEFAULT '分类组长', status TEXT DEFAULT '在任',
        time TEXT, owner TEXT, note TEXT, operator TEXT,
        scope TEXT DEFAULT '',
        created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS login_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT, login_time TEXT, ip TEXT DEFAULT '', device_id TEXT DEFAULT '',
        user_agent TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS password_reset_request(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL, contact TEXT DEFAULT '',
        status TEXT DEFAULT '待处理',
        created_at TEXT, handled_at TEXT, handled_by TEXT, note TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS assess_category_detail(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT, period TEXT, category TEXT,
        versions INTEGER DEFAULT 0,
        UNIQUE(account_id, period, category));
    CREATE TABLE IF NOT EXISTS violation_record(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT, level TEXT DEFAULT '一般违规', reason TEXT, penalty TEXT,
        penalty_time TEXT, referrer TEXT, operator TEXT, note TEXT,
        penalty_term INTEGER DEFAULT 0, penalty_due TEXT, restored_at TEXT,
        created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS appeal_record(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ref_type TEXT, ref_id INTEGER, account_id TEXT, appeal_time TEXT,
        handler TEXT, conclusion TEXT, suspended INTEGER DEFAULT 0, note TEXT,
        created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS referrer_liability(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        violation_id INTEGER, violator_account TEXT, referrer_account TEXT,
        category TEXT, level TEXT, penalty TEXT, status TEXT DEFAULT '待处理',
        handled_by TEXT, handled_time TEXT, note TEXT,
        created_at TEXT, updated_at TEXT,
        UNIQUE(violation_id));
    CREATE TABLE IF NOT EXISTS status_strip_apply(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_account TEXT, category TEXT, department TEXT,
        reason TEXT, status TEXT DEFAULT '待审核',
        applicant TEXT,
        senior_approver TEXT DEFAULT '', cat_lead_approver TEXT DEFAULT '',
        quality_lead_approver TEXT DEFAULT '', review_lead_approver TEXT DEFAULT '',
        source_type TEXT, source_id INTEGER,
        created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS account_capability(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT, capability TEXT,
        granted INTEGER DEFAULT 1, operator TEXT, reason TEXT,
        created_at TEXT, updated_at TEXT,
        UNIQUE(account_id, capability));
    CREATE TABLE IF NOT EXISTS spot_check(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT, account_id TEXT, category TEXT,
        total_versions INTEGER DEFAULT 0,
        sample_need INTEGER DEFAULT 0, main_need INTEGER DEFAULT 0, sub_need INTEGER DEFAULT 0,
        sampled INTEGER DEFAULT 0, problem_versions INTEGER DEFAULT 0,
        level TEXT DEFAULT '', handling TEXT DEFAULT '', is_official INTEGER DEFAULT 0,
        checker TEXT, check_time TEXT, note TEXT,
        operator TEXT, created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS reinstate_apply(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT, category TEXT, target_level TEXT DEFAULT '初审',
        status TEXT DEFAULT '待审核', apply_time TEXT,
        official_versions INTEGER DEFAULT 0, main_cat_versions INTEGER DEFAULT 0,
        accuracy REAL DEFAULT 0, prior_reinstated_at TEXT,
        extend_count INTEGER DEFAULT 0, cancel_count INTEGER DEFAULT 0,
        block_until TEXT, result_time TEXT, owner TEXT, note TEXT,
        operator TEXT, created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS message(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_type TEXT DEFAULT 'system',    -- system=系统消息(全局配置类) / push=单独推送(定向通知)
        title TEXT,
        body TEXT,
        sender TEXT,
        scope_type TEXT DEFAULT 'all',      -- all=全体 / user=指定账号(可多) / group=用户组(群体)
        scope_target TEXT DEFAULT '',        -- 用户组/群体 key 或账号列表(逗号分隔)
        send_time TEXT,                      -- 发送时间(即时即当前)
        source TEXT DEFAULT 'manual',        -- manual=手动发布 / auto=自动触发(考核类)
        auto_rule TEXT DEFAULT '',           -- 自动触发规则标识，如 assess_result/assess_notice
        created_at TEXT,
        updated_at TEXT);
    CREATE TABLE IF NOT EXISTS message_recipient(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER,
        account_id TEXT,
        is_read INTEGER DEFAULT 0,
        read_time TEXT,
        created_at TEXT);
    CREATE TABLE IF NOT EXISTS eval_role_assign(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,                -- 评审角色：分类小组长 / 所属大团队质量组长 / 评审相关负责人
        account_id TEXT NOT NULL,          -- 被绑定的具体人员账号
        category TEXT DEFAULT '',          -- 关联分类（空字符串=适用于全部分类）
        created_at TEXT, updated_at TEXT,
        UNIQUE(role, account_id, category));
    CREATE INDEX IF NOT EXISTS idx_evalrole_role ON eval_role_assign(role);
    CREATE INDEX IF NOT EXISTS idx_evalrole_acct ON eval_role_assign(account_id);
    CREATE INDEX IF NOT EXISTS idx_perm_acct ON permission(account_id);
    CREATE INDEX IF NOT EXISTS idx_exempt ON assess_exemption(account_id, period);
    CREATE INDEX IF NOT EXISTS idx_perm_cat ON permission(category);
    CREATE INDEX IF NOT EXISTS idx_assess_acct ON assess_record(account_id);
    CREATE INDEX IF NOT EXISTS idx_assess_period ON assess_record(period);
    CREATE INDEX IF NOT EXISTS idx_msg_send ON message(send_time);
    CREATE INDEX IF NOT EXISTS idx_msg_source ON message(source, auto_rule);
    CREATE INDEX IF NOT EXISTS idx_msgrec_acct ON message_recipient(account_id, is_read);
    CREATE INDEX IF NOT EXISTS idx_msgrec_msg ON message_recipient(message_id);
    """)
    conn.commit()

    # 迁移：为旧版 status_strip_apply 增加来源关联字段
    for col, typ in [("source_type", "TEXT"), ("source_id", "INTEGER")]:
        try:
            conn.execute("ALTER TABLE status_strip_apply ADD COLUMN %s %s" % (col, typ))
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # 迁移：新评审报名表字段扩展（报名条件/截图/评估节点/评估结果等）
    for col, typ in [("apply_level", "TEXT DEFAULT '初审'"), ("condition_type", "TEXT"), ("screenshot_path", "TEXT"),
                     ("eval_node", "TEXT"), ("eval_node_time", "TEXT"), ("eval_result", "TEXT"),
                     ("eval_result_time", "TEXT"), ("evaluator", "TEXT")]:
        try:
            conn.execute("ALTER TABLE registration ADD COLUMN %s %s" % (col, typ))
            conn.commit()
        except sqlite3.OperationalError:
            pass
    # 历史数据：若原表存在 feature_held/perm_open_time/owner/assess_result 等旧字段，保留但不再使用
    # （评估节点由空或旧 current_node 迁移到新的 eval_node，保持业务连续）
    try:
        conn.execute("UPDATE registration SET eval_node=current_node WHERE eval_node IS NULL AND current_node IS NOT NULL")
        conn.execute("UPDATE registration SET eval_node='资格待核查' WHERE eval_node IS NULL OR eval_node=''")
        conn.execute("UPDATE registration SET eval_result='待评估' WHERE eval_result IS NULL OR eval_result=''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # 迁移：升级中审申请工作流化（字段语义重构）
    for col, typ in [("apply_id", "TEXT"), ("qq", "TEXT"), ("referrer", "TEXT"),
                     ("category", "TEXT"), ("screenshot_path", "TEXT"), ("op_remark", "TEXT"),
                     ("eval_node", "TEXT DEFAULT '资格待核查'"), ("eval_node_time", "TEXT"),
                     ("eval_result", "TEXT DEFAULT '待评估'"), ("eval_result_time", "TEXT"), ("evaluator", "TEXT")]:
        try:
            conn.execute("ALTER TABLE upgrade_apply ADD COLUMN %s %s" % (col, typ))
            conn.commit()
        except sqlite3.OperationalError:
            pass
    for col, typ in [("entry_link", "TEXT"), ("compliant_time", "TEXT")]:
        try:
            conn.execute("ALTER TABLE upgrade_apply_feature ADD COLUMN %s %s" % (col, typ))
            conn.commit()
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute("UPDATE upgrade_apply SET eval_node='资格待核查' WHERE eval_node IS NULL OR eval_node=''")
        conn.execute("UPDATE upgrade_apply SET eval_result='待评估' WHERE eval_result IS NULL OR eval_result=''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # 迁移：分类扩充工作流化（字段语义对齐升级中审申请，复用同一评估流程）
    for col, typ in [("apply_id", "TEXT"), ("qq", "TEXT"), ("referrer", "TEXT"),
                     ("category", "TEXT"), ("screenshot_path", "TEXT"),
                     ("eval_node", "TEXT DEFAULT '资格待核查'"), ("eval_node_time", "TEXT"),
                     ("eval_result", "TEXT DEFAULT '待评估'"), ("eval_result_time", "TEXT"), ("evaluator", "TEXT")]:
        try:
            conn.execute("ALTER TABLE category_expand ADD COLUMN %s %s" % (col, typ))
            conn.commit()
        except sqlite3.OperationalError:
            pass
    try:
        # 旧字段 account_id/add_category/status/owner 语义映射到新工作流字段
        conn.execute("""UPDATE category_expand SET apply_id=COALESCE(NULLIF(apply_id,''), account_id),
                        category=COALESCE(NULLIF(category,''), add_category)
                        WHERE apply_id IS NULL OR apply_id=''""")
        conn.execute("""UPDATE category_expand SET eval_node='评估完成',
                        eval_result=CASE status WHEN '已通过' THEN '通过转正' WHEN '已驳回' THEN '不通过' ELSE '待评估' END,
                        operator=COALESCE(NULLIF(operator,''), owner)
                        WHERE eval_node IS NULL OR eval_node=''""")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # 分类字典
    cat_csv = os.path.join(DATA_DIR, "categories.csv")
    if os.path.exists(cat_csv) and c.execute("SELECT COUNT(*) FROM category_dict").fetchone()[0] == 0:
        with open(cat_csv, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                c.execute("INSERT OR IGNORE INTO category_dict(domain,group_name,category) VALUES(?,?,?)",
                          (row["domain"], row["group_name"], row["category"]))
    # 账号（以文档为准）
    acct_csv = os.path.join(DATA_DIR, "accounts.csv")
    if os.path.exists(acct_csv):
        with open(acct_csv, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                aid = row["account_id"].strip()
                c.execute("""INSERT OR IGNORE INTO account(account_id,display_name,level,status,join_date,note)
                             VALUES(?,?, '中审','正常','2026-09-04','')""", (aid, aid))
    # 权限（以文档 〇 标记为准）
    perm_csv = os.path.join(DATA_DIR, "permissions.csv")
    if os.path.exists(perm_csv) and c.execute("SELECT COUNT(*) FROM permission").fetchone()[0] == 0:
        now = _now()
        with open(perm_csv, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                c.execute("""INSERT INTO permission(account_id,category,level,status,effect_date,expire_date,source,system_version,operator,created_at,updated_at)
                             VALUES(?,?,'中审','正常','2026-09-04','','过渡认定','V20260904','系统初始化',?,?)""", 
                          (row["account_id"], row["category"], now, now))
        n = c.execute("SELECT COUNT(*) FROM permission").fetchone()[0]
        c.execute("INSERT INTO change_log(permission_id,action,operator,change_time,detail) VALUES(?,?,?,?,?)",
                  (0, "初始化导入", "系统初始化", now, "从权限统计表过渡认定导入 %d 条" % n))
    # 迁移：旧四级(初审/中审/复审/终审) / 旧三级(初/中/高) -> 新三级(初审/中审/高审)
    c.execute("UPDATE account SET level='初审' WHERE level IN ('初','初审')")
    c.execute("UPDATE account SET level='中审' WHERE level IN ('中','中审')")
    c.execute("UPDATE account SET level='高审' WHERE level IN ('高','复审','终审')")
    c.execute("UPDATE permission SET level='初审' WHERE level IN ('初','初审')")
    c.execute("UPDATE permission SET level='中审' WHERE level IN ('中','中审')")
    c.execute("UPDATE permission SET level='高审' WHERE level IN ('高','复审','终审')")
    # 迁移：账号状态「在册」统一为「正常」，与权限状态口径保持一致
    c.execute("UPDATE account SET status='正常' WHERE status='在册'")
    # 迁移：职务角色名称「评审委员会」统一为「评审委员会成员」，与制度表述一致
    c.execute("UPDATE leader_record SET role='评审委员会成员' WHERE role='评审委员会'")
    # 迁移：账号密码列（默认 account_id@2026），并对尚无密码的账号初始化默认密码
    acols = {x[1] for x in c.execute("PRAGMA table_info(account)")}
    if "password" not in acols:
        c.execute("ALTER TABLE account ADD COLUMN password TEXT DEFAULT ''")
    # 历史错误：曾把空密码批量写成 default_pw("")（即 @2026 的散列），需按 account_id 重算为 account_id@2026
    wrong_pw = default_pw("")
    for (aid,) in c.execute("SELECT account_id FROM account").fetchall():
        cur = c.execute("SELECT password FROM account WHERE account_id=?", (aid,)).fetchone()[0]
        if not cur or cur == wrong_pw:
            c.execute("UPDATE account SET password=? WHERE account_id=?", (default_pw(aid), aid))
    # 迁移：旧 official_list（单人员-任务登记） -> 官方任务包 + 成员关系表
    ocols = {x[1] for x in c.execute("PRAGMA table_info(official_list)")}
    new_pkg_empty = c.execute("SELECT COUNT(*) FROM official_task_package").fetchone()[0] == 0
    if ocols and new_pkg_empty:
        rows = c.execute("SELECT * FROM official_list ORDER BY id").fetchall()
        groups = {}
        for r in rows:
            key = (r["task_name"] or "").strip() or "未命名任务"
            if key not in groups:
                groups[key] = []
            groups[key].append(r)
        now = _now()
        for task_name, mems in groups.items():
            task_id = task_name
            # 去重 task_id：若已有同名任务包，追加序号
            base_id, seq = task_id, 1
            while c.execute("SELECT 1 FROM official_task_package WHERE task_id=?", (task_id,)).fetchone():
                task_id = "%s_%d" % (base_id, seq); seq += 1
            creator = next((r["operator"] or "" for r in mems if r["operator"]), "系统迁移")
            owner = next((r["owner"] or "" for r in mems if r["owner"]), "")
            note = "从旧官方任务名单迁移"
            cur = c.execute("""INSERT INTO official_task_package
                (task_name, task_id, creator, owner, note, operator, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (task_name, task_id, creator, owner, note, "系统迁移", now, now))
            pid = cur.lastrowid
            for r in mems:
                aid = (r["account_id"] or "").strip()
                if not aid:
                    continue
                if c.execute("SELECT 1 FROM official_task_member WHERE package_id=? AND account_id=?", (pid, aid)).fetchone():
                    continue
                c.execute("""INSERT INTO official_task_member
                    (package_id, account_id, required_level, note, operator, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?)""",
                    (pid, aid, r["required_level"] or "", r["note"] or "", r["operator"] or "系统迁移", now, now))
        # 迁移完成，重命名旧表备查（不删除，避免误伤历史数据）
        try:
            c.execute("ALTER TABLE official_list RENAME TO official_list_legacy")
        except sqlite3.OperationalError:
            pass
        conn.commit()
    # 迁移：permission 增加 见习期截止，落实 5.6 见习 1 个月转正
    pcols = {x[1] for x in c.execute("PRAGMA table_info(permission)")}
    if "probation_until" not in pcols:
        c.execute("ALTER TABLE permission ADD COLUMN probation_until TEXT DEFAULT ''")
    # 迁移：权限类型(perm_type)整体下线，相关位置协同清理
    if "perm_type" in pcols:
        try:
            c.execute("ALTER TABLE permission DROP COLUMN perm_type")
        except sqlite3.OperationalError:
            pass
    # 迁移：assess_record 增加流程字段
    cols = {x[1] for x in c.execute("PRAGMA table_info(assess_record)")}
    if "flow_status" not in cols:
        c.execute("ALTER TABLE assess_record ADD COLUMN flow_status TEXT DEFAULT '考核中'")
    if "reject_reason" not in cols:
        c.execute("ALTER TABLE assess_record ADD COLUMN reject_reason TEXT")
    if "reject_time" not in cols:
        c.execute("ALTER TABLE assess_record ADD COLUMN reject_time TEXT")
    # 迁移：registration 报名登记 → 申请管理（字段语义重构）
    rcols = {x[1] for x in c.execute("PRAGMA table_info(registration)")}
    if "audit_type" in rcols and "apply_level" not in rcols:
        c.execute("ALTER TABLE registration RENAME COLUMN audit_type TO apply_level")
    rcols = {x[1] for x in c.execute("PRAGMA table_info(registration)")}
    if "current_node" not in rcols:
        c.execute("ALTER TABLE registration ADD COLUMN current_node TEXT")
    if "node_time" not in rcols:
        c.execute("ALTER TABLE registration ADD COLUMN node_time TEXT")
    if "transfer_time" not in rcols:
        c.execute("ALTER TABLE registration ADD COLUMN transfer_time TEXT")
    # 考核指标配置
    if c.execute("SELECT COUNT(*) FROM assess_config").fetchone()[0] == 0:
        for i, (name, w, pl, d, it, note) in enumerate(DEFAULT_ASSESS):
            c.execute("INSERT INTO assess_config(name,weight,pass_line,direction,input_type,note,sort_order) VALUES(?,?,?,?,?,?,?)",
                      (name, w, pl, d, it, note, i))
    # 考核示例记录（演示数据，可随时清空重录）
    if c.execute("SELECT COUNT(*) FROM assess_record").fetchone()[0] == 0:
        _seed_assess(conn, c)
    conn.commit()
    conn.close()

def _seed_assess(conn, c):
    now = _now()
    accts = [r["account_id"] for r in c.execute("SELECT account_id FROM account").fetchall()]
    rnd = random.Random(20260904)
    periods = [("2026-07", "月"), ("2026-08", "月")]
    for period, ptype in periods:
        for aid in accts:
            judgment = round(rnd.uniform(94.0, 99.8), 1)
            task = round(rnd.uniform(95.0, 99.8), 1)
            official_err = round(rnd.uniform(0, 4.8), 1)
            feedback = rnd.choice([0, 0, 0, 0, 1, 1, 2])
            official_versions = rnd.randint(300, 720)
            main_cat_versions = rnd.randint(22, 52)
            feature_edits = rnd.randint(1, 4)
            veto = 1 if rnd.random() < 0.02 else 0
            veto_reason = "演示示例：存在一票否决情形" if veto else ""
            c.execute("""INSERT INTO assess_record(account_id,period,period_type,v_judgment,v_task,v_official_err,v_feedback,
                        official_versions,main_cat_versions,feature_edits,veto,veto_reason,note,operator,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (aid, period, ptype, judgment, task, official_err, feedback, official_versions,
                       main_cat_versions, feature_edits, veto, veto_reason, "演示示例数据", "系统初始化", now, now))

def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ---------------------------------------------------------------- 考核计算
def assess_eval(values, config):
    """values: dict of metric column->value; config: list of assess_config rows (ordered).
    返回 (composite, passed, per_metric[{name,value,pass,contrib}])"""
    per = []
    composite = 0.0
    all_pass = True
    for cfg in config:
        col = METRIC_COLS.get(cfg["name"])
        if not col:
            continue
        val = values.get(col)
        if val is None:
            val = 0
        pl = cfg["pass_line"]
        w = cfg["weight"]
        if cfg["direction"] == "ge":
            ok = val >= pl
            contrib = (w / 100) * max(0, min(val, 100))
        elif cfg["direction"] == "le":
            ok = val <= pl
            contrib = (w / 100) * max(0, min((pl - val) / pl * 100, 100)) if pl else ((w / 100) if val <= 0 else 0)
        elif cfg["direction"] == "count0":
            ok = val <= pl
            contrib = (w / 100) * max(0, 100 - val * 20)
        else:
            ok = True
            contrib = (w / 100) * min(val, 100)
        # 官方任务专项：必考（制度 5.4）。无官方任务评审量即视为缺考不通过
        if cfg["name"] == "官方任务专项错误率" and "official_versions" in values and (values.get("official_versions") or 0) < 1:
            ok = False
        composite += contrib
        all_pass = all_pass and ok
        per.append(dict(name=cfg["name"], value=val, passed=ok, contrib=round(contrib, 1)))
    # 一票否决（制度 5.4/5.5）：存在否决项即判定不通过，且综合成绩归零
    if values.get("veto"):
        all_pass = False
        composite = 0.0
    return round(composite, 1), all_pass, per

# ---------------------------------------------------------------- 校验
def _derive_expire(status, provided):
    """失效时间非手动：仅 停审/退出/永封 自动置失效日期（未提供则取当天），其余状态清空。"""
    if status in ("停审", "退出", "永封"):
        return (provided or "").strip() or _now()[:10]
    return ""

def validate_permission(p, conn):
    account_id = (p.get("account_id") or "").strip()
    level = (p.get("level") or "").strip() or "中审"
    if level not in LEVELS:
        return False, "等级非法"
    category = (p.get("category") or "").strip()
    # 初审：仅普通评审，不绑定分类
    if level == "初审":
        category = ""
    if not account_id:
        return False, "账号ID为必填项"
    if level != "初审" and not category:
        return False, "分类为必填项（初审除外）"
    if category and not conn.execute("SELECT 1 FROM category_dict WHERE category=?", (category,)).fetchone():
        return False, "分类「%s」不在分类字典中" % category
    status = p.get("status") or "正常"
    if status not in PERM_STATUSES:
        return False, "状态非法"
    for d in ((p.get("effect_date") or "").strip(), (p.get("expire_date") or "").strip()):
        if d:
            try:
                datetime.datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                return False, "日期格式应为 YYYY-MM-DD：%s" % d
    ed, exd = (p.get("effect_date") or "").strip(), (p.get("expire_date") or "").strip()
    if ed and exd and ed > exd:
        return False, "生效时间不能晚于失效时间"
    exd = _derive_expire(status, exd)
    return True, (account_id, category, level, status, ed, exd)

# ---------------------------------------------------------------- 统计/冲突
def snapshot(conn):
    total_acct = conn.execute("SELECT COUNT(*) FROM account").fetchone()[0]
    total_cat = conn.execute("SELECT COUNT(*) FROM category_dict").fetchone()[0]
    total_perm = conn.execute("SELECT COUNT(*) FROM permission").fetchone()[0]
    assigned = conn.execute(
        "SELECT COUNT(DISTINCT account_id||'|'||category) FROM permission WHERE recycled=0 AND status IN (%s)"
        % ",".join("?" * len(ACTIVE_PERM)), tuple(ACTIVE_PERM)).fetchone()[0]
    matrix = total_acct * total_cat
    active_acct = conn.execute("SELECT COUNT(*) FROM account WHERE status IN (%s)" % ",".join("?" * len(ACTIVE_ACCT)), tuple(ACTIVE_ACCT)).fetchone()[0]
    return dict(total_acct=total_acct, total_cat=total_cat, total_perm=total_perm, matrix=matrix,
                assigned=assigned, unassigned=matrix - assigned, coverage=round(assigned / matrix * 100, 2) if matrix else 0,
                active_acct=active_acct, active_rate=round(active_acct / total_acct * 100, 1) if total_acct else 0)

def cross_stats(conn, filters):
    where, params = build_where(filters)
    dim = filters.get("dim", "domain")
    allowed = {"domain": "cd.domain", "group_name": "cd.group_name", "category": "p.category",
               "level": "p.level", "status": "p.status",
               "system_version": "p.system_version", "effect_month": "substr(p.effect_date,1,7)",
               "operator": "p.operator"}
    col = allowed.get(dim, "cd.domain")
    sql = """SELECT %s AS dim, COUNT(*) AS perm_cnt, COUNT(DISTINCT p.account_id) AS person_cnt, COUNT(DISTINCT p.category) AS cat_cnt
             FROM permission p LEFT JOIN category_dict cd ON p.category=cd.category
             LEFT JOIN account a ON p.account_id=a.account_id %s GROUP BY %s ORDER BY perm_cnt DESC""" % (col, where, col)
    return [dict(dim=r["dim"] or "(空)", perm_cnt=r["perm_cnt"], person_cnt=r["person_cnt"], cat_cnt=r["cat_cnt"]) for r in conn.execute(sql, params).fetchall()]

def build_where(filters):
    clauses, params = [], []
    mapping = {"domain": "cd.domain", "group_name": "cd.group_name", "category": "p.category",
               "level": "p.level", "status": "p.status",
               "system_version": "p.system_version", "account_id": "p.account_id",
               "operator": "p.operator", "recycled": "p.recycled"}
    for k in ("domain", "group_name", "category", "level", "status", "system_version", "account_id", "operator"):
        v = filters.get(k)
        if v:
            if k == "account_id":
                like = "%%%s%%" % v.lower()
                clauses.append("(LOWER(p.account_id) LIKE ? OR LOWER(COALESCE(a.display_name,'')) LIKE ?)")
                params.extend([like, like])
            else:
                clauses.append("%s=?" % mapping[k]); params.append(v)
    if filters.get("effect_from"):
        clauses.append("p.effect_date>=?"); params.append(filters["effect_from"])
    if filters.get("effect_to"):
        clauses.append("p.effect_date<=?"); params.append(filters["effect_to"])
    if "recycled" in filters:
        clauses.append("p.recycled=?"); params.append(int(filters["recycled"]))
    if filters.get("only_active"):
        clauses.append("p.status IN (%s)" % ",".join("?" * len(ACTIVE_PERM))); params.extend(ACTIVE_PERM)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params

def detect_conflicts(conn):
    """数据冲突：影响台账准确性的硬性问题，建议尽快处理。"""
    out = []
    rows = conn.execute("SELECT * FROM permission WHERE recycled=0").fetchall()
    by_pair = {}
    for r in rows:
        by_pair.setdefault((r["account_id"], r["category"]), []).append(r)
    for (acct, cat), lst in by_pair.items():
        levels = set(x["level"] for x in lst)
        if "初审" in levels and "中审" in levels:
            out.append(dict(group="conflict", kind="初审/中审并存", severity="高",
                            account=acct, category=cat,
                            detail="同账号同分类同时存在「初审」与「中审」两条权限记录，等级相互冲突（制度1.1）。",
                            suggestion="核实后保留正确的一条，回收或合并另一条。",
                            ids=[x["id"] for x in lst]))
    for r in rows:
        if r["status"] in ("停审", "降级", "已回收", "退出", "永封") and not (r["expire_date"] or "").strip():
            out.append(dict(group="conflict", kind="缺失失效时间", severity="中",
                            account=r["account_id"], category=r["category"],
                            detail="权限状态为「%s」但缺少失效时间，无法判断何时解除（制度6.3）。" % r["status"],
                            suggestion="补充失效时间，或转入正式休眠/回收流程。",
                            ids=[r["id"]]))
        if r["effect_date"] and r["expire_date"] and r["effect_date"] > r["expire_date"]:
            out.append(dict(group="conflict", kind="生效晚于失效", severity="高",
                            account=r["account_id"], category=r["category"],
                            detail="生效日期 %s 晚于失效日期 %s，时间区间非法。" % (r["effect_date"], r["expire_date"]),
                            suggestion="核对并修正日期，或回收该记录。",
                            ids=[r["id"]]))
    return out

def detect_redundancy(conn):
    """疑似冗余：多为历史/审计痕迹，建议人工确认后再决定清理。"""
    out = []
    rows = conn.execute("SELECT * FROM permission WHERE recycled=0").fetchall()
    seen = {}
    for r in rows:
        seen.setdefault((r["account_id"], r["category"], r["level"]), []).append(r)
    for key, lst in seen.items():
        if len(lst) > 1:
            out.append(dict(group="redundancy", kind="完全重复记录", severity="中",
                            account=key[0], category=key[1],
                            detail="存在 %d 条完全相同的权限记录（账号/分类/类型/等级一致）。" % len(lst),
                            suggestion="确认后保留一条，删除其余重复项。",
                            ids=[x["id"] for x in lst]))
    for r in conn.execute("SELECT * FROM permission WHERE recycled=1").fetchall():
        out.append(dict(group="redundancy", kind="已回收记录占位", severity="低",
                        account=r["account_id"], category=r["category"],
                        detail="该权限已回收，仍保留在台账中（通常需留存审计痕迹，非必须清理）。",
                        suggestion="如确认无需审计，可归档或清理。",
                        ids=[r["id"]]))
    by_pair = {}
    for r in rows:
        by_pair.setdefault((r["account_id"], r["category"]), []).append(r)
    for (acct, cat), lst in by_pair.items():
        levels = set(x["level"] for x in lst)
        if "中审" in levels and "初审" in levels:
            for x in lst:
                if x["level"] == "初审":
                    out.append(dict(group="redundancy", kind="低阶冗余", severity="低",
                                    account=acct, category=cat,
                                    detail="同分类已有「中审」权限，该「初审」记录可由中审向下覆盖（制度1.1）。",
                                    suggestion="如无特殊用途，可清理该初审记录。",
                                    ids=[x["id"]]))
    return out

# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    # 启用 HTTP/1.1 持久连接：浏览器可复用 TCP 连接，避免大量短连接堆积为
    # CLOSE_WAIT/TIME_WAIT（此前表现为「越用越慢直至连不上」）。
    # 前提：所有响应必须携带准确的 Content-Length，故统一收敛到 _send 出口。
    protocol_version = "HTTP/1.1"

    def _send(self, code, obj=None, body=None, ctype="application/json; charset=utf-8", headers=None):
        if obj is not None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        if body is None:
            body = b""
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if headers:
            for _k, _v in headers.items():
                self.send_header(_k, _v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

    def _auth_account(self, conn):
        """从 Authorization: Bearer <token> 解析当前登录账号（未登录返回 None）。
        同时兼容 ?token= 查询参数，供 <iframe>/<img> 等无法携带自定义头的浏览器内嵌资源使用。"""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return session_get(auth[7:].strip())
        # <iframe> 与 <img> 无法发送 Authorization 头，允许通过 URL 查询参数透传 token
        qs, _ = self._q()
        token = qs.get("token", [None])[0]
        if token:
            return session_get(token)
        return None

    def _require_login(self, conn):
        """要求已登录；未登录直接返回 401 并短路。返回 account_id 或 None。"""
        aid = self._auth_account(conn)
        if not aid:
            self._send(401, {"error": "未登录或登录已失效，请先登录"})
            return None
        return aid

    def _require_admin(self, conn, aid):
        """要求当前登录账号属于管理角色（在任的 评审委员会成员/团队负责人/质量组长）。"""
        if not aid:
            return False
        if is_admin(conn, aid):
            return True
        # 超级管理员单独授予的“系统管理/管理员”能力覆盖同样视同管理角色（用于路由门禁）
        if cap_override(conn, aid, "system_admin") == 1:
            return True
        if cap_override(conn, aid, "admin_grant") == 1:
            return True
        return bool(conn.execute(
            "SELECT 1 FROM leader_record WHERE account_id=? AND role IN (%s) AND status IN (%s) LIMIT 1"
            % (",".join("?"*len(ADMIN_ROLES)), ",".join("?"*len(REVIEWER_STATUSES))),
            (aid,) + tuple(ADMIN_ROLES) + tuple(REVIEWER_STATUSES)).fetchone())

    def _is_rev_or_admin(self, conn, aid):
        """当前账号是否为评审角色（在任的 分类组长/质量组长/评审委员会成员）或管理角色（含超级管理员单独授予的覆盖）。"""
        return has_cap(conn, aid, "upgrade_review") or has_cap(conn, aid, "system_admin")

    def _need_rev_or_admin(self, conn, aid):
        if self._is_rev_or_admin(conn, aid):
            return True
        self._send(403, {"error": "无权限：需要评审或管理角色（分类组长/质量组长/评审委员会成员/团队负责人）"})
        return False

    def _need_owner_or_admin(self, conn, aid, owner_account_id):
        """资源归属校验：本人或管理角色可操作；否则 403。"""
        if aid == owner_account_id or self._require_admin(conn, aid):
            return True
        self._send(403, {"error": "无权限：仅本人或管理角色可操作该记录"})
        return False

    def _eval_role_assigns(self, conn, aid, method, eid=None, b=None):
        """评审角色身份绑定（不可跨权）：仅超级管理员可读写；GET 列表 / POST 新增 / DELETE 删除。"""
        now = _now()
        if not is_super_admin(conn, aid):
            return self._send(403, {"error": "无权限：评审角色绑定仅超级管理员可管理"})
        if method == "GET":
            role = (b or {}).get("role") or ""
            cat = (b or {}).get("category")
            where = "WHERE 1=1"; params = []
            if role:
                where += " AND role=?"; params.append(role)
            if cat:
                where += " AND category=?"; params.append(cat)
            rows = conn.execute(
                "SELECT a.*, ac.display_name FROM eval_role_assign a LEFT JOIN account ac ON a.account_id=ac.account_id %s ORDER BY a.role, a.category, a.account_id" % where,
                params).fetchall()
            return self._send(200, dict(rows=[dict(r) for r in rows], roles=EVAL_REVIEW_ROLES))
        if method == "POST":
            role = (b.get("role") or "").strip()
            account_id = (b.get("account_id") or "").strip()
            category = (b.get("category") or "").strip()
            if role not in EVAL_REVIEW_ROLES:
                return self._send(400, {"error": "评审角色非法：应为 %s 之一" % " / ".join(EVAL_REVIEW_ROLES)})
            if not account_id:
                return self._send(400, {"error": "被绑定账号为必填"})
            acct = conn.execute("SELECT 1 FROM account WHERE account_id=?", (account_id,)).fetchone()
            if not acct:
                return self._send(400, {"error": "账号不存在：%s" % account_id})
            try:
                conn.execute("INSERT INTO eval_role_assign(role,account_id,category,created_at,updated_at) VALUES(?,?,?,?,?)",
                             (role, account_id, category, now, now))
                conn.commit()
            except Exception as e:
                return self._send(400, {"error": "新增失败（可能已存在相同绑定）：%s" % e})
            return self._send(200, {"ok": True})
        if method == "DELETE":
            if not eid:
                return self._send(400, {"error": "缺少绑定记录 id"})
            conn.execute("DELETE FROM eval_role_assign WHERE id=?", (eid,))
            conn.commit()
            return self._send(200, {"ok": True})
        return self._send(405, {"error": "method not allowed"})

    def _perm_suspended(self, conn, account_id, category):
        """该账号在该分类的权限是否处于停审（严重/重大违规挂起）。"""
        if not account_id or not category:
            return False
        r = conn.execute(
            "SELECT 1 FROM permission WHERE account_id=? AND category=? AND status=? AND recycled=0 LIMIT 1",
            (account_id, category, SUSPEND_STATUS)).fetchone()
        return bool(r)

    def _login(self, conn, b):
        account_id = (b.get("account_id") or "").strip()
        password = b.get("password") or ""
        r = login_account(conn, account_id, password)
        if not r:
            _login_fail(account_id)
            cnt = _login_fail_count(account_id)
            window_min = LOGIN_FAIL_WINDOW // 60
            return self._send(401, {"error": f"账号或密码错误（近 {window_min} 分钟内已失败 {cnt} 次），请核对后重试"})
        _login_ok(account_id)
        token = gen_token()
        SESSIONS[token] = {"account_id": r["account_id"], "expires": datetime.datetime.now().timestamp() + SESSION_TTL}
        # 登录审计：记录 IP / 设备码 / User-Agent（系统管理-账号登录情况 仅超级管理员可见）
        try:
            ip = self.client_address[0] if self.client_address else ""
            ua = (self.headers.get("User-Agent") or "")[:200]
            device_id = (b.get("device_id") or "").strip()[:64]
            now = _now()
            conn.execute("INSERT INTO login_log(account_id,login_time,ip,device_id,user_agent) VALUES(?,?,?,?,?)",
                         (r["account_id"], now, ip, device_id, ua))
            conn.execute("UPDATE account SET last_login_time=?, last_login_ip=?, last_login_device=? WHERE account_id=?",
                         (now, ip, device_id, r["account_id"]))
            conn.commit()
        except Exception:
            pass
        return self._send(200, dict(token=token, account_id=r["account_id"], level=r["level"], status=r["status"],
                                     is_reviewer=has_cap(conn, r["account_id"], "upgrade_review"),
                                     is_admin=has_cap(conn, r["account_id"], "system_admin"),
                                     is_senior=has_cap(conn, r["account_id"], "violation_register"),
                                     is_super_admin=has_cap(conn, r["account_id"], "admin_grant")))

    def _me(self, qs):
        # 仅接受 Authorization: Bearer 头，避免 token 泄露到日志/历史
        token = self.headers.get("Authorization", "")
        if token.startswith("Bearer "):
            token = token[7:].strip()
        else:
            token = ""
        if not token:
            return self._send(200, dict(account_id=None))
        aid = session_get(token)
        if not aid:
            return self._send(200, dict(account_id=None))
        conn = get_conn()
        try:
            r = conn.execute("SELECT account_id,level,status FROM account WHERE account_id=?", (aid,)).fetchone()
            return self._send(200, dict(account_id=aid, level=r["level"], status=r["status"],
                                         is_reviewer=has_cap(conn, aid, "upgrade_review"),
                                         is_admin=has_cap(conn, aid, "system_admin"),
                                         is_senior=has_cap(conn, aid, "violation_register"),
                                         is_super_admin=has_cap(conn, aid, "admin_grant"),
                                         eval_roles=get_eval_roles(conn, aid)))
        finally:
            conn.close()

    def _q(self):
        p = urllib.parse.urlparse(self.path)
        return urllib.parse.parse_qs(p.query), p.path

    def do_GET(self):
        qs, path = self._q()
        if path in ("/", "/index.html"):
            return self._static_file("index.html", "text/html; charset=utf-8")
        if path == "/api/me":
            return self._me(qs)
        m = re.match(r"^/api/screenshots/(.+)$", path)
        if m:
            return self._serve_screenshot(m.group(1))
        m = re.match(r"^/api/system-docs/(.+)$", path)
        if m:
            return self._serve_system_doc(m.group(1))
        if path.startswith("/static/"):
            return self._static_file(os.path.basename(path))
        if path.startswith("/api/"):
            return self.api_get(path, qs)
        self._send(404, {"error": "not found"})

    def _static_file(self, fn, ctype=None):
        fp = os.path.join(STATIC_DIR, fn)
        if not os.path.exists(fp):
            return self._send(404, {"error": "no file"})
        mtime = os.path.getmtime(fp)
        # 协商缓存：文件未变更时返回 304，避免每次刷新全量重传
        # （三个静态资源合计约 250KB，其中 app.js 约 146KB）
        ims = self.headers.get("If-Modified-Since")
        if ims:
            try:
                since = email.utils.parsedate_to_datetime(ims).timestamp()
                if int(since) >= int(mtime):
                    self.send_response(304)
                    self.send_header("Content-Length", "0")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    return
            except Exception:
                pass
        with open(fp, "rb") as f:
            data = f.read()
        if ctype is None:
            ctype = "text/html; charset=utf-8" if fn.endswith(".html") else ("application/javascript; charset=utf-8" if fn.endswith(".js") else "text/css; charset=utf-8")
        self._send(200, body=data, ctype=ctype,
                   headers={"Cache-Control": "no-cache",
                            "Last-Modified": email.utils.formatdate(mtime, usegmt=True)})

    def _serve_screenshot(self, rel):
        # 仅登录用户可查看截图（报名人与评估人均需查看）
        conn = get_conn()
        try:
            aid = self._require_login(conn)
            if aid is None: return
        finally:
            conn.close()
        rel = rel.replace("..", ".").lstrip("/")
        fp = os.path.normpath(os.path.join(BASE_DIR, "data", "screenshots", rel))
        if not fp.startswith(os.path.normpath(SCREENSHOT_DIR)) or not os.path.isfile(fp):
            return self._send(404, {"error": "截图不存在"})
        ext = os.path.splitext(fp)[1].lower()
        ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}.get(ext, "application/octet-stream")
        with open(fp, "rb") as f:
            data = f.read()
        return self._send(200, body=data, ctype=ctype, headers={"Cache-Control": "private, max-age=86400"})

    def _serve_system_doc(self, rel):
        # 制度文档（PDF / 流程图）内置为系统页面资源；登录后可查看
        conn = get_conn()
        try:
            aid = self._require_login(conn)
            if aid is None: return
        finally:
            conn.close()
        rel = urllib.parse.unquote(rel)
        rel = rel.replace("..", ".").lstrip("/")
        fp = os.path.normpath(os.path.join(BASE_DIR, "static", "system_docs", rel))
        base = os.path.normpath(os.path.join(BASE_DIR, "static", "system_docs"))
        if not fp.startswith(base) or not os.path.isfile(fp):
            return self._send(404, {"error": "文档不存在"})
        ext = os.path.splitext(fp)[1].lower()
        ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
                 ".pdf": "application/pdf"}.get(ext, "application/octet-stream")
        with open(fp, "rb") as f:
            data = f.read()
        return self._send(200, body=data, ctype=ctype, headers={"Cache-Control": "public, max-age=86400"})

    def api_get(self, path, qs):
        conn = get_conn()
        try:
            def g(k): return qs.get(k, [None])[0]
            if path == "/api/overview":
                aid = self._auth_account(conn)
                if not has_cap(conn, aid, "system_admin"):
                    return self._send(403, {"error": "无权限：总览已归入系统管理，仅管理员可访问"})
                snap = snapshot(conn)
                status_dist = conn.execute("SELECT status, COUNT(*) c FROM account GROUP BY status").fetchall()
                domain_cov = conn.execute(
                    """SELECT cd.domain AS domain, COUNT(DISTINCT p.account_id) AS persons FROM permission p
                       LEFT JOIN category_dict cd ON p.category=cd.category WHERE p.recycled=0 AND p.status IN (%s)
                       GROUP BY cd.domain""" % ",".join("?" * len(ACTIVE_PERM)), tuple(ACTIVE_PERM)).fetchall()
                ta = conn.execute("SELECT MAX(period) AS lp FROM assess_record").fetchone()["lp"]
                assess = self._assess_summary(conn, ta) if ta else None
                return self._send(200, dict(snapshot=snap,
                    status_dist=[dict(status=r["status"], c=r["c"]) for r in status_dist],
                    domain_cov=[dict(domain=r["domain"], coverage=round(r["persons"]/snap["total_acct"]*100, 1) if snap["total_acct"] else 0, persons=r["persons"]) for r in domain_cov],
                    assess=assess, latest_period=ta))
            if path == "/api/dict":
                cats = conn.execute("SELECT domain,group_name,category FROM category_dict ORDER BY domain,group_name,category").fetchall()
                accts = conn.execute("SELECT account_id,display_name,level,status FROM account ORDER BY account_id").fetchall()
                return self._send(200, dict(
                    categories=[dict(domain=r["domain"], group_name=r["group_name"], category=r["category"]) for r in cats],
                    accounts=[dict(account_id=r["account_id"], display_name=r["display_name"], level=r["level"], status=r["status"]) for r in accts],
                    levels=LEVELS, statuses=PERM_STATUSES,
                    account_levels=ACCOUNT_LEVELS, account_statuses=ACCOUNT_STATUSES, system_version=SYSTEM_VERSION))
            if path == "/api/eval-role-assigns":
                aid = self._auth_account(conn)
                return self._eval_role_assigns(conn, aid, "GET", b=dict(qs))
            if path == "/api/categories":
                rows = conn.execute("SELECT id,domain,group_name,category FROM category_dict ORDER BY domain,group_name,category").fetchall()
                return self._send(200, dict(rows=[dict(r) for r in rows]))
            if path == "/api/accounts":
                rows = conn.execute("SELECT * FROM account ORDER BY account_id").fetchall()
                return self._send(200, dict(rows=[dict(r) for r in rows], account_levels=ACCOUNT_LEVELS))
            if path == "/api/permissions":
                filters = {k: g(k) for k in ("domain","group_name","category","perm_type","level","status","system_version","account_id","operator","effect_from","effect_to")}
                if g("recycled") in ("0","1"): filters["recycled"] = g("recycled")
                if g("only_active") == "1": filters["only_active"] = 1
                where, params = build_where(filters)
                page = int(g("page") or 1); size = int(g("size") or 50)
                total = conn.execute("SELECT COUNT(*) FROM permission p LEFT JOIN category_dict cd ON p.category=cd.category LEFT JOIN account a ON p.account_id=a.account_id " + where, params).fetchone()[0]
                sql = """SELECT p.id,p.account_id,a.display_name,p.category,cd.domain,cd.group_name,p.level,p.status,
                                p.effect_date,p.expire_date,p.source,p.system_version,p.operator,p.created_at,p.updated_at,p.recycled,
                                p.probation_until
                         FROM permission p LEFT JOIN category_dict cd ON p.category=cd.category LEFT JOIN account a ON p.account_id=a.account_id %s
                         ORDER BY p.account_id, p.category LIMIT ? OFFSET ?""" % where
                rows = conn.execute(sql, params + [size, (page-1)*size]).fetchall()
                return self._send(200, dict(total=total, page=page, size=size, rows=[dict(r) for r in rows]))
            if path == "/api/permissions/matrix":
                return self._perm_matrix(conn, qs)
            if path == "/api/stats":
                aid = self._auth_account(conn)
                if not has_cap(conn, aid, "system_admin"):
                    return self._send(403, {"error": "无权限：统计已归入系统管理，仅管理员可访问"})
                filters = {k: g(k) for k in ("domain","group_name","category","perm_type","level","status","system_version","account_id","operator","effect_from","effect_to")}
                filters["dim"] = g("dim") or "domain"
                return self._send(200, dict(dim=filters["dim"], rows=cross_stats(conn, filters)))
            if path == "/api/conflicts":
                aid = self._auth_account(conn)
                if not is_admin(conn, aid):
                    return self._send(403, {"error": "无权限：数据质量检查仅对管理员开放"})
                return self._send(200, dict(rows=detect_conflicts(conn)))
            if path == "/api/redundancy":
                aid = self._auth_account(conn)
                if not is_admin(conn, aid):
                    return self._send(403, {"error": "无权限：数据质量检查仅对管理员开放"})
                return self._send(200, dict(rows=detect_redundancy(conn)))
            if path == "/api/logs":
                rows = conn.execute("SELECT * FROM change_log ORDER BY id DESC LIMIT 500").fetchall()
                return self._send(200, dict(rows=[dict(r) for r in rows]))
            # ---- 站内信箱（内部消息系统）----
            if path == "/api/messages":
                return self._msg_list(conn, qs)
            if path == "/api/messages/groups":
                return self._msg_groups(conn)
            if path == "/api/inbox":
                return self._inbox(conn, qs)
            if path == "/api/inbox/unread-count":
                return self._inbox_unread(conn)
            _m_inbox = re.match(r"^/api/inbox/(\d+)$", path)
            if _m_inbox:
                return self._inbox_detail(conn, int(_m_inbox.group(1)))
            _m_msg = re.match(r"^/api/messages/(\d+)$", path)
            if _m_msg:
                return self._msg_detail(conn, int(_m_msg.group(1)))
            if path == "/api/assess/config":
                cfg = conn.execute("SELECT * FROM assess_config ORDER BY sort_order").fetchall()
                return self._send(200, dict(rows=[dict(r) for r in cfg]))
            if path == "/api/assess/periods":
                rows = conn.execute("SELECT DISTINCT period FROM assess_record ORDER BY period DESC").fetchall()
                return self._send(200, dict(periods=[r["period"] for r in rows]))
            if path == "/api/assess/records":
                period = g("period") or conn.execute("SELECT MAX(period) FROM assess_record").fetchone()[0]
                acct = g("account_id")
                where = "WHERE period=?"; params = [period]
                if acct: where += " AND account_id=?"; params.append(acct)
                rows = conn.execute("SELECT r.*,a.display_name FROM assess_record r LEFT JOIN account a ON r.account_id=a.account_id %s ORDER BY r.account_id" % where, params).fetchall()
                cfg = conn.execute("SELECT * FROM assess_config ORDER BY sort_order").fetchall()
                out = []
                for r in rows:
                    d = dict(r)
                    composite, passed, per = assess_eval(dict(d), cfg)
                    d["composite"] = composite; d["passed"] = passed; d["metrics"] = per
                    out.append(d)
                return self._send(200, dict(period=period, rows=out, config=[dict(c) for c in cfg]))
            if path == "/api/assess/stats":
                period = g("period") or conn.execute("SELECT MAX(period) FROM assess_record").fetchone()[0]
                return self._send(200, self._assess_stats(conn, period))
            if path == "/api/assess/review-progress":
                period = g("period") or conn.execute("SELECT MAX(period) FROM assess_record").fetchone()[0]
                return self._send(200, self._review_progress(conn, period))
            if path == "/api/assess/exemptions":
                period = g("period")
                where = "WHERE 1=1"; params = []
                if period:
                    where += " AND period=?"; params.append(period)
                rows = conn.execute("SELECT e.*,a.display_name FROM assess_exemption e LEFT JOIN account a ON e.account_id=a.account_id %s ORDER BY e.period DESC,e.account_id" % where, params).fetchall()
                return self._send(200, dict(rows=[dict(r) for r in rows]))
            if path == "/api/registrations":
                rows = conn.execute("SELECT * FROM registration ORDER BY id DESC").fetchall()
                return self._send(200, dict(rows=[dict(r) for r in rows]))
            if path == "/api/assess/pending":
                period = g("period") or conn.execute("SELECT MAX(period) FROM assess_record").fetchone()[0]
                cfg = conn.execute("SELECT * FROM assess_config ORDER BY sort_order").fetchall()
                rows = conn.execute("SELECT r.*,a.display_name FROM assess_record r LEFT JOIN account a ON r.account_id=a.account_id WHERE r.flow_status='已打回' AND r.period=? ORDER BY r.reject_time DESC", (period,)).fetchall()
                out = []
                for r in rows:
                    d = dict(r); composite, ok, per = assess_eval(dict(d), cfg)
                    d["composite"] = composite; d["passed"] = ok
                    out.append(d)
                return self._send(200, dict(period=period, rows=out))
            if path == "/api/official-task-packages":
                kw = (g("kw") or "").strip()
                rows = self._list_official_packages(conn, kw)
                return self._send(200, dict(rows=rows))
            m = re.match(r"^/api/official-task-packages/(\d+)$", path)
            if m:
                pkg = self._get_official_package(conn, int(m.group(1)))
                if not pkg: return self._send(404, {"error": "任务包不存在"})
                return self._send(200, pkg)
            if path == "/api/export-reg":
                rows = conn.execute("SELECT * FROM registration ORDER BY id DESC").fetchall()
                import io as _io
                buf = _io.StringIO(); w = csv.writer(buf)
                w.writerow(["申请等级","报名时间","百科ID","QQ","推荐人百科ID","报名分类","报名条件","备注","当前流程节点","节点操作时间","评估结果","评估结果时间","评估人","操作人"])
                for r in rows:
                    w.writerow([r["apply_level"],r["apply_time"],r["apply_id"],r["qq"],r["referrer"],r["category"],r["condition_type"],r["note"],r["eval_node"],r["eval_node_time"],r["eval_result"],r["eval_result_time"],r["evaluator"],r["operator"]])
                data = ("\ufeff" + buf.getvalue()).encode("utf-8-sig")
                self.send_response(200); self.send_header("Content-Type", "text/csv; charset=utf-8-sig")
                self.send_header("Content-Disposition", "attachment; filename=application_report.csv")
                return self._send(200, body=data, ctype="text/csv; charset=utf-8-sig",
                                  headers={"Content-Disposition": "attachment; filename=application_report.csv"})
            if path == "/api/export":
                return self._export(conn, qs)
            # 升级申请评估结果列表
            m = re.match(r"^/api/upgrade-applies/(\d+)/evals$", path)
            if m:
                aid = self._auth_account(conn)
                return self._get_upgrade_evals(conn, aid, int(m.group(1)))
            m = re.match(r"^/api/category-expands/(\d+)/evals$", path)
            if m:
                aid = self._auth_account(conn)
                return self._get_upgrade_evals(conn, aid, int(m.group(1)), "expand")
            # 分类扩充申请列表（复用升级工作流，含特色词条）
            for key in GEN:
                if path == "/api/" + key:
                    meta = GEN[key]
                    fcols = meta["f"]
                    where, params = [], []
                    for f in fcols:
                        v = g(f)
                        if v:
                            where.append("%s=?" % f); params.append(v)
                    sql = "SELECT * FROM %s" % meta["t"]
                    if where:
                        sql += " WHERE " + " AND ".join(where)
                    sql += " ORDER BY id DESC"
                    rows = conn.execute(sql, params).fetchall()
                    out_rows = [dict(r) for r in rows]
                    if meta["t"] == "upgrade_apply":
                        for d in out_rows:
                            d["features"] = [dict(x) for x in conn.execute(
                                "SELECT id,entry_name,entry_link,compliant_time,note FROM upgrade_apply_feature WHERE apply_id=?", (d["id"],)).fetchall()]
                    if meta["t"] == "category_expand":
                        for d in out_rows:
                            d["features"] = [dict(x) for x in conn.execute(
                                "SELECT id,entry_name,entry_link,compliant_time,note FROM category_expand_feature WHERE apply_id=?", (d["id"],)).fetchall()]
                    return self._send(200, dict(rows=out_rows))
            if path == "/api/violations":
                self._restore_expired_penalties(conn)
                conn.commit()
                rows = conn.execute("SELECT * FROM violation_record ORDER BY id DESC").fetchall()
                return self._send(200, dict(rows=[dict(r) for r in rows]))
            if path == "/api/violation-stats":
                return self._send(200, self._violation_stats(conn))
            if path == "/api/referrer-liabilities":
                rows = conn.execute("SELECT * FROM referrer_liability ORDER BY id DESC").fetchall()
                return self._send(200, dict(rows=[dict(r) for r in rows]))
            if path == "/api/appeals":
                rows = conn.execute("SELECT * FROM appeal_record ORDER BY id DESC").fetchall()
                return self._send(200, dict(rows=[dict(r) for r in rows]))
            if path == "/api/status-strip-applies":
                aid = self._auth_account(conn)
                st = (qs.get("source_type") or [""])[0].strip()
                sid_raw = (qs.get("source_id") or [""])[0].strip()
                where, params = "", []
                if st in ("upgrade", "expand"):
                    where = "WHERE source_type=?"
                    params.append(st)
                    if sid_raw.isdigit():
                        where += " AND source_id=?"
                        params.append(int(sid_raw))
                rows = conn.execute("SELECT * FROM status_strip_apply %s ORDER BY id DESC" % where, params).fetchall()
                out = []
                for r in rows:
                    d = dict(r)
                    # 按当前登录账号计算其在各审批节点的可操作性（与后端审批门禁一一对应）
                    d["can_cat_lead"] = bool(is_reviewer(conn, aid) and _holds_perm_in_category(conn, aid, r["category"]))
                    d["can_quality_lead"] = bool(is_admin(conn, aid) and _holds_perm_in_dept(conn, aid, r["department"]))
                    d["can_review_lead"] = is_super_admin(conn, aid)
                    d["can_delete"] = (r["applicant"] == aid) or is_super_admin(conn, aid)
                    out.append(d)
                return self._send(200, dict(rows=out))
            if path == "/api/login-logs":
                if not is_super_admin(conn, self._auth_account(conn)):
                    return self._send(403, {"error": "无权限：登录情况仅超级管理员可查看"})
                rows = conn.execute("SELECT * FROM login_log ORDER BY id DESC LIMIT 500").fetchall()
                return self._send(200, dict(rows=[dict(r) for r in rows]))
            if path == "/api/password-reset-requests":
                if not is_super_admin(conn, self._auth_account(conn)):
                    return self._send(403, {"error": "无权限：密码恢复申请仅超级管理员可查看"})
                st = (qs.get("status") or [""])[0].strip()
                w, params = "", []
                if st:
                    w = "WHERE status=?"; params.append(st)
                rows = conn.execute("SELECT * FROM password_reset_request %s ORDER BY id DESC LIMIT 200" % w, params).fetchall()
                pending = conn.execute("SELECT COUNT(*) FROM password_reset_request WHERE status='待处理'").fetchone()[0]
                return self._send(200, dict(rows=[dict(r) for r in rows], pending=pending))
            if path == "/api/admin/accounts":
                if not has_cap(conn, self._auth_account(conn), "admin_grant"):
                    return self._send(403, {"error": "无权限：仅超级管理员可查看"})
                rows = conn.execute("SELECT account_id, display_name, level, status FROM account ORDER BY account_id").fetchall()
                out = []
                for r in rows:
                    d = dict(r)
                    d["is_admin"] = is_admin(conn, r["account_id"])
                    d["is_super_admin"] = is_super_admin(conn, r["account_id"])
                    d["roles"] = [dict(x) for x in conn.execute("SELECT role,status,scope FROM leader_record WHERE account_id=?", (r["account_id"],)).fetchall()]
                    out.append(d)
                domains = [x[0] for x in conn.execute("SELECT DISTINCT domain FROM category_dict ORDER BY domain")]
                groups = [dict(group_name=x[0], domain=x[1]) for x in
                          conn.execute("SELECT DISTINCT group_name, domain FROM category_dict ORDER BY domain, group_name")]
                return self._send(200, dict(rows=out, admin_roles=sorted(ADMIN_ROLES), extra_admin_role=EXTRA_ADMIN_ROLE,
                                            scoped_roles=SCOPED_ADMIN_ROLES, domains=domains, groups=groups))
            if path == "/api/capabilities":
                # 系统现有权限清单 + 各权限当前持有账号数（统计）
                return self._send(200, dict(
                    tiers=TIERS,
                    caps=[{k: c[k] for k in ("key", "name", "tier", "desc")} for c in CAPS],
                    stats=capability_stats(conn)))
            if path == "/api/my-capabilities":
                return self._send(200, self._my_capabilities(conn, self._auth_account(conn)))
            if path == "/api/admin/account-capabilities":
                if not has_cap(conn, self._auth_account(conn), "admin_grant"):
                    return self._send(403, {"error": "无权限：仅超级管理员可查看"})
                t = (qs.get("account_id") or [""])[0].strip()
                if not t:
                    return self._send(400, {"error": "account_id 为必填"})
                return self._send(200, self._admin_account_capabilities(conn, t))
            if path == "/api/spot-checks":
                return self._send(200, self._spot_list(conn, g("period"), g("account_id")))
            if path == "/api/reinstate":
                return self._send(200, self._reinstate_list(conn, g("account_id"), g("status")))
            if path == "/api/underperform":
                return self._send(200, self._underperform(conn, g("months") or 6))
            if path == "/api/recuse-hint":
                return self._send(200, dict(hint=self._recuse_hint(conn, g("account_id"), g("handler"))))
            if path == "/api/dormant":
                return self._send(200, dict(rows=self._dormant_list(conn)))
            if path == "/api/internship":
                return self._send(200, dict(rows=self._internship_list(conn)))
            if path == "/api/retrains":
                return self._send(200, self._retrain_list(conn, g("guide_version"), g("status")))
            if path == "/api/tadpole":
                return self._send(200, self._tadpole_list(conn))
            if path == "/api/need-retrain":
                return self._send(200, self._need_retrain_list(conn))
            if path == "/api/assess/cat-detail":
                acct = g("account_id"); period = g("period")
                where = "WHERE 1=1"; params = []
                if acct: where += " AND account_id=?"; params.append(acct)
                if period: where += " AND period=?"; params.append(period)
                rows = conn.execute("SELECT * FROM assess_category_detail %s ORDER BY period DESC, versions DESC" % where, params).fetchall()
                return self._send(200, dict(rows=[dict(r) for r in rows]))
            if path == "/api/upgrade/quota":
                rows = conn.execute(
                    """SELECT e.apply_id AS account_id, a.display_name, substr(e.apply_time,1,7) AS mon, COUNT(*) c
                       FROM category_expand e LEFT JOIN account a ON e.apply_id=a.account_id
                       GROUP BY e.apply_id, mon ORDER BY mon DESC, c DESC""").fetchall()
                out = [dict(account_id=r["account_id"], display_name=r["display_name"], month=r["mon"],
                            count=r["c"], limit=1, over=r["c"] > 1) for r in rows]
                return self._send(200, dict(rows=out, limit=1))
            self._send(404, {"error": "unknown api"})
        finally:
            conn.close()

    def _assess_summary(self, conn, period):
        rows = conn.execute("SELECT * FROM assess_record WHERE period=?", (period,)).fetchall()
        cfg = conn.execute("SELECT * FROM assess_config ORDER BY sort_order").fetchall()
        if not rows:
            return None
        passed = 0; comps = []; vetos = 0
        for r in rows:
            d = dict(r); composite, ok, _ = assess_eval(d, cfg)
            comps.append(composite); passed += 1 if ok else 0; vetos += 1 if d["veto"] else 0
        return dict(period=period, total=len(rows), passed=passed, fail=len(rows)-passed,
                    pass_rate=round(passed/len(rows)*100, 1), avg_score=round(sum(comps)/len(comps), 1), veto=vetos)

    def _load_exempt(self, conn, period):
        ex = conn.execute("SELECT * FROM assess_exemption WHERE period=?", (period,)).fetchall()
        return {r["account_id"]: dict(r) for r in ex}

    def _review_progress(self, conn, period):
        rows = conn.execute("""SELECT r.*, a.display_name, a.status as acct_status FROM assess_record r
            LEFT JOIN account a ON r.account_id=a.account_id WHERE r.period=?""", (period,)).fetchall()
        out = []
        any_detail = False
        for r in rows:
            acct = r["account_id"]
            # 当前有效权限分类（去重）
            cats = conn.execute("""SELECT DISTINCT category FROM permission
                WHERE account_id=? AND recycled=0 AND status IN ('正常','考核期','见习','实习')""", (acct,)).fetchall()
            held = [c["category"] for c in cats]
            # 当月各分类评审量明细（制度 3.1：主/副分类由当月评审量决定）
            detail = {row["category"]: row["versions"] for row in
                      conn.execute("SELECT category,versions FROM assess_category_detail WHERE account_id=? AND period=?", (acct, period)).fetchall()}
            has_detail = any(c in detail for c in held)
            if has_detail:
                any_detail = True
                # 按当月评审量降序：第1为主分类，随后 A(2-3)/B(4-6)/C(7-10)/D(11+) 副分类
                ranked = sorted(held, key=lambda c: -detail.get(c, 0))
                main_cat = ranked[0] if ranked else None
                subs = ranked[1:] if len(ranked) > 1 else []
                main_actual = detail.get(main_cat, 0) if main_cat else 0
            else:
                # 兼容历史聚合数据：主分类取字母序首位，评审量用 main_cat_versions 聚合值
                main_cat = held[0] if held else None
                subs = held[1:] if len(held) > 1 else []
                main_actual = r["main_cat_versions"] or 0

            def tier_of(i):
                if i < 2: return "A"
                if i < 5: return "B"
                if i < 9: return "C"
                return "D"
            def need_of(i):
                if i < 2: return 20
                if i < 5: return 10
                if i < 9: return 5
                return 5
            main_need = 30 if main_cat else 0
            sub_needs = [(subs[i], need_of(i), tier_of(i)) for i in range(len(subs))]
            official = r["official_versions"] or 0
            # 官方任务 50 个可代换 10 个特色/初优版本（仅副分类可代换，主分类不可）
            substitution = (official // 50) * 10
            # 主分类必须自达 30；副分类累计缺口可由代换额度补足
            main_ok = (main_actual >= main_need) if main_cat else True
            sub_deficit = sum(max(0, need_of(i) - detail.get(subs[i], 0) if has_detail else 0) for i in range(len(subs)))
            passed = bool(main_ok and (sub_deficit <= substitution))
            effective = main_actual + (sum(detail.get(c, 0) for c in subs) if has_detail else 0) + substitution
            out.append(dict(
                account_id=acct, display_name=r["display_name"], period=period,
                has_detail=has_detail,
                main_cat=main_cat, main_need=main_need, main_actual=main_actual,
                sub_count=len(subs), sub_needs=sub_needs,
                total_need=main_need + sum(need_of(i) for i in range(len(subs))),
                official_versions=official, substitution=substitution, effective=effective,
                passed=passed, v_judgment=r["v_judgment"]
            ))
        # 按达标情况、effective 排序
        out.sort(key=lambda x: (x["passed"], x["effective"]), reverse=True)
        return dict(period=period, rows=out, note=("" if any_detail else "部分账号缺少按分类评审量明细，主/副分类按历史聚合数据估算，请在「月度考核-评审量明细」中录入后重算"))

    def _assess_stats(self, conn, period):
        cfg = conn.execute("SELECT * FROM assess_config ORDER BY sort_order").fetchall()
        ex_map = self._load_exempt(conn, period)
        rows = conn.execute("SELECT r.*, a.display_name FROM assess_record r LEFT JOIN account a ON r.account_id=a.account_id WHERE period=?", (period,)).fetchall()
        results = []
        for r in rows:
            d = dict(r); composite, ok, per = assess_eval(d, cfg)
            ex = ex_map.get(d["account_id"])
            item = dict(account_id=d["account_id"], display_name=d["display_name"], composite=composite, passed=ok,
                        v_judgment=d["v_judgment"], v_task=d["v_task"], v_official_err=d["v_official_err"],
                        v_feedback=d["v_feedback"], veto=d["veto"], official_versions=d["official_versions"],
                        main_cat_versions=d["main_cat_versions"], feature_edits=d["feature_edits"])
            if ex:
                mode = ex["mode"]
                if mode == "免考核":
                    item["exempt"] = True; item["exempt_tag"] = "免考核"
                else:
                    item["exempt"] = False; item["exempt_tag"] = "减免%.0f%%" % (ex["reduce_ratio"] or 0)
                item["exempt_kind"] = ex["kind"]
            else:
                item["exempt"] = False; item["exempt_tag"] = ""
            results.append(item)
        # 免考核者不计入通过率分母
        countable = [x for x in results if not x["exempt"]]
        passed = sum(1 for x in countable if x["passed"])
        total = len(countable) or 1
        # 指标平均达标率
        metric_avg = []
        for c in cfg:
            col = METRIC_COLS.get(c["name"])
            if not col: continue
            vals = [x[col] or 0 for x in rows]
            avg = round(sum(vals)/len(vals), 1) if vals else 0
            ok = sum(1 for v in vals if (v >= c["pass_line"] if c["direction"] in ("ge",) else (v <= c["pass_line"])))
            metric_avg.append(dict(name=c["name"], avg=avg, pass_rate=round(ok/len(vals)*100, 1) if vals else 0, direction=c["direction"], pass_line=c["pass_line"]))
        # 排名 top10
        ranking = sorted(results, key=lambda x: x["composite"], reverse=True)[:10]
        # 趋势（按周期）
        periods = [r["period"] for r in conn.execute("SELECT DISTINCT period FROM assess_record ORDER BY period").fetchall()]
        trend = []
        for p in periods:
            rs = conn.execute("SELECT * FROM assess_record WHERE period=?", (p,)).fetchall()
            comps = []; pp = 0
            for r in rs:
                d = dict(r); composite, ok, _ = assess_eval(d, cfg); comps.append(composite); pp += 1 if ok else 0
            trend.append(dict(period=p, pass_rate=round(pp/len(rs)*100, 1) if rs else 0, avg_score=round(sum(comps)/len(comps), 1) if rs else 0, total=len(rs)))
        return dict(period=period, total=len(results), passed=passed, fail=len(countable)-passed,
                    exempt=len(results)-len(countable),
                    pass_rate=round(passed/total*100, 1), avg_score=round(sum(x["composite"] for x in countable)/total, 1) if countable else 0,
                    veto=sum(1 for x in results if x["veto"]), metric_avg=metric_avg, ranking=ranking,
                    distribution=[dict(label="通过", value=passed), dict(label="不通过", value=len(countable)-passed), dict(label="免考核", value=len(results)-len(countable))],
                    trend=trend, table=results)

    def _export(self, conn, qs):
        def g(k): return qs.get(k, [None])[0]
        filters = {k: g(k) for k in ("domain","group_name","category","perm_type","level","status","system_version","account_id","operator","effect_from","effect_to","recycled")}
        if g("only_active") == "1": filters["only_active"] = 1
        where, params = build_where(filters)
        sql = """SELECT p.id,p.account_id,a.display_name,cd.domain,cd.group_name,p.category,p.level,p.status,
                        p.effect_date,p.expire_date,p.source,p.system_version,p.operator,p.created_at,p.recycled
                 FROM permission p LEFT JOIN category_dict cd ON p.category=cd.category LEFT JOIN account a ON p.account_id=a.account_id %s
                 ORDER BY p.account_id, p.category""" % where
        rows = conn.execute(sql, params).fetchall()
        import io
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow(["ID","账号","昵称","领域(部门)","二级组","分类","等级","状态","生效","失效","来源","版本","操作人","创建时间","已回收"])
        for r in rows:
            w.writerow([r["id"],r["account_id"],r["display_name"],r["domain"],r["group_name"],r["category"],r["level"],r["status"],r["effect_date"],r["expire_date"],r["source"],r["system_version"],r["operator"],r["created_at"],r["recycled"]])
        data = ("\ufeff" + buf.getvalue()).encode("utf-8-sig")
        self.send_response(200); self.send_header("Content-Type", "text/csv; charset=utf-8-sig")
        self.send_header("Content-Disposition", "attachment; filename=permission_report.csv")
        return self._send(200, body=data, ctype="text/csv; charset=utf-8-sig",
                          headers={"Content-Disposition": "attachment; filename=permission_report.csv"})

    def _perm_matrix(self, conn, qs):
        def g(k): return qs.get(k, [None])[0]
        filters = {k: g(k) for k in ("domain","group_name","category","perm_type","level","status","system_version","account_id","operator","effect_from","effect_to")}
        if g("recycled") in ("0","1"): filters["recycled"] = g("recycled")
        if g("only_active") == "1": filters["only_active"] = 1
        where, params = build_where(filters)
        # 评审权限一览仅显示实际用户账号，剔除测试账号
        if where.strip():
            where2 = where + " AND a.is_test=0"
        else:
            where2 = "WHERE a.is_test=0"
        page = int(g("page") or 1); size = int(g("size") or 50)
        # 先统计符合条件的账号
        acct_sql = """SELECT COUNT(DISTINCT p.account_id) FROM permission p
                      LEFT JOIN category_dict cd ON p.category=cd.category
                      LEFT JOIN account a ON p.account_id=a.account_id %s""" % where2
        total = conn.execute(acct_sql, params).fetchone()[0]
        # 取本页账号：正常/考核期/见习/实习/待复权 排前面，停审/降级/已回收/退出/永封 置末尾
        active_sort = "CASE WHEN a.status IN (%s) THEN 0 ELSE 1 END" % ",".join("?" * len(ACTIVE_ACCT))
        acct_list_sql = """SELECT DISTINCT p.account_id FROM permission p
                           LEFT JOIN category_dict cd ON p.category=cd.category
                           LEFT JOIN account a ON p.account_id=a.account_id %s
                           ORDER BY %s, p.account_id LIMIT ? OFFSET ?""" % (where2, active_sort)
        accts = [r[0] for r in conn.execute(acct_list_sql, params + list(ACTIVE_ACCT) + [size, (page-1)*size]).fetchall()]
        if not accts:
            return self._send(200, dict(total=0, page=page, size=size, rows=[]))
        # 取这些账号的权限明细（同账号同分类只保留最新一条有效）
        rows = conn.execute("""SELECT p.id,p.account_id,a.display_name,a.level AS acct_level,a.status AS acct_status,
                                      p.category,cd.domain,cd.group_name,p.level,p.status,
                                      p.effect_date,p.expire_date,p.source,p.operator
                               FROM permission p
                               LEFT JOIN category_dict cd ON p.category=cd.category
                               LEFT JOIN account a ON p.account_id=a.account_id
                               WHERE p.account_id IN (%s) AND p.recycled=0
                               ORDER BY p.account_id, p.category, p.updated_at DESC""" % (",".join("?"*len(accts)) if accts else "''"), accts).fetchall()
        # 去重：同账号同分类取第一条（最新）
        seen = set(); perms = []
        for r in rows:
            key = (r["account_id"], r["category"])
            if key in seen: continue
            seen.add(key); perms.append(r)
        # 按账号聚合
        groups = {}
        for r in perms:
            aid = r["account_id"]
            groups.setdefault(aid, {"account_id": aid, "display_name": r["display_name"], "acct_level": r["acct_level"],
                                    "acct_status": r["acct_status"], "perm_count": 0, "domains": {}})
            g_ = groups[aid]
            g_["perm_count"] += 1
            dom = r["domain"] or "(未分类)"
            g_["domains"].setdefault(dom, {"items": []})
            g_["domains"][dom]["items"].append(dict(category=r["category"], group_name=r["group_name"], level=r["level"], status=r["status"]))
        # 构造返回，保留分组顺序
        result = []
        for aid in accts:
            g_ = groups.get(aid)
            if not g_: continue
            result.append({"account_id": aid, "display_name": g_["display_name"], "acct_level": g_["acct_level"],
                           "acct_status": g_["acct_status"], "perm_count": g_["perm_count"],
                           "domains": [{"domain": d, **v} for d, v in g_["domains"].items()]})
        return self._send(200, dict(total=total, page=page, size=size, rows=result))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        # 文件上传：不走 JSON body
        if parsed.path == "/api/upload/screenshot":
            return self._upload_screenshot()
        body = self._json_body(); conn = get_conn()
        try:
            if parsed.path == "/api/login":
                return self._login(conn, body)
            if parsed.path == "/api/password-reset-request":
                return self._request_password_reset(conn, body)
            # 其余所有写操作必须登录
            aid = self._require_login(conn)
            if aid is None:
                return
            if parsed.path == "/api/change-password":
                return self._change_pw(conn, aid, body)
            if parsed.path == "/api/accounts/reset-password":
                return self._reset_password(conn, aid, body)
            # 敏感写操作需管理角色（各路径映射到具体系统功能权限；超级管理员单独授予亦生效）
            ADMIN_PATHS = {"/api/permissions": "perm_manage", "/api/permissions/import": "perm_manage",
                           "/api/assess/config": "assess_manage", "/api/assess/import": "assess_manage",
                           "/api/assess/exemptions": "assess_manage",
                           "/api/leader/import": "leader_manage", "/api/permissions/restore": "perm_manage"}
            if parsed.path in ADMIN_PATHS and not has_cap(conn, aid, ADMIN_PATHS[parsed.path]):
                return self._send(403, {"error": "无权限：需要管理角色（评审委员会成员/团队负责人/质量组长）"})
            if parsed.path == "/api/permissions":
                return self._add_perm(conn, body)
            if parsed.path == "/api/permissions/import":
                return self._import(conn, body)
            if parsed.path == "/api/assess/config":
                return self._add_config(conn, body)
            if parsed.path == "/api/assess/records":
                return self._add_assess(conn, body)
            if parsed.path == "/api/assess/import":
                return self._import_assess(conn, body)
            if parsed.path == "/api/assess/exemptions":
                return self._add_exemption(conn, body)
            if parsed.path == "/api/registrations":
                return self._add_registration(conn, aid, body)
            if parsed.path == "/api/eval-role-assigns":
                return self._eval_role_assigns(conn, aid, "POST", b=body)
            if parsed.path == "/api/leader/import":
                return self._import_leaders(conn, body)
            if parsed.path == "/api/assess/cat-detail":
                if not self._is_rev_or_admin(conn, aid):
                    return self._send(403, {"error": "无权限：需要评审或管理角色"})
                return self._set_cat_detail(conn, body)
            if parsed.path == "/api/violations":
                if not has_cap(conn, aid, "violation_register"):
                    return self._send(403, {"error": "无权限：仅高审账号可登记违规"})
                return self._add_violation(conn, body)
            if parsed.path == "/api/spot-checks":
                if not self._is_rev_or_admin(conn, aid):
                    return self._send(403, {"error": "无权限：需要评审或管理角色"})
                return self._add_spot_check(conn, body)
            if parsed.path == "/api/reinstate":
                return self._add_reinstate(conn, body)
            if parsed.path == "/api/retrains":
                if not self._is_rev_or_admin(conn, aid):
                    return self._send(403, {"error": "无权限：需要评审或管理角色"})
                return self._add_retrain(conn, body)
            if parsed.path == "/api/underperform/execute":
                if not self._require_admin(conn, aid):
                    return self._send(403, {"error": "无权限：需要管理角色"})
                return self._execute_underperform(conn, body)
            if parsed.path == "/api/appeals":
                subj = (body.get("account_id") or "").strip()
                if not (aid == subj or self._require_admin(conn, aid)):
                    return self._send(403, {"error": "无权限：仅被处罚本人或管理角色可提交申诉"})
                return self._add_appeal(conn, body)
            # 超级管理员：设置 / 取消 其余账号的管理员身份（超级权限，仅超级管理员可调）
            if parsed.path == "/api/admin/grant":
                return self._admin_set(conn, aid, body, True)
            if parsed.path == "/api/admin/revoke":
                return self._admin_set(conn, aid, body, False)
            # 超级管理员：为某账号单独开通 / 撤销 某项系统功能权限（覆盖默认推导）
            if parsed.path == "/api/admin/capability-grant":
                return self._admin_cap_set(conn, aid, body, True)
            if parsed.path == "/api/admin/capability-revoke":
                return self._admin_cap_set(conn, aid, body, False)
            if parsed.path == "/api/admin/capability-bulk":
                return self._admin_cap_bulk(conn, aid, body)
            # 评审状态处置申请（提交，任意登录评审/管理可发起；审批需多节点）
            if parsed.path == "/api/status-strip-applies":
                return self._add_status_strip(conn, aid, body)
            # 官方任务包（名单管理）
            if parsed.path == "/api/official-task-packages":
                return self._add_official_package(conn, aid, body)
            # 站内信箱：发布消息（仅超级管理员）/ 标记已读（当前接收人本人）
            if parsed.path == "/api/messages":
                return self._post_message(conn, aid, body)
            _m_read = re.match(r"^/api/inbox/(\d+)/read$", parsed.path)
            if _m_read:
                return self._mark_read(conn, aid, int(_m_read.group(1)))
            m = re.match(r"^/api/permissions/(\d+)/restore$", parsed.path)
            if m:
                if not self._require_admin(conn, aid):
                    return self._send(403, {"error": "无权限：需要管理角色"})
                return self._restore_perm(int(m.group(1)), body)
            # 升级中审申请 / 分类扩充申请：工作流化写入（先于通用 CRUD）
            if parsed.path == "/api/upgrade-applies":
                return self._add_upgrade(conn, aid, body)
            if parsed.path == "/api/category-expands":
                return self._add_upgrade(conn, aid, body, "expand")
            m = re.match(r"^/api/upgrade-applies/(\d+)/evals$", parsed.path)
            if m:
                return self._add_upgrade_eval(conn, aid, int(m.group(1)), body)
            # 通用 CRUD 新增：official-list/leader-records 需管理角色；upgrade-applies/category-expands 支持本人自助提交或管理角色
            GEN_ADMIN_CAP = {"leader-records": "leader_manage"}
            for key in GEN:
                if parsed.path == "/api/" + key:
                    if key in GEN_ADMIN_CAP and not has_cap(conn, aid, GEN_ADMIN_CAP[key]):
                        return self._send(403, {"error": "无权限：需要管理角色"})
                    # 个人自助提交：归属校验（本人或管理角色）
                    if key in ("category-expands", "upgrade-applies"):
                        b_acct = (body.get("account_id") or "").strip()
                        if not (aid == b_acct or self._require_admin(conn, aid)):
                            return self._send(403, {"error": "无权限：%s 仅本人或管理角色可提交" % key})
                    return self._gen_add(conn, GEN[key], body)
            if parsed.path == "/api/categories":
                return self._add_category(conn, aid, body)
            self._send(404, {"error": "unknown api"})
        finally:
            conn.close()

    def _add_perm(self, conn, b):
        # 等级未指定时取账号身份等级
        if not b.get("level"):
            acct = conn.execute("SELECT level FROM account WHERE account_id=?", ((b.get("account_id") or "").strip(),)).fetchone()
            b["level"] = acct["level"] if acct else "中审"
        ok, res = validate_permission(b, conn)
        if not ok: return self._send(400, {"error": res})
        account_id, category, level, status, ed, exd = res
        if category and conn.execute("SELECT 1 FROM permission WHERE account_id=? AND category=? AND recycled=0", (account_id,category)).fetchone():
            return self._send(409, {"error": "该账号在「%s」下已存在权限记录" % category})
        conn.execute("INSERT OR IGNORE INTO account(account_id,display_name) VALUES(?,?)", (account_id, account_id))
        now = _now()
        cur = conn.execute("""INSERT INTO permission(account_id,category,level,status,effect_date,expire_date,source,system_version,operator,created_at,updated_at)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                           (account_id,category,level,status,ed,exd,b.get("source") or "手动录入",b.get("system_version") or SYSTEM_VERSION,b.get("operator") or "未署名",now,now))
        pid = cur.lastrowid
        conn.execute("INSERT INTO change_log(permission_id,action,operator,change_time,detail) VALUES(?,?,?,?,?)", (pid,"新增",b.get("operator") or "未署名",now,"新增权限：%s / %s / %s / %s" % (account_id,category,level,status)))
        conn.commit(); return self._send(200, {"ok": True, "id": pid})

    def _import(self, conn, b):
        rows = b.get("rows", []); mode = b.get("mode", "skip")
        added, skipped, errors = 0, 0, []; now = _now()
        for idx, p in enumerate(rows, 1):
            account_id = (p.get("account_id") or "").strip()
            if not p.get("level"):
                acct = conn.execute("SELECT level FROM account WHERE account_id=?", (account_id,)).fetchone()
                p["level"] = acct["level"] if acct else "中审"
            ok, res = validate_permission(p, conn)
            if not ok: errors.append("第%d行：%s" % (idx, res)); continue
            account_id, category, level, status, ed, exd = res
            dup = conn.execute("SELECT id FROM permission WHERE account_id=? AND category=? AND recycled=0", (account_id,category)).fetchone()
            if dup:
                if mode == "skip": skipped += 1; continue
                conn.execute("UPDATE permission SET status=?,effect_date=?,expire_date=?,operator=?,updated_at=? WHERE id=?", (status,ed,exd,p.get("operator") or "批量导入",now,dup["id"]))
                conn.execute("INSERT INTO change_log(permission_id,action,operator,change_time,detail) VALUES(?,?,?,?,?)", (dup["id"],"修改",p.get("operator") or "批量导入",now,"批量导入更新"))
                added += 1; continue
            conn.execute("INSERT OR IGNORE INTO account(account_id,display_name) VALUES(?,?)", (account_id, account_id))
            cur = conn.execute("""INSERT INTO permission(account_id,category,level,status,effect_date,expire_date,source,system_version,operator,created_at,updated_at)
                                  VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                               (account_id,category,level,status,ed,exd,p.get("source") or "批量导入",b.get("system_version") or SYSTEM_VERSION,p.get("operator") or "批量导入",now,now))
            pid = cur.lastrowid
            conn.execute("INSERT INTO change_log(permission_id,action,operator,change_time,detail) VALUES(?,?,?,?,?)", (pid,"新增",p.get("operator") or "批量导入",now,"批量导入新增"))
            added += 1
        conn.commit(); return self._send(200, dict(ok=True, added=added, skipped=skipped, errors=errors))

    def _add_config(self, conn, b):
        name = (b.get("name") or "").strip()
        if not name: return self._send(400, {"error": "指标名称为必填"})
        if conn.execute("SELECT 1 FROM assess_config WHERE name=?", (name,)).fetchone():
            return self._send(409, {"error": "指标已存在"})
        n = conn.execute("SELECT COUNT(*) FROM assess_config").fetchone()[0]
        try:
            cur = conn.execute("INSERT INTO assess_config(name,weight,pass_line,direction,input_type,note,sort_order) VALUES(?,?,?,?,?,?,?)",
                         (name, float(b.get("weight") or 0), float(b.get("pass_line") or 0), b.get("direction") or "ge", b.get("input_type") or "percent", b.get("note") or "", n))
        except sqlite3.IntegrityError:
            return self._send(409, {"error": "指标已存在"})
        conn.execute("INSERT INTO change_log(permission_id,action,operator,change_time,detail) VALUES(?,?,?,?,?)", (0,"指标配置新增",b.get("operator") or "未署名",_now(),"新增指标："+name))
        conn.commit(); return self._send(200, {"ok": True, "id": cur.lastrowid})

    # ---------- 站内信箱（内部消息系统） ----------
    def _need_super_admin(self, conn, aid):
        """站内信的管理发布权限：仅超级管理员具备。"""
        if not aid:
            self._send(401, {"error": "未登录或登录已失效，请先登录"}); return False
        if not is_super_admin(conn, aid):
            self._send(403, {"error": "无权限：站内信管理仅超级管理员可操作"}); return False
        return True

    def _msg_list(self, conn, qs):
        """管理端消息列表（含接收人数 / 已读数）。仅超级管理员。"""
        aid = self._auth_account(conn)
        if not self._need_super_admin(conn, aid): return
        def g(k): return qs.get(k, [None])[0]
        kw = (g("kw") or "").strip(); mtype = g("msg_type") or ""; scope = g("scope_type") or ""
        page = int(g("page") or 1); size = int(g("size") or 20)
        where, params = [], []
        if kw:
            where.append("(title LIKE ? OR body LIKE ?)"); params += ["%%%s%%" % kw, "%%%s%%" % kw]
        if mtype: where.append("msg_type=?"); params.append(mtype)
        if scope: where.append("scope_type=?"); params.append(scope)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        total = conn.execute("SELECT COUNT(*) FROM message" + w, params).fetchone()[0]
        rows = conn.execute("SELECT * FROM message" + w + " ORDER BY id DESC LIMIT ? OFFSET ?",
                            params + [size, (page - 1) * size]).fetchall()
        # 一次性聚合本页所有消息的接收/已读数，避免逐条 COUNT 造成的 N+1 查询
        ids = [m["id"] for m in rows]
        agg = {}
        if ids:
            ph = ",".join("?" * len(ids))
            for r in conn.execute(
                    "SELECT message_id, COUNT(*) n, SUM(is_read) rd FROM message_recipient WHERE message_id IN (%s) GROUP BY message_id" % ph,
                    ids).fetchall():
                agg[r["message_id"]] = (r["n"], r["rd"] or 0)
        out = []
        for m in rows:
            d = dict(m)
            n, rd = agg.get(m["id"], (0, 0))
            d["recipient_count"] = n; d["read_count"] = rd
            out.append(d)
        return self._send(200, dict(total=total, page=page, size=size, rows=out))

    def _msg_groups(self, conn):
        """可选用户组 / 群体清单（动态推导）。仅超级管理员。"""
        aid = self._auth_account(conn)
        if not self._need_super_admin(conn, aid): return
        return self._send(200, dict(rows=list_msg_groups(conn), kinds=MSG_GROUP_KINDS,
                                    scopes=MSG_SCOPES, msg_types=MSG_TYPES, auto_rules=AUTO_RULES))

    def _msg_detail(self, conn, mid):
        """管理端消息详情（含各接收人已读情况）。仅超级管理员。"""
        aid = self._auth_account(conn)
        if not self._need_super_admin(conn, aid): return
        m = conn.execute("SELECT * FROM message WHERE id=?", (mid,)).fetchone()
        if not m: return self._send(404, {"error": "消息不存在"})
        d = dict(m)
        recs = conn.execute("""SELECT mr.is_read, mr.read_time, mr.account_id, a.display_name
                               FROM message_recipient mr LEFT JOIN account a ON mr.account_id=a.account_id
                               WHERE mr.message_id=? ORDER BY mr.id""", (mid,)).fetchall()
        d["recipients"] = [dict(is_read=r["is_read"], read_time=r["read_time"],
                                account_id=r["account_id"], display_name=r["display_name"]) for r in recs]
        return self._send(200, d)

    def _inbox(self, conn, qs):
        """用户端收件箱：当前登录者可见的消息（含已读状态）。"""
        aid = self._auth_account(conn)
        if not aid: return self._send(401, {"error": "未登录或登录已失效，请先登录"})
        def g(k): return qs.get(k, [None])[0]
        kw = (g("kw") or "").strip(); only_unread = g("only_unread") == "1"
        page = int(g("page") or 1); size = int(g("size") or 20)
        where = ["mr.account_id=?"]; params = [aid]
        if kw:
            where.append("(m.title LIKE ? OR m.body LIKE ?)"); params += ["%%%s%%" % kw, "%%%s%%" % kw]
        if only_unread: where.append("mr.is_read=0")
        w = " WHERE " + " AND ".join(where)
        total = conn.execute("SELECT COUNT(*) FROM message_recipient mr JOIN message m ON m.id=mr.message_id" + w, params).fetchone()[0]
        rows = conn.execute("""SELECT m.*, mr.is_read, mr.read_time
                               FROM message_recipient mr JOIN message m ON m.id=mr.message_id
                               %s ORDER BY m.id DESC LIMIT ? OFFSET ?""" % w, params + [size, (page - 1) * size]).fetchall()
        return self._send(200, dict(total=total, page=page, size=size, rows=[dict(r) for r in rows]))

    def _inbox_detail(self, conn, mid):
        """用户端：查看本人收到的某条消息详情（含已读状态）。"""
        aid = self._auth_account(conn)
        if not aid: return self._send(401, {"error": "未登录或登录已失效，请先登录"})
        r = conn.execute("""SELECT m.*, mr.is_read, mr.read_time
                            FROM message_recipient mr JOIN message m ON m.id=mr.message_id
                            WHERE mr.message_id=? AND mr.account_id=?""", (mid, aid)).fetchone()
        if not r: return self._send(404, {"error": "未找到该消息，或您不在该消息的接收人中"})
        return self._send(200, dict(r))

    def _inbox_unread(self, conn):
        """当前用户未读消息数（用于站内信入口提醒角标）。"""
        aid = self._auth_account(conn)
        if not aid: return self._send(200, dict(unread=0))
        n = conn.execute("SELECT COUNT(*) FROM message_recipient WHERE account_id=? AND is_read=0", (aid,)).fetchone()[0]
        return self._send(200, dict(unread=n))

    def _post_message(self, conn, aid, b):
        """超级管理员发布站内信：支持系统消息 / 单独推送，单人、多账号、用户组或全体。"""
        if not self._need_super_admin(conn, aid): return
        res, err = create_message(conn, aid, b.get("msg_type") or "system", b.get("title"),
                                  b.get("body"), b.get("scope_type") or "all", b.get("scope_target"),
                                  source="manual")
        if err: return self._send(400, {"error": err})
        return self._send(200, dict(ok=True, id=res["id"], count=res["count"]))

    def _mark_read(self, conn, aid, mid):
        """当前用户将某条消息标记为已读。"""
        if not aid: return self._send(401, {"error": "未登录或登录已失效，请先登录"})
        r = conn.execute("SELECT id FROM message_recipient WHERE message_id=? AND account_id=?", (mid, aid)).fetchone()
        if not r: return self._send(404, {"error": "未找到该消息，或您不在该消息的接收人中"})
        conn.execute("UPDATE message_recipient SET is_read=1, read_time=? WHERE id=?", (_now(), r["id"]))
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM message_recipient WHERE account_id=? AND is_read=0", (aid,)).fetchone()[0]
        return self._send(200, dict(ok=True, unread=n))

    def _del_message(self, conn, aid, mid):
        """超级管理员删除站内信（级联清除接收人记录）。"""
        if not self._need_super_admin(conn, aid): return
        if not conn.execute("SELECT id FROM message WHERE id=?", (mid,)).fetchone():
            return self._send(404, {"error": "消息不存在"})
        conn.execute("DELETE FROM message_recipient WHERE message_id=?", (mid,))
        conn.execute("DELETE FROM message WHERE id=?", (mid,))
        conn.commit()
        return self._send(200, dict(ok=True))

    def _add_assess(self, conn, b):
        account_id = (b.get("account_id") or "").strip()
        period = (b.get("period") or "").strip()
        if not account_id or not period: return self._send(400, {"error": "账号与考核周期为必填"})
        if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (account_id,)).fetchone():
            return self._send(400, {"error": "账号不存在"})
        if conn.execute("SELECT 1 FROM assess_record WHERE account_id=? AND period=?", (account_id, period)).fetchone():
            return self._send(409, {"error": "该账号该周期评分记录已存在，请修改"})
        verr = self._check_veto(b)
        if verr:
            return self._send(400, {"error": verr})
        now = _now()
        cur = conn.execute("""INSERT INTO assess_record(account_id,period,period_type,v_judgment,v_task,v_official_err,v_feedback,official_versions,main_cat_versions,feature_edits,veto,veto_reason,note,operator,created_at,updated_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (account_id,period,b.get("period_type") or "月",_f(b.get("v_judgment")),_f(b.get("v_task")),_f(b.get("v_official_err")),int(b.get("v_feedback") or 0),
                      int(b.get("official_versions") or 0),int(b.get("main_cat_versions") or 0),int(b.get("feature_edits") or 0),1 if b.get("veto") else 0,b.get("veto_reason") or "",b.get("note") or "",b.get("operator") or "未署名",now,now))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)", (0,"考核记录新增",account_id,b.get("operator") or "未署名",now,"%s %s 评分录入" % (account_id, period)))
        rid = cur.lastrowid
        conn.commit()
        # 考核类自动发布（成绩公布）：评分落地即出结果，按预设规则自动通知被考核人
        self._auto_assess_result(conn, rid)
        return self._send(200, {"ok": True, "id": rid})

    def _auto_assess_result(self, conn, record_id):
        """按预设规则自动推送「考核成绩公布」站内信。同一账号同一周期重复录入时更新原文而非叠加。
        异常一律吞掉，避免影响主流程（评分录入）。"""
        try:
            r = conn.execute("SELECT * FROM assess_record WHERE id=?", (record_id,)).fetchone()
            if not r: return
            cfg = conn.execute("SELECT * FROM assess_config ORDER BY sort_order").fetchall()
            composite, passed, _ = assess_eval(dict(r), cfg)
            acc, period = r["account_id"], r["period"]
            title = "%s 月度考核成绩公布" % period
            body = ("您 %s 的月度考核成绩已公布：综合得分 %.1f，判定「%s」。\n"
                    "可前往「月度考核」查看各项指标明细。" % (period, composite, "达标" if passed else "未达标"))
            now = _now()
            old = conn.execute("""SELECT m.id FROM message m JOIN message_recipient mr ON mr.message_id=m.id
                                  WHERE m.auto_rule='assess_result' AND mr.account_id=? AND m.title=?""",
                               (acc, title)).fetchone()
            if old:
                # 成绩被修订：更新正文并重置为未读，保证接收人看到最新结果
                conn.execute("UPDATE message SET body=?, send_time=?, updated_at=? WHERE id=?", (body, now, now, old["id"]))
                conn.execute("UPDATE message_recipient SET is_read=0, read_time='' WHERE message_id=?", (old["id"],))
                conn.commit(); return
            auto_send_message(conn, "assess_result", title, body, accounts=[acc],
                              scope_type="user", scope_target=acc)
        except Exception:
            pass

    def _import_assess(self, conn, b):
        import io
        raw = b.get("csv") or ""
        if not raw: return self._send(400, {"error": "CSV 内容为空"})
        # 如果 raw 是 bytes（某些客户端），先按 utf-8/gbk 解码
        if isinstance(raw, bytes):
            text = None
            for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
                try:
                    text = raw.decode(enc)
                    break
                except Exception:
                    pass
            if text is None:
                return self._send(400, {"error": "CSV 编码无法识别，请使用 UTF-8 或 GBK 编码"})
        else:
            text = raw
        f = io.StringIO(text)
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return self._send(400, {"error": "CSV 缺少表头"})
        fn = [h.strip() for h in reader.fieldnames]
        # 必要字段映射：任务名/任务类型/领取人/评审人/参与状态/反馈原因/领取时间/更新完成时间
        req = {"任务名", "任务类型", "领取人", "参与状态"}
        missing = req - set(fn)
        if missing:
            return self._send(400, {"error": "CSV 缺少必要字段：%s" % ", ".join(missing)})
        # 周期：优先使用传入 period，否则从数据时间推断
        period = (b.get("period") or "").strip()
        if not period:
            dates = []
            for r in list(reader):
                for k in ("领取时间", "更新/评审完成时间", "提交时间"):
                    if r.get(k):
                        dates.append(r[k].strip()[:7])
            if dates:
                period = sorted(dates)[-1]
            f.seek(0); next(f)  # 重新读取
            reader = csv.DictReader(f)
        if not period:
            return self._send(400, {"error": "无法识别考核周期，请手动填写"})
        operator = (b.get("operator") or "CSV导入").strip()
        scope = (b.get("scope") or "all").strip()
        if scope not in ("edit", "review", "official", "all"):
            return self._send(400, {"error": "未知的导入类型：%s" % scope})
        # 聚合统计
        stats = {}
        official_kw = ["官方", "世界杯", "专项"]
        ok_status = {"已完成"}
        fail_status = {"未达标", "未通过", "反馈无效"}
        feedback_status = {"反馈无效", "反馈并放弃"}
        # 有效状态定义（用户给定 CSV 规则）
        review_valid_status = {"已完成", "未达标"}          # 评审任务：仅已完成/未达标为有效评审版本
        edit_valid_status = {"已完成"}                      # 编辑任务：仅已完成为有效编辑版本
        now = _now()
        skipped_rows = 0
        for r in reader:
            task_type = (r.get("任务类型") or "").strip()
            status = (r.get("参与状态") or "").strip()
            task_name = (r.get("任务名") or "").strip()
            acct = (r.get("领取人") or "").strip()
            if not acct:
                skipped_rows += 1
                continue
            is_official = any(kw in task_name for kw in official_kw)
            # 按页签隔离：只统计当前页签负责的任务范围，互不干扰
            if scope == "edit":
                if task_type != "词条编辑任务":
                    skipped_rows += 1
                    continue
                if "特色" not in task_name:
                    skipped_rows += 1
                    continue
                if status not in edit_valid_status:
                    skipped_rows += 1
                    continue
            elif scope == "review":
                if task_type != "词条评审任务":
                    skipped_rows += 1
                    continue
                if status not in review_valid_status:
                    skipped_rows += 1
                    continue
            elif scope == "official" and not is_official:
                skipped_rows += 1
                continue

            s = stats.setdefault(acct, {"judge_total": 0, "judge_ok": 0, "task_total": 0, "task_ok": 0,
                                         "official_total": 0, "official_err": 0, "feedback": 0, "rows": 0})
            s["rows"] += 1
            if task_type == "词条评审任务":
                s["judge_total"] += 1
                if status in ok_status:
                    s["judge_ok"] += 1
            elif task_type == "词条编辑任务":
                s["task_total"] += 1
                if status in ok_status:
                    s["task_ok"] += 1
            if is_official:
                s["official_total"] += 1
                if status not in ok_status:
                    s["official_err"] += 1
            if status in feedback_status:
                s["feedback"] += 1
            if is_official and status in fail_status:
                s["feedback"] += 1  # 官方任务失败视为专项错误叠加
        # 写入/更新 assess_record（按页签隔离：只覆盖本页签负责的字段，其余保留原值）
        records = []
        SCOPE_LABEL = {"edit": "编辑任务", "review": "评审任务", "official": "官方任务", "all": "全部"}
        DEFAULTS = dict(v_judgment=100.0, v_task=100.0, v_official_err=0.0, v_feedback=0,
                        official_versions=0, main_cat_versions=0, feature_edits=0)
        for acct, s in sorted(stats.items()):
            ex = conn.execute("SELECT * FROM assess_record WHERE account_id=? AND period=?", (acct, period)).fetchone()
            base = dict(ex) if ex else {}
            v_judgment = round(s["judge_ok"] / s["judge_total"] * 100, 1) if s["judge_total"] else None
            v_task = round(s["task_ok"] / s["task_total"] * 100, 1) if s["task_total"] else None
            v_official_err = round(s["official_err"] / s["official_total"] * 100, 1) if s["official_total"] else None
            # 字段修正：编辑任务→特色编辑达标数；评审任务→主分类评审版本数
            feature_edits = s["task_total"]
            main_cat_versions = s["judge_total"]
            official_versions = s["official_total"]
            if scope == "edit":
                vals = dict(v_task=(v_task if v_task is not None else base.get("v_task", 100.0)),
                            feature_edits=feature_edits)
            elif scope == "review":
                vals = dict(v_judgment=(v_judgment if v_judgment is not None else base.get("v_judgment", 100.0)),
                            main_cat_versions=main_cat_versions)
            elif scope == "official":
                vals = dict(v_official_err=(v_official_err if v_official_err is not None else base.get("v_official_err", 0.0)),
                            official_versions=official_versions)
            else:
                vals = dict(v_judgment=(v_judgment if v_judgment is not None else 100.0),
                            v_task=(v_task if v_task is not None else 100.0),
                            v_official_err=(v_official_err if v_official_err is not None else 0.0),
                            v_feedback=s["feedback"], official_versions=official_versions,
                            main_cat_versions=main_cat_versions, feature_edits=feature_edits)
            note = "CSV自动导入(%s)" % SCOPE_LABEL[scope]
            if not b.get("preview"):
                # 查找或插入账号
                conn.execute("INSERT OR IGNORE INTO account(account_id,display_name,level,status,join_date,note) VALUES(?,?, '中审','正常','','')", (acct, acct))
                if ex:
                    sets = ",".join("%s=?" % k for k in vals) + ",operator=?,updated_at=?,note=?"
                    conn.execute("UPDATE assess_record SET %s WHERE id=?" % sets,
                                 tuple(vals.values()) + (operator, now, note, ex["id"]))
                else:
                    full = dict(DEFAULTS); full.update(vals)
                    conn.execute("""INSERT INTO assess_record(account_id,period,period_type,v_judgment,v_task,v_official_err,v_feedback,
                                    official_versions,main_cat_versions,feature_edits,veto,veto_reason,note,operator,created_at,updated_at)
                                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                 (acct, period, "月", full["v_judgment"], full["v_task"], full["v_official_err"], full["v_feedback"],
                                  full["official_versions"], full["main_cat_versions"], full["feature_edits"], 0, "", note, operator, now, now))
            view = dict(DEFAULTS)
            if ex:
                view.update({k: base.get(k) for k in DEFAULTS if base.get(k) is not None})
            view.update(vals)
            cfg = conn.execute("SELECT * FROM assess_config ORDER BY sort_order").fetchall()
            composite, passed, per = assess_eval({"v_judgment": view["v_judgment"], "v_task": view["v_task"],
                                                  "v_official_err": view["v_official_err"], "v_feedback": view["v_feedback"],
                                                  "veto": base.get("veto", 0)}, cfg)
            records.append(dict(account_id=acct, period=period, v_judgment=view["v_judgment"], v_task=view["v_task"],
                                v_official_err=view["v_official_err"], v_feedback=view["v_feedback"],
                                official_versions=view["official_versions"], main_cat_versions=view["main_cat_versions"],
                                feature_edits=view["feature_edits"], composite=composite, passed=passed, rows=s["rows"]))
        total_rows = sum(s["rows"] for s in stats.values())
        if not b.get("preview"):
            conn.execute("INSERT INTO change_log(permission_id,action,operator,change_time,detail) VALUES(?,?,?,?,?)",
                         (0, "考核CSV导入", operator, now, "周期 %s 导入%s %d 条有效记录（跳过%d条），生成 %d 人评分" % (period, SCOPE_LABEL[scope], total_rows, skipped_rows, len(records))))
            conn.commit()
        return self._send(200, dict(ok=True, period=period, scope=scope, total_rows=total_rows, skipped_rows=skipped_rows, records=records))

    def do_PUT(self):
        try:
            parsed = urllib.parse.urlparse(self.path); parts = parsed.path.strip("/").split("/")
            body = self._json_body()
            conn = get_conn()
            # 所有写操作必须登录
            aid = self._require_login(conn)
            if aid is None:
                return
            ADMIN = lambda: self._require_admin(conn, aid)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "permissions" and parts[2].isdigit():
                if not ADMIN(): return self._send(403, {"error": "无权限：需要管理角色"})
                return self._put_perm(int(parts[2]), body)
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "accounts" and parts[2].isdigit() and parts[3] == "test":
                if not is_super_admin(conn, aid):
                    return self._send(403, {"error": "无权限：仅超级管理员可设置测试账号"})
                return self._set_account_test(conn, aid, int(parts[2]), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "accounts":
                if not ADMIN(): return self._send(403, {"error": "无权限：需要管理角色"})
                return self._put_account(int(parts[2]), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "assess" and parts[2] == "config":
                if not ADMIN(): return self._send(403, {"error": "无权限：需要管理角色"})
                return self._put_config(body)
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "assess" and parts[2] == "records":
                if not self._is_rev_or_admin(conn, aid):
                    return self._send(403, {"error": "无权限：需要评审或管理角色"})
                return self._put_assess(int(parts[3]), body)
            m = re.match(r"^/api/assess/records/(\d+)/reject$", parsed.path)
            if m:
                if not self._is_rev_or_admin(conn, aid):
                    return self._send(403, {"error": "无权限：需要评审或管理角色"})
                return self._reject_assess(int(m.group(1)), body)
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "assess" and parts[2] == "exemptions":
                if not ADMIN(): return self._send(403, {"error": "无权限：需要管理角色"})
                return self._put_exemption(int(parts[3]), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "registrations":
                return self._put_registration(conn, aid, int(parts[2]), body)
            # 升级中审申请 / 分类扩充申请 工作流化更新（先于通用 CRUD）
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "upgrade-applies" and parts[2].isdigit():
                return self._put_upgrade(conn, aid, int(parts[2]), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "category-expands" and parts[2].isdigit():
                return self._put_upgrade(conn, aid, int(parts[2]), body, "expand")
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "permissions" and parts[2] == "promote":
                if not ADMIN(): return self._send(403, {"error": "无权限：需要管理角色"})
                return self._promote_perm(conn, body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "me" and parts[2] == "password":
                return self._change_pw(conn, aid, body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "violations" and parts[2].isdigit():
                if not has_cap(conn, aid, "violation_edit"):
                    return self._send(403, {"error": "无权限：违规记录的删改仅管理员身份可进行"})
                return self._put_violation(conn, int(parts[2]), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "appeals" and parts[2].isdigit():
                if not ADMIN():
                    r = conn.execute("SELECT account_id FROM appeal_record WHERE id=?", (int(parts[2]),)).fetchone()
                    if not r or r["account_id"] != aid:
                        return self._send(403, {"error": "无权限：仅被处罚本人或管理角色可操作该申诉"})
                return self._put_appeal(conn, int(parts[2]), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "referrer-liabilities" and parts[2].isdigit():
                if not ADMIN(): return self._send(403, {"error": "无权限：需要管理角色"})
                return self._put_referrer_liability(conn, int(parts[2]), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "spot-checks" and parts[2].isdigit():
                if not self._is_rev_or_admin(conn, aid):
                    return self._send(403, {"error": "无权限：需要评审或管理角色"})
                return self._put_spot_check(conn, int(parts[2]), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "reinstate" and parts[2].isdigit():
                if not self._is_rev_or_admin(conn, aid):
                    return self._send(403, {"error": "无权限：需要评审或管理角色"})
                return self._put_reinstate(conn, int(parts[2]), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "retrains" and parts[2].isdigit():
                if not self._is_rev_or_admin(conn, aid):
                    return self._send(403, {"error": "无权限：需要评审或管理角色"})
                return self._put_retrain(conn, int(parts[2]), body)
            m = re.match(r"^/api/status-strip-applies/(\d+)/approve$", parsed.path)
            if m:
                return self._approve_status_strip(conn, aid, int(m.group(1)), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "dormant" and parts[2].isdigit():
                if not self._is_rev_or_admin(conn, aid):
                    return self._send(403, {"error": "无权限：需要评审或管理角色"})
                return self._set_dormant(conn, int(parts[2]), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "internship" and parts[2].isdigit():
                if not self._is_rev_or_admin(conn, aid):
                    return self._send(403, {"error": "无权限：需要评审或管理角色"})
                return self._internship_set(conn, int(parts[2]), body)
            m = re.match(r"^/api/official-task-packages/(\d+)$", parsed.path)
            if m:
                return self._put_official_package(conn, aid, int(m.group(1)), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] in GEN:
                key = parts[1]
                if key == "leader-records" and not ADMIN():
                    return self._send(403, {"error": "无权限：需要管理角色"})
                if key == "upgrade-applies" and not ADMIN():
                    r = conn.execute("SELECT account_id FROM upgrade_apply WHERE id=?", (int(parts[2]),)).fetchone()
                    if not r or r["account_id"] != aid:
                        return self._send(403, {"error": "无权限：仅本人或管理角色可编辑该升级申请"})
                return self._gen_put(conn, GEN[key], int(parts[2]), body)
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "categories" and parts[2].isdigit():
                return self._put_category(conn, aid, int(parts[2]), body)
            self._send(404, {"error": "unknown"})
        except Exception as e:
            import traceback as _tb
            _tb.print_exc()
            self._send(500, {"error": "服务器错误: %s" % e})
        finally:
            try: conn.close()
            except: pass

    def _put_perm(self, pid, b):
        conn = get_conn()
        try:
            r = conn.execute("SELECT * FROM permission WHERE id=?", (pid,)).fetchone()
            if not r: return self._send(404, {"error": "记录不存在"})
            # 非手动字段前端不传，沿用旧值；失效时间由状态推导（非手动）
            merged = dict(r); merged.update(b)
            ok, res = validate_permission(merged, conn)
            if not ok: return self._send(400, {"error": res})
            _, category, level, status, ed, exd = res
            old = "等级:%s/状态:%s/生效:%s/失效:%s" % (r["level"],r["status"],r["effect_date"],r["expire_date"])
            now = _now()
            conn.execute("UPDATE permission SET level=?,status=?,effect_date=?,expire_date=?,operator=?,updated_at=? WHERE id=?", (level,status,ed,exd,b.get("operator") or r["operator"],now,pid))
            new = "等级:%s/状态:%s/生效:%s/失效:%s" % (level,status,ed,exd)
            conn.execute("INSERT INTO change_log(permission_id,action,operator,change_time,detail) VALUES(?,?,?,?,?)", (pid,"修改",b.get("operator") or r["operator"],now,"旧[%s]→新[%s]" % (old,new)))
            conn.commit(); return self._send(200, {"ok": True})
        finally:
            conn.close()

    def _put_account(self, aid, b):
        conn = get_conn()
        try:
            r = conn.execute("SELECT * FROM account WHERE id=?", (aid,)).fetchone()
            if not r: return self._send(404, {"error": "账号不存在"})
            now = _now()
            new_level = b.get("level", r["level"])
            conn.execute("UPDATE account SET display_name=?,level=?,status=?,join_date=?,note=? WHERE id=?",
                         (b.get("display_name", r["display_name"]), new_level, b.get("status", r["status"]), b.get("join_date", r["join_date"]), b.get("note", r["note"]), aid))
            # 账号身份等级变更后，同步到其所有有效权限记录
            if "level" in b and b["level"] != r["level"]:
                conn.execute("UPDATE permission SET level=? WHERE account_id=? AND recycled=0", (new_level, r["account_id"]))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                         (0,"账号变更",r["account_id"],b.get("operator") or "未署名",now,"账号状态/信息更新：%s→%s / %s→%s" % (r["status"],b.get("status",r["status"]),r["level"],new_level)))
            conn.commit(); return self._send(200, {"ok": True})
        finally:
            conn.close()

    def _put_config(self, b):
        conn = get_conn()
        try:
            items = b.get("items", [])
            now = _now()
            for it in items:
                conn.execute("UPDATE assess_config SET weight=?,pass_line=?,direction=?,input_type=?,note=? WHERE name=?",
                             (float(it.get("weight") or 0), float(it.get("pass_line") or 0), it.get("direction") or "ge", it.get("input_type") or "percent", it.get("note") or "", it["name"]))
            conn.execute("INSERT INTO change_log(permission_id,action,operator,change_time,detail) VALUES(?,?,?,?,?)", (0,"指标配置更新",b.get("operator") or "未署名",now,"更新考核指标权重/合格线"))
            conn.commit(); return self._send(200, {"ok": True})
        finally:
            conn.close()

    def _put_assess(self, rid, b):
        conn = get_conn()
        try:
            r = conn.execute("SELECT * FROM assess_record WHERE id=?", (rid,)).fetchone()
            if not r: return self._send(404, {"error": "记录不存在"})
            merged = dict(r); merged.update({k: v for k, v in b.items() if v is not None})
            verr = self._check_veto(merged)
            if verr:
                return self._send(400, {"error": verr})
            now = _now()
            conn.execute("""UPDATE assess_record SET v_judgment=?,v_task=?,v_official_err=?,v_feedback=?,official_versions=?,main_cat_versions=?,feature_edits=?,veto=?,veto_reason=?,note=?,operator=?,updated_at=? WHERE id=?""",
                         (_f(b.get("v_judgment")),_f(b.get("v_task")),_f(b.get("v_official_err")),int(b.get("v_feedback") or 0),int(b.get("official_versions") or 0),int(b.get("main_cat_versions") or 0),int(b.get("feature_edits") or 0),1 if b.get("veto") else 0,b.get("veto_reason") or "",b.get("note") or "",b.get("operator") or r["operator"],now,rid))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)", (0,"考核记录修改",r["account_id"],b.get("operator") or r["operator"],now,"%s %s 评分修改" % (r["account_id"], r["period"])))
            # 已打回记录被重新录入评分时，复位流程状态为「考核中」并清空打回原因
            if r["flow_status"] == "已打回":
                conn.execute("UPDATE assess_record SET flow_status='考核中', reject_reason=NULL, reject_time=NULL WHERE id=?", (rid,))
                conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)", (0,"考核打回复位",r["account_id"],b.get("operator") or r["operator"],now,"%s %s 重新录入评分，流程状态复位为考核中" % (r["account_id"], r["period"])))
            conn.commit(); return self._send(200, {"ok": True})
        finally:
            conn.close()

    def _reject_assess(self, rid, b):
        conn = get_conn()
        try:
            r = conn.execute("SELECT * FROM assess_record WHERE id=?", (rid,)).fetchone()
            if not r: return self._send(404, {"error": "记录不存在"})
            reason = (b.get("reject_reason") or "").strip()
            if not reason:
                return self._send(400, {"error": "打回原因不能为空"})
            now = _now()
            conn.execute("""UPDATE assess_record SET flow_status='已打回', reject_reason=?, reject_time=?, updated_at=? WHERE id=?""",
                         (reason, now, now, rid))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                         (0,"考核打回",r["account_id"],b.get("operator") or "未署名",now,"%s %s 考核不通过打回：%s" % (r["account_id"], r["period"], reason)))
            conn.commit(); return self._send(200, {"ok": True})
        finally:
            conn.close()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path); parts = parsed.path.strip("/").split("/")
        conn = get_conn()
        try:
            aid = self._require_login(conn)
            if aid is None:
                return
            # 升级申请评估：撤回自己的评估（仅在待转正评估阶段）
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "upgrade-applies" and parts[2].isdigit() and parts[3] == "evals":
                return self._del_upgrade_eval(conn, aid, int(parts[2]))
            # 分类扩充评估：撤回自己的评估（仅在待转正评估阶段）
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "category-expands" and parts[2].isdigit() and parts[3] == "evals":
                return self._del_upgrade_eval(conn, aid, int(parts[2]), "expand")
            # 升级申请：申请人本人、管理角色、评审角色可删除（含特色记录与评估记录）
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "upgrade-applies" and parts[2].isdigit():
                return self._del_upgrade(conn, aid, int(parts[2]))
            # 分类扩充申请：申请人本人、管理角色、评审角色可删除（含特色记录与评估记录）
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "category-expands" and parts[2].isdigit():
                return self._del_upgrade(conn, aid, int(parts[2]), "expand")
            # 站内信箱：删除消息（仅超级管理员）。置于统一管理员门禁之前，
            # 避免超级管理员自身不具备管理角色时被误拦。
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "messages" and parts[2].isdigit():
                return self._del_message(conn, aid, int(parts[2]))
            # 评审角色绑定：删除（仅超级管理员，由 _eval_role_assigns 内部校验）
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "eval-role-assigns" and parts[2].isdigit():
                return self._eval_role_assigns(conn, aid, "DELETE", eid=int(parts[2]))
            # 报名删除允许申请人本人（非管理角色）操作，故不纳入统一管理员门禁
            if (not self._require_admin(conn, aid)) and not (len(parts)==3 and parts[0]=="api" and parts[1]=="registrations"):
                return self._send(403, {"error": "无权限：需要管理角色（评审委员会成员/团队负责人/质量组长）"})
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "permissions":
                return self._del_perm(int(parts[2]))
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "assess" and parts[2] == "records":
                return self._del_assess(int(parts[3]))
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "assess" and parts[2] == "exemptions":
                return self._del_exemption(int(parts[3]))
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "retrains" and parts[2].isdigit():
                return self._del_retrain(conn, int(parts[2]))
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "registrations":
                if not self._require_admin(conn, aid):
                    r = conn.execute("SELECT apply_id FROM registration WHERE id=?", (int(parts[2]),)).fetchone()
                    if not r or (r["apply_id"] or "") != aid:
                        return self._send(403, {"error": "无权限：仅本人或管理角色可删除该申请"})
                return self._del_registration(int(parts[2]))
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "violations":
                if not has_cap(conn, aid, "violation_delete"):
                    return self._send(403, {"error": "无权限：违规记录的删改仅管理员身份可进行"})
                return self._del_violation(conn, int(parts[2]))
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "status-strip-applies" and parts[2].isdigit():
                r = conn.execute("SELECT applicant,status FROM status_strip_apply WHERE id=?", (int(parts[2]),)).fetchone()
                if not r: return self._send(404, {"error": "申请不存在"})
                if r["status"] != "待审核": return self._send(400, {"error": "已终结的申请不可删除"})
                if r["applicant"] != aid and not is_super_admin(conn, aid):
                    return self._send(403, {"error": "无权限：仅申请人或超级管理员可删除该申请"})
                conn.execute("DELETE FROM status_strip_apply WHERE id=?", (int(parts[2]),))
                conn.commit(); return self._send(200, {"ok": True})
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "appeals":
                if not self._require_admin(conn, aid):
                    r = conn.execute("SELECT account_id FROM appeal_record WHERE id=?", (int(parts[2]),)).fetchone()
                    if not r or r["account_id"] != aid:
                        return self._send(403, {"error": "无权限：仅本人或管理角色可删除该申诉"})
                return self._del_appeal(conn, int(parts[2]))
            m = re.match(r"^/api/assess/config/(\d+)$", parsed.path)
            if m:
                return self._del_config(int(m.group(1)))
            m = re.match(r"^/api/official-task-packages/(\d+)$", parsed.path)
            if m:
                return self._del_official_package(conn, aid, int(m.group(1)))
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "accounts" and parts[2].isdigit():
                return self._del_account(conn, aid, int(parts[2]))
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "categories" and parts[2].isdigit():
                return self._del_category(conn, aid, int(parts[2]))
            if len(parts) == 3 and parts[0] == "api" and parts[1] in GEN:
                return self._gen_del(conn, GEN[parts[1]], int(parts[2]))
            self._send(404, {"error": "unknown"})
        finally:
            try: conn.close()
            except: pass

    def _del_perm(self, pid):
        conn = get_conn()
        try:
            r = conn.execute("SELECT * FROM permission WHERE id=?", (pid,)).fetchone()
            if not r: return self._send(404, {"error": "记录不存在"})
            now = _now()
            conn.execute("UPDATE permission SET recycled=1,status='已回收',expire_date=?,updated_at=? WHERE id=?", (now[:10], now, pid))
            conn.execute("INSERT INTO change_log(permission_id,action,operator,change_time,detail) VALUES(?,?,?,?,?)", (pid,"回收","未署名",now,"回收权限：%s / %s" % (r["account_id"], r["category"])))
            conn.commit(); return self._send(200, {"ok": True})
        finally:
            conn.close()

    def _del_account(self, conn, operator_id, account_db_id):
        """超级管理员彻底删除账号及其关联数据（全局闭环）。"""
        if not is_super_admin(conn, operator_id):
            return self._send(403, {"error": "无权限：仅超级管理员可删除账号"})
        r = conn.execute("SELECT account_id FROM account WHERE id=?", (account_db_id,)).fetchone()
        if not r:
            return self._send(404, {"error": "账号不存在"})
        aid = r["account_id"]
        # 保护超级管理员自身账号
        if is_super_admin(conn, aid):
            return self._send(400, {"error": "不可删除超级管理员账号"})
        # 账号级关联表（含 account_id 字段）
        tables = [
            "permission", "change_log", "login_log", "leader_record", "eval_role_assign",
            "password_reset_request", "assess_record", "assess_category_detail",
            "registration", "upgrade_apply", "upgrade_apply_eval",
            "category_expand", "category_expand_eval", "reinstate_apply",
            "violation_record", "appeal_record", "retrain_record",
            "status_strip_apply", "account_capability", "spot_check"
        ]
        for tbl in tables:
            try:
                conn.execute("DELETE FROM %s WHERE account_id=?" % tbl, (aid,))
            except Exception:
                pass
        # 站内信：删除该账号作为接收人的记录，以及该账号发送的消息
        try:
            conn.execute("DELETE FROM message_recipient WHERE account_id=?", (aid,))
            conn.execute("DELETE FROM message WHERE sender=?", (aid,))
        except Exception:
            pass
        # 部分申请表以 apply_id 存储账号 ID
        for tbl in ("registration", "upgrade_apply", "category_expand", "reinstate_apply"):
            try:
                conn.execute("DELETE FROM %s WHERE apply_id=?" % tbl, (aid,))
            except Exception:
                pass
        conn.execute("DELETE FROM account WHERE id=?", (account_db_id,))
        now = _now()
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "删除账号", aid, operator_id, now, "超级管理员 %s 彻底删除账号 %s 及其关联数据" % (operator_id, aid)))
        conn.commit()
        return self._send(200, {"ok": True})

    def _set_account_test(self, conn, operator_id, account_db_id, b):
        """超级管理员将账号标记为测试账号或实际账号。"""
        r = conn.execute("SELECT account_id, is_test FROM account WHERE id=?", (account_db_id,)).fetchone()
        if not r: return self._send(404, {"error": "账号不存在"})
        target = 1 if b.get("is_test") in (1, "1", True, "true") else 0
        if r["is_test"] == target:
            return self._send(200, {"ok": True, "unchanged": True, "is_test": target, "account_id": r["account_id"]})
        conn.execute("UPDATE account SET is_test=? WHERE id=?", (target, account_db_id))
        now = _now()
        label = "测试账号" if target else "实际账号"
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "账号用途变更", r["account_id"], operator_id, now, "超级管理员 %s 将账号 %s 标记为 %s" % (operator_id, r["account_id"], label)))
        conn.commit()
        return self._send(200, {"ok": True, "is_test": target, "account_id": r["account_id"]})

    def _check_category(self, conn, b, cid=None):
        domain = (b.get("domain") or "").strip()
        group = (b.get("group_name") or "").strip()
        cat = (b.get("category") or "").strip()
        if not domain or not group or not cat:
            return False, "领域、二级组、分类名称均为必填"
        # 唯一性校验（同一分类名全局唯一；如要改为同名不同组，需先删除旧记录）
        where = "category=?"
        params = [cat]
        if cid:
            where += " AND id<>?"
            params.append(cid)
        if conn.execute("SELECT 1 FROM category_dict WHERE %s" % where, params).fetchone():
            return False, "分类「%s」已存在" % cat
        return True, None

    def _add_category(self, conn, aid, b):
        if not is_super_admin(conn, aid):
            return self._send(403, {"error": "无权限：仅超级管理员可维护分类字典"})
        ok, err = self._check_category(conn, b)
        if not ok:
            return self._send(400, {"error": err})
        cur = conn.execute("INSERT INTO category_dict(domain,group_name,category) VALUES(?,?,?)",
                           (b.get("domain"), b.get("group_name"), b.get("category")))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "新增分类", "", aid, _now(), "新增分类：%s / %s / %s" % (b.get("domain"), b.get("group_name"), b.get("category"))))
        conn.commit()
        return self._send(200, {"ok": True, "id": cur.lastrowid})

    def _put_category(self, conn, aid, cid, b):
        if not is_super_admin(conn, aid):
            return self._send(403, {"error": "无权限：仅超级管理员可维护分类字典"})
        r = conn.execute("SELECT * FROM category_dict WHERE id=?", (cid,)).fetchone()
        if not r:
            return self._send(404, {"error": "分类不存在"})
        ok, err = self._check_category(conn, b, cid=cid)
        if not ok:
            return self._send(400, {"error": err})
        conn.execute("UPDATE category_dict SET domain=?, group_name=?, category=? WHERE id=?",
                     (b.get("domain"), b.get("group_name"), b.get("category"), cid))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "修改分类", "", aid, _now(), "修改分类 %s：%s / %s / %s" % (cid, b.get("domain"), b.get("group_name"), b.get("category"))))
        conn.commit()
        return self._send(200, {"ok": True})

    def _del_category(self, conn, aid, cid):
        if not is_super_admin(conn, aid):
            return self._send(403, {"error": "无权限：仅超级管理员可维护分类字典"})
        r = conn.execute("SELECT * FROM category_dict WHERE id=?", (cid,)).fetchone()
        if not r:
            return self._send(404, {"error": "分类不存在"})
        # 检查是否已被权限记录引用
        refs = conn.execute("SELECT COUNT(*) FROM permission WHERE category=? AND recycled=0", (r["category"],)).fetchone()[0]
        if refs:
            return self._send(400, {"error": "该分类已被 %d 条权限记录引用，不可删除" % refs})
        conn.execute("DELETE FROM category_dict WHERE id=?", (cid,))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "删除分类", "", aid, _now(), "删除分类：%s / %s / %s" % (r["domain"], r["group_name"], r["category"])))
        conn.commit()
        return self._send(200, {"ok": True})

    def _restore_perm(self, pid, b):
        conn = get_conn()
        try:
            r = conn.execute("SELECT * FROM permission WHERE id=?", (pid,)).fetchone()
            if not r: return self._send(404, {"error": "记录不存在"})
            if r["status"] != "已回收":
                return self._send(400, {"error": "只有已回收权限可以恢复"})
            now = _now()
            # 恢复为正常，清空失效日期，recycled 归 0
            conn.execute("UPDATE permission SET recycled=0, status='正常', expire_date='', updated_at=? WHERE id=?", (now, pid))
            conn.execute("INSERT INTO change_log(permission_id,action,operator,change_time,detail) VALUES(?,?,?,?,?)",
                         (pid, "恢复", b.get("operator") or "未署名", now, "恢复权限：%s / %s" % (r["account_id"], r["category"])))
            conn.commit(); return self._send(200, {"ok": True, "status": "正常"})
        finally:
            conn.close()

    def _del_assess(self, rid):
        conn = get_conn()
        try:
            r = conn.execute("SELECT * FROM assess_record WHERE id=?", (rid,)).fetchone()
            if not r: return self._send(404, {"error": "记录不存在"})
            now = _now()
            conn.execute("DELETE FROM assess_record WHERE id=?", (rid,))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)", (0,"考核记录删除",r["account_id"],"未署名",now,"%s %s 评分删除" % (r["account_id"], r["period"])))
            conn.commit(); return self._send(200, {"ok": True})
        finally:
            conn.close()

    # ---- 免减考核 ----
    def _add_exemption(self, conn, b):
        try:
            acct = (b.get("account_id") or "").strip()
            period = (b.get("period") or "").strip()
            if not acct: return self._send(400, {"error": "请填写账号"})
            if not period: return self._send(400, {"error": "请填写周期"})
            kind = b.get("kind") or "请假"
            mode = b.get("mode") or "免考核"
            now = _now()
            cur = conn.execute("""INSERT INTO assess_exemption(account_id,period,kind,mode,days,reduce_ratio,category,reason,operator,created_at)
                                  VALUES(?,?,?,?,?,?,?,?,?,?)""",
                              (acct, period, kind, mode, _f(b.get("days") or 0), _f(b.get("reduce_ratio") or 0),
                               b.get("category") or "", b.get("reason") or "", b.get("operator") or "未署名", now))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                        (0,"免减考核登记",acct,b.get("operator") or "未署名",now,"%s %s %s/%s 登记" % (acct, period, kind, mode)))
            conn.commit(); return self._send(200, {"ok": True, "id": cur.lastrowid})
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def _put_exemption(self, eid, b):
        conn = get_conn()
        try:
            r = conn.execute("SELECT * FROM assess_exemption WHERE id=?", (eid,)).fetchone()
            if not r: return self._send(404, {"error": "记录不存在"})
            now = _now()
            conn.execute("""UPDATE assess_exemption SET kind=?,mode=?,days=?,reduce_ratio=?,category=?,reason=?,operator=? WHERE id=?""",
                        (b.get("kind", r["kind"]), b.get("mode", r["mode"]), _f(b.get("days") if b.get("days") is not None else r["days"]),
                         _f(b.get("reduce_ratio") if b.get("reduce_ratio") is not None else r["reduce_ratio"]), b.get("category", r["category"]),
                         b.get("reason", r["reason"]), b.get("operator") or r["operator"], eid))
            conn.commit(); return self._send(200, {"ok": True})
        finally:
            conn.close()

    def _del_exemption(self, eid):
        conn = get_conn()
        try:
            r = conn.execute("SELECT * FROM assess_exemption WHERE id=?", (eid,)).fetchone()
            if not r: return self._send(404, {"error": "记录不存在"})
            now = _now()
            conn.execute("DELETE FROM assess_exemption WHERE id=?", (eid,))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                        (0,"免减考核删除",r["account_id"],"未署名",now,"%s %s 免减记录删除" % (r["account_id"], r["period"])))
            conn.commit(); return self._send(200, {"ok": True})
        finally:
            conn.close()

    # ---- 报名登记 ----
    def _add_registration(self, conn, aid, b):
        try:
            now = _now()
            apply_id = (b.get("apply_id") or "").strip()
            reg_cat = (b.get("category") or "").strip()
            condition_type = (b.get("condition_type") or "").strip()
            is_adm = is_admin(conn, aid)
            if not apply_id:
                return self._send(400, {"error": "百科ID 为必填"})
            # 跨权防卫：非管理员只能为自己提交报名申请
            if not is_adm and apply_id != aid:
                return self._send(403, {"error": "无权限：只能提交本人的报名申请"})
            if condition_type and condition_type not in REG_CONDITIONS:
                return self._send(400, {"error": "报名条件选项非法"})
            # 停审级联：报名账号在报名分类权限处于停审（严重违规挂起）时，暂不可报名
            if apply_id and reg_cat and self._perm_suspended(conn, apply_id, reg_cat):
                return self._send(400, {"error": "该账号在「%s」的权限处于停审（严重违规挂起），暂不可报名该分类" % reg_cat})
            # 制度 4.4 不得报名的情形：封禁/限制/取消、处罚期内、近6个月违规取消资格
            blk, reason = self._block_apply_reason(conn, apply_id)
            if blk:
                return self._send(400, {"error": reason})
            cur = conn.execute("""INSERT INTO registration(apply_level,apply_time,apply_id,qq,referrer,category,condition_type,screenshot_path,note,operator,eval_node,eval_node_time,eval_result,created_at,updated_at)
                                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                               ("初审", now, apply_id, b.get("qq") or "", b.get("referrer") or "",
                                reg_cat, condition_type, b.get("screenshot_path") or "",
                                b.get("note") or "", aid or "未署名",
                                "资格待核查", now, "", now, now))
            # 自动为报名账号创建系统账号（若不存在）：否则后续「待转正评估」须申请人本人登录提交，流程将卡死。
            # 初始密码为默认规则 账号@2026（登录后可自行修改）。
            created_account = False
            if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (apply_id,)).fetchone():
                conn.execute("INSERT INTO account(account_id,display_name,level,status,join_date,note) VALUES(?,?,?,?,?,?)",
                             (apply_id, apply_id, "待转正", "正常", now[:10], "初审报名自动建号（待转正）"))
                created_account = True
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                         (0, "申请登记新增", apply_id, aid or "未署名", now,
                          "申请登记：%s / %s / 待转正%s" % (apply_id, reg_cat, ("；自动建号（初始密码 %s@2026）" % apply_id) if created_account else "")))
            conn.commit(); return self._send(200, {"ok": True, "id": cur.lastrowid, "created_account": created_account,
                                                    "default_pw": (apply_id + "@2026") if created_account else ""})
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def _put_registration(self, conn, aid, eid, b):
        try:
            r = conn.execute("SELECT * FROM registration WHERE id=?", (eid,)).fetchone()
            if not r: return self._send(404, {"error": "记录不存在"})
            now = _now()
            action = (b.get("action") or "apply").strip()
            is_adm = is_admin(conn, aid)
            is_super = is_super_admin(conn, aid)
            if action == "authorize":
                # 授权：待授权 → 已授权（仅管理角色）
                if not is_adm:
                    return self._send(403, {"error": "无权限：仅管理角色可进行授权"})
                if (r["eval_node"] or "") != "待授权":
                    return self._send(400, {"error": "当前流程节点为「%s」，无法授权（仅「待授权」可授权）" % (r["eval_node"] or "未指定")})
                conn.execute("UPDATE registration SET eval_node=?,eval_node_time=?,updated_at=? WHERE id=?", ("已授权", now, now, eid))
                conn.commit(); return self._send(200, {"ok": True})
            if action == "submit_eval_apply":
                # 发起方提交评估申请：已授权 → 待转正评估（仅申请人本人）
                if (r["apply_id"] or "") != aid:
                    return self._send(403, {"error": "无权限：仅申请人本人可提交评估申请"})
                if (r["eval_node"] or "") != "已授权":
                    return self._send(400, {"error": "当前流程节点为「%s」，尚未达到「已授权」，无法提交评估申请" % (r["eval_node"] or "未指定")})
                conn.execute("UPDATE registration SET eval_node=?,eval_node_time=?,eval_result=?,eval_result_time=?,updated_at=? WHERE id=?",
                             ("待转正评估", now, "待评估", now, now, eid))
                conn.commit(); return self._send(200, {"ok": True})
            if action == "eval":
                # 评估操作：仅管理员/超级管理员可修改评估节点与结果
                if not is_adm:
                    return self._send(403, {"error": "无权限：仅管理角色可进行评估操作"})
                new_node = (b.get("eval_node") or r["eval_node"] or "").strip()
                if new_node and new_node not in EVAL_NODES:
                    return self._send(400, {"error": "流程节点非法：%s（应为 %s 之一）" % (new_node, " / ".join(EVAL_NODES))})
                old_idx = EVAL_NODES.index(r["eval_node"]) if (r["eval_node"] or "") in EVAL_NODES else -1
                new_idx = EVAL_NODES.index(new_node) if new_node in EVAL_NODES else -1
                node_changed = (new_node != (r["eval_node"] or ""))
                if node_changed and old_idx >= 0 and new_idx >= 0 and new_idx < old_idx and not is_super:
                    return self._send(400, {"error": "流程不可倒退：不能从「%s」回到「%s」（仅超级管理员可回退）" % (r["eval_node"], new_node)})
                # 资格待核查：满足/不满足申请资格（特殊动作）
                decision = (b.get("decision") or "").strip()
                if (r["eval_node"] or "") == "资格待核查" and decision == "不满足申请资格":
                    conn.execute("""UPDATE registration SET eval_node=?,eval_node_time=?,eval_result=?,eval_result_time=?,evaluator=?,updated_at=? WHERE id=?""",
                                 ("评估完成", now, "不通过", now, aid, now, eid))
                    conn.commit(); return self._send(200, {"ok": True})
                if (r["eval_node"] or "") == "资格待核查" and decision == "满足申请资格":
                    new_node = "待授权"
                eval_node_time = (now if node_changed else r["eval_node_time"]) or now
                # 进入「待转正评估」后自动显示为「待评估」
                eval_result = (r["eval_result"] or "").strip()
                eval_result_time = r["eval_result_time"]
                if node_changed and new_node == "待转正评估" and not eval_result:
                    eval_result = "待评估"
                    eval_result_time = now
                # 评估结果：显式修改时须流程进入「待转正评估」；一旦设定为非「待评估」仅超级管理员可修改
                # 空字符串视为「不修改结果」，避免回传空值覆盖节点流转自动置位的「待评估」
                if b.get("eval_result"):
                    val = b.get("eval_result").strip()
                    if val and val not in EVAL_RESULTS:
                        return self._send(400, {"error": "评估结果非法：%s" % val})
                    # 未变更结果值时允许保存（前端可能回传当前「待评估」）
                    if val != eval_result:
                        # 仅在「待转正评估」及「评估完成」节点允许显式修改评估结果
                        if new_node not in ("待转正评估", "评估完成"):
                            return self._send(400, {"error": "流程节点未进入「待转正评估」，无法填改评估结果"})
                        if eval_result and eval_result != "待评估" and not is_super:
                            return self._send(403, {"error": "无权限：评估结果一旦设定仅超级管理员可修改"})
                        eval_result = val
                        eval_result_time = now
                conn.execute("""UPDATE registration SET eval_node=?,eval_node_time=?,eval_result=?,eval_result_time=?,evaluator=?,updated_at=? WHERE id=?""",
                             (new_node, eval_node_time, eval_result, eval_result_time, aid, now, eid))
                # 回环：评估完成且通过转正/实习时，在权限台账建立/激活该申请人分类授权
                if new_node == "评估完成" and eval_result in ("通过转正", "实习"):
                    if apply_id := (r["apply_id"] or "").strip():
                        cat = (r["category"] or "").strip()
                        lvl = "初审"
                        conn.execute("INSERT OR IGNORE INTO account(account_id,display_name,level,status,join_date,note) VALUES(?,?,?,?,?,?)", (apply_id, apply_id, lvl, '正常', '', '新评审申请转正'))
                        # 仅当账号当前为待转正（报名自动建号）时提升为初审；已有等级保持不变
                        conn.execute("""UPDATE account SET
                            level=CASE WHEN COALESCE(level,'') IN ('','待转正') THEN ? ELSE level END,
                            status='正常',
                            note=CASE WHEN COALESCE(level,'')='待转正' THEN '新评审申请转正' ELSE note END
                            WHERE account_id=?""", (lvl, apply_id))
                        self._grant_category(conn, apply_id, cat, aid or "未署名", now)
                conn.commit(); return self._send(200, {"ok": True})
            else:
                # 申请信息修改：仅本人或管理员
                if not is_adm and (r["apply_id"] or "") != aid:
                    return self._send(403, {"error": "无权限：仅本人或管理角色可修改申请信息"})
                # 资格审查后（节点≠资格待核查），申请人/非管理员不可再修改申请信息
                if (r["eval_node"] or "") != "资格待核查" and not is_adm:
                    return self._send(403, {"error": "资格审查后申请内容已锁定，不可修改（当前节点：%s）" % (r["eval_node"] or "未指定")})
                new_apply_id = (b.get("apply_id") or r["apply_id"] or "").strip()
                # 跨权防卫：非管理员不可变更申请人百科ID
                if not is_adm and new_apply_id != (r["apply_id"] or ""):
                    return self._send(403, {"error": "无权限：不可变更申请人百科ID"})
                new_condition = (b.get("condition_type") or r["condition_type"] or "").strip()
                if new_condition and new_condition not in REG_CONDITIONS:
                    return self._send(400, {"error": "报名条件选项非法"})
                # 不允许通过申请修改接口变更评估节点/结果
                conn.execute("""UPDATE registration SET apply_id=?,qq=?,referrer=?,category=?,condition_type=?,screenshot_path=?,note=?,operator=?,updated_at=? WHERE id=?""",
                             (new_apply_id, b.get("qq", r["qq"]), b.get("referrer", r["referrer"]),
                              b.get("category", r["category"]), new_condition,
                              b.get("screenshot_path", r["screenshot_path"]), b.get("note", r["note"]), aid or "未署名", now, eid))
                conn.commit(); return self._send(200, {"ok": True})
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def _del_registration(self, eid):
        conn = get_conn()
        try:
            r = conn.execute("SELECT * FROM registration WHERE id=?", (eid,)).fetchone()
            if not r: return self._send(404, {"error": "记录不存在"})
            now = _now()
            # 如存在截图文件，一并清理
            sp = (r["screenshot_path"] or "").strip()
            if sp:
                fp = os.path.join(BASE_DIR, sp) if not os.path.isabs(sp) else sp
                try:
                    if os.path.exists(fp): os.remove(fp)
                except Exception:
                    pass
            conn.execute("DELETE FROM registration WHERE id=?", (eid,))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)", (0,"报名登记删除",r["apply_id"] or "","未署名",now,"报名登记删除：%s" % (r["apply_id"] or "")))
            conn.commit(); return self._send(200, {"ok": True})
        finally:
            conn.close()

    # ---------- 升级中审申请 / 分类扩充申请（工作流化，kind 区分；评估流程完全复用） ----------
    def _add_upgrade(self, conn, aid, b, kind="upgrade"):
        try:
            now = _now()
            tbl = KIND_TBL.get(kind, "upgrade_apply")
            apply_id = (b.get("apply_id") or "").strip()
            cat = (b.get("category") or "").strip()
            if not apply_id:
                return self._send(400, {"error": "申请人账号为必填"})
            if not cat:
                return self._send(400, {"error": "申请分类为必填"})
            is_adm = is_admin(conn, aid); is_rev = is_reviewer(conn, aid)
            # 跨权防卫：非管理/评审角色只能为自己提交
            if not (is_adm or is_rev) and apply_id != aid:
                return self._send(403, {"error": "无权限：只能提交本人的申请"})
            # 不得报名情形（封禁/限制/取消、处罚期内、近6月违规取消等）
            blk, reason = self._block_apply_reason(conn, apply_id)
            if blk:
                return self._send(400, {"error": reason})
            # 分类扩充：月度限额强控 + 同分类重报间隔（制度 3.7）
            if kind == "expand":
                mon = now[:7]
                dup_month = conn.execute("SELECT 1 FROM %s WHERE apply_id=? AND substr(apply_time,1,7)=?" % tbl, (apply_id, mon)).fetchone()
                if dup_month:
                    has_perm = conn.execute("SELECT 1 FROM permission WHERE account_id=? AND recycled=0 AND status IN ('正常','考核期','见习','实习')", (apply_id,)).fetchone()
                    if has_perm:
                        return self._send(409, {"error": "分类扩充月度限额：同一自然月仅可申请 1 个分类（%s 已占用）" % mon})
                since = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
                recent = conn.execute("SELECT 1 FROM %s WHERE apply_id=? AND category=? AND apply_time>=?" % tbl, (apply_id, cat, since)).fetchone()
                if recent:
                    return self._send(409, {"error": "该分类扩充申请 1 个月内已提交，重报须间隔 1 个月（制度 3.7.6）"})
            cur = conn.execute(
                """INSERT INTO %s(apply_id,qq,referrer,category,screenshot_path,note,operator,apply_time,eval_node,eval_node_time,eval_result,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""" % tbl,
                (apply_id, b.get("qq") or "", b.get("referrer") or "", cat,
                 b.get("screenshot_path") or "", b.get("note") or "", aid or "未署名",
                 b.get("apply_time") or now, "资格待核查", now, "待评估", now, now))
            if b.get("features") is not None:
                self._save_features(conn, kind, cur.lastrowid, b.get("features"))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                         (0, "升级申请新增" if kind == "upgrade" else "分类扩充新增", apply_id, aid or "未署名", now, "%s：%s / %s" % ("升级申请" if kind == "upgrade" else "分类扩充", apply_id, cat)))
            conn.commit(); return self._send(200, {"ok": True, "id": cur.lastrowid})
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def _put_upgrade(self, conn, aid, eid, b, kind="upgrade"):
        try:
            tbl = KIND_TBL.get(kind, "upgrade_apply")
            r = conn.execute("SELECT * FROM %s WHERE id=?" % tbl, (eid,)).fetchone()
            if not r: return self._send(404, {"error": "记录不存在"})
            now = _now()
            action = (b.get("action") or "apply").strip()
            is_adm = is_admin(conn, aid); is_rev = is_reviewer(conn, aid); is_super = is_super_admin(conn, aid)
            if action == "eval":
                if not (is_adm or is_rev):
                    return self._send(403, {"error": "无权限：仅管理/评审角色可进行节点评估操作"})
                new_node = (b.get("eval_node") or r["eval_node"] or "").strip()
                if new_node and new_node not in EVAL_NODES:
                    return self._send(400, {"error": "流程节点非法：%s（应为 %s 之一）" % (new_node, " / ".join(EVAL_NODES))})
                old_idx = EVAL_NODES.index(r["eval_node"]) if (r["eval_node"] or "") in EVAL_NODES else -1
                new_idx = EVAL_NODES.index(new_node) if new_node in EVAL_NODES else -1
                node_changed = (new_node != (r["eval_node"] or ""))
                if node_changed and old_idx >= 0 and new_idx >= 0 and new_idx < old_idx and not is_super:
                    return self._send(400, {"error": "流程不可倒退：不能从「%s」回到「%s」（仅超级管理员可回退）" % (r["eval_node"], new_node)})
                # 资格待核查：满足/不满足申请资格（特殊动作）
                decision = (b.get("decision") or "").strip()
                if (r["eval_node"] or "") == "资格待核查" and decision == "不满足申请资格":
                    conn.execute("""UPDATE %s SET eval_node=?,eval_node_time=?,eval_result=?,eval_result_time=?,evaluator=?,updated_at=? WHERE id=?""" % tbl,
                                 ("评估完成", now, "不通过", now, aid, now, eid))
                    conn.commit(); return self._send(200, {"ok": True})
                if (r["eval_node"] or "") == "资格待核查" and decision == "满足申请资格":
                    new_node = "待授权"
                node_changed = (new_node != (r["eval_node"] or ""))
                eval_node_time = (now if node_changed else r["eval_node_time"]) or now
                eval_result = (r["eval_result"] or "").strip()
                eval_result_time = r["eval_result_time"]
                # 进入「待转正评估」后自动显示为「待评估」
                if node_changed and new_node == "待转正评估" and not eval_result:
                    eval_result = "待评估"; eval_result_time = now
                # 评估结果：仅在「待转正评估」及「评估完成」节点允许显式修改；一旦非「待评估」仅超级管理员可改
                if b.get("eval_result"):
                    val = b.get("eval_result").strip()
                    if val and val not in EVAL_RESULTS:
                        return self._send(400, {"error": "评估结果非法：%s" % val})
                    if val != eval_result:
                        if new_node not in ("待转正评估", "评估完成"):
                            return self._send(400, {"error": "流程节点未进入「待转正评估」，无法填改评估结果"})
                        if eval_result and eval_result != "待评估" and not is_super:
                            return self._send(403, {"error": "无权限：评估结果一旦设定仅超级管理员可修改"})
                        eval_result = val; eval_result_time = now
                conn.execute("""UPDATE %s SET eval_node=?,eval_node_time=?,eval_result=?,eval_result_time=?,evaluator=?,updated_at=? WHERE id=?""" % tbl,
                             (new_node, eval_node_time, eval_result, eval_result_time, aid, now, eid))
                # 回环：评估完成且通过转正/实习时，在权限台账建立/激活该申请人分类授权
                if new_node == "评估完成" and eval_result in ("通过转正", "实习"):
                    if apply_id := (r["apply_id"] or "").strip():
                        self._grant_category(conn, apply_id, (r["category"] or "").strip(), aid or "未署名", now)
                conn.commit(); return self._send(200, {"ok": True})
            if action == "accept":
                if not (is_adm or is_rev):
                    return self._send(403, {"error": "无权限：仅管理/评审角色可受理申请"})
                # 受理/推进：在当前节点基础上顺序推进一个节点
                cur_node = r["eval_node"] or "资格待核查"
                # 评估阶段节点不可用「受理」推进：待转正评估→已公示由 3 角色全部提交自动进入；
                # 已公示→评估完成仅可由「评审相关负责人」确认发布（action=publish），否则评估结果将缺失
                if cur_node in ("待转正评估", "已公示", "评估完成"):
                    return self._send(400, {"error": "当前节点「%s」由评估流程推进：待转正评估/已公示阶段请通过「评」提交角色评估，已公示后由「评审相关负责人」确认发布" % cur_node})
                if cur_node == "资格待核查": new_node = "待授权"
                elif cur_node == "待授权": new_node = "已授权"
                elif cur_node == "已授权": new_node = "待转正评估"
                else:
                    return self._send(400, {"error": "当前节点「%s」已无需推进" % cur_node})
                old_idx = EVAL_NODES.index(cur_node) if cur_node in EVAL_NODES else -1
                new_idx = EVAL_NODES.index(new_node)
                if new_idx < old_idx and not is_super:
                    return self._send(400, {"error": "流程不可倒退：不能从「%s」回到更早节点" % cur_node})
                eval_result = (r["eval_result"] or "").strip()
                eval_result_time = r["eval_result_time"]
                if new_node == "待转正评估" and not eval_result:
                    eval_result = "待评估"; eval_result_time = now
                conn.execute("""UPDATE %s SET eval_node=?,eval_node_time=?,eval_result=?,eval_result_time=?,evaluator=?,op_remark=?,updated_at=? WHERE id=?""" % tbl,
                             (new_node, now, eval_result, eval_result_time, aid, (b.get("op_remark") or "").strip(), now, eid))
                conn.commit(); return self._send(200, {"ok": True})
            if action == "decline":
                if not (is_adm or is_rev):
                    return self._send(403, {"error": "无权限：仅管理/评审角色可驳回申请"})
                if (r["eval_node"] or "") != "资格待核查":
                    return self._send(400, {"error": "仅在「资格待核查」节点可执行「不满足申请资格」驳回"})
                conn.execute("""UPDATE %s SET eval_node=?,eval_node_time=?,eval_result=?,eval_result_time=?,evaluator=?,op_remark=?,updated_at=? WHERE id=?""" % tbl,
                             ("评估完成", now, "不通过", now, aid, (b.get("op_remark") or "").strip(), now, eid))
                conn.commit(); return self._send(200, {"ok": True})
            if action == "publish":
                # 仅「评审相关负责人」（含超级管理员）可从「已公示」确认发布至「评估完成」
                user_roles = get_eval_roles(conn, aid)
                if "评审相关负责人" not in user_roles and not is_super_admin(conn, aid):
                    return self._send(403, {"error": "无权限：仅「评审相关负责人」可确认发布"})
                if (r["eval_node"] or "") != "已公示":
                    return self._send(400, {"error": "当前节点为「%s」，仅「已公示」节点可确认发布" % (r["eval_node"] or "未指定")})
                eval_result = (b.get("eval_result") or "").strip()
                if eval_result not in ("通过转正", "不通过", "实习"):
                    return self._send(400, {"error": "确认发布须指定最终评估结果（通过转正/不通过/实习）"})
                conn.execute("""UPDATE %s SET eval_node=?,eval_node_time=?,eval_result=?,eval_result_time=?,evaluator=?,updated_at=? WHERE id=?""" % tbl,
                             ("评估完成", now, eval_result, now, aid, now, eid))
                # 回环：评估完成且通过转正/实习时，在权限台账建立/激活该申请人分类授权
                if eval_result in ("通过转正", "实习"):
                    apply_id = (r["apply_id"] or "").strip()
                    if apply_id:
                        self._grant_category(conn, apply_id, (r["category"] or "").strip(), aid or "未署名", now)
                conn.commit(); return self._send(200, {"ok": True})
            # 申请信息修改：仅本人或管理/评审角色
            if not (is_adm or is_rev) and (r["apply_id"] or "") != aid:
                return self._send(403, {"error": "无权限：仅本人或管理/评审角色可修改申请信息"})
            # 资格审查后（节点≠资格待核查），申请人/非管理评审角色不可再修改申请信息
            if (r["eval_node"] or "") != "资格待核查" and not (is_adm or is_rev):
                return self._send(403, {"error": "资格审查后申请内容已锁定，不可修改（当前节点：%s）" % (r["eval_node"] or "未指定")})
            new_apply_id = (b.get("apply_id") or r["apply_id"] or "").strip()
            if not (is_adm or is_rev) and new_apply_id != (r["apply_id"] or ""):
                return self._send(403, {"error": "无权限：不可变更申请人百科ID"})
            new_cat = (b.get("category") or r["category"] or "").strip()
            conn.execute("""UPDATE %s SET apply_id=?,qq=?,referrer=?,category=?,screenshot_path=?,note=?,operator=?,updated_at=? WHERE id=?""" % tbl,
                         (new_apply_id, b.get("qq", r["qq"]), b.get("referrer", r["referrer"]),
                          new_cat, b.get("screenshot_path", r["screenshot_path"]),
                          b.get("note", r["note"]), aid or "未署名", now, eid))
            if b.get("features") is not None:
                self._save_features(conn, kind, eid, b.get("features"))
            conn.commit(); return self._send(200, {"ok": True})
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def _del_upgrade(self, conn, aid, eid, kind="upgrade"):
        tbl = KIND_TBL.get(kind, "upgrade_apply"); feat = KIND_FEAT.get(kind, "upgrade_apply_feature"); ev = KIND_EVAL.get(kind, "upgrade_apply_eval")
        r = conn.execute("SELECT * FROM %s WHERE id=?" % tbl, (eid,)).fetchone()
        if not r: return self._send(404, {"error": "记录不存在"})
        is_adm = is_admin(conn, aid); is_rev = is_reviewer(conn, aid)
        if (r["apply_id"] or "") != aid and not (is_adm or is_super_admin(conn, aid)):
            return self._send(403, {"error": "无权限：仅申请人本人、管理员或超级管理员可删除"})
        now = _now()
        conn.execute("DELETE FROM %s WHERE apply_id=?" % feat, (eid,))
        conn.execute("DELETE FROM %s WHERE apply_id=?" % ev, (eid,))
        conn.execute("DELETE FROM %s WHERE id=?" % tbl, (eid,))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "升级申请删除" if kind == "upgrade" else "分类扩充删除", r["apply_id"] or "", aid or "未署名", now, "%s删除：%s" % ("升级申请" if kind == "upgrade" else "分类扩充", r["apply_id"] or "")))
        conn.commit(); return self._send(200, {"ok": True})

    def _get_upgrade_evals(self, conn, aid, apply_id, kind="upgrade"):
        tbl = KIND_TBL.get(kind, "upgrade_apply"); ev = KIND_EVAL.get(kind, "upgrade_apply_eval")
        r = conn.execute("SELECT * FROM %s WHERE id=?" % tbl, (apply_id,)).fetchone()
        if not r: return self._send(404, {"error": "申请不存在"})
        node = r["eval_node"] or ""
        public = node in ("已公示", "评估完成")
        is_rev = is_reviewer(conn, aid); is_adm = is_admin(conn, aid)
        user_roles = get_eval_roles(conn, aid)
        # 公示后（已公示/评估完成）评估留痕对公众（所有登录用户）可见；公示前仅评审/管理角色可查看
        if not public and not (is_rev or is_adm or user_roles or is_super_admin(conn, aid)):
            return self._send(403, {"error": "无权限：仅评审/管理角色或已绑定评审身份者可查看评估详情（公示后对公众开放）"})
        rows = conn.execute("SELECT * FROM %s WHERE apply_id=? ORDER BY id" % ev, (apply_id,)).fetchall()
        user_roles = get_eval_roles(conn, aid)
        out = []
        for x in rows:
            d = dict(x)
            role = d.get("evaluator_role")
            # 公示前理由隔离：非公示状态且非「评审相关负责人」本人，只能看自己绑定角色的理由
            if not public and "评审相关负责人" not in user_roles and role not in user_roles:
                d["reason"] = "（公示前不可查看其他角色理由）"
                d["reason_masked"] = True
            out.append(d)
        return self._send(200, dict(rows=out, node=node, eval_result=r["eval_result"], public=public, my_roles=user_roles))

    def _add_upgrade_eval(self, conn, aid, apply_id, b, kind="upgrade"):
        try:
            tbl = KIND_TBL.get(kind, "upgrade_apply"); ev = KIND_EVAL.get(kind, "upgrade_apply_eval")
            r = conn.execute("SELECT * FROM %s WHERE id=?" % tbl, (apply_id,)).fetchone()
            if not r: return self._send(404, {"error": "申请不存在"})
            is_rev = is_reviewer(conn, aid); is_adm = is_admin(conn, aid)
            user_roles = get_eval_roles(conn, aid)
            is_sa = is_super_admin(conn, aid)
            if not (is_rev or is_adm or user_roles or is_sa):
                return self._send(403, {"error": "无权限：仅评审/管理角色或已绑定评审身份者可参与评估"})
            role = (b.get("evaluator_role") or "").strip()
            if role not in EVAL_REVIEW_ROLES:
                return self._send(400, {"error": "评估角色非法：%s" % role})
            # 不可跨权：提交者必须与 eval_role_assign 中绑定的角色一致（超级管理员亦不例外，
            # 其仅隐含「评审相关负责人」身份），杜绝以任意角色代他人提交评估
            if role not in user_roles:
                return self._send(403, {"error": "无权限：您未绑定「%s」身份，不可提交该角色评估" % role})
            node = r["eval_node"] or ""
            if node not in ("待转正评估", "已公示"):
                return self._send(400, {"error": "当前流程节点为「%s」，不在可评估/修改状态" % (node or "未指定")})
            # 公示后仅允许超级管理员修改（原则上公示期应只读，但超级管理员可修正）
            if node == "已公示" and not is_super_admin(conn, aid):
                return self._send(400, {"error": "已进入公示状态，不可修改评估结果（需超级管理员撤回公示）"})
            agree = (b.get("agree") or "").strip()
            if agree not in ("同意", "不同意"):
                return self._send(400, {"error": "是否同意授予 必须为「同意」或「不同意」"})
            reason = (b.get("reason") or "").strip()
            if not reason:
                return self._send(400, {"error": "评估理由为必填"})
            # 同一角色同一申请覆盖式更新（一人一票）
            existing = conn.execute("SELECT id FROM %s WHERE apply_id=? AND evaluator_role=?" % ev, (apply_id, role)).fetchone()
            if existing:
                conn.execute("UPDATE %s SET account_id=?,agree=?,reason=?,eval_time=?,created_at=? WHERE id=?" % ev,
                             (aid, agree, reason, _now(), _now(), existing["id"]))
            else:
                conn.execute("INSERT INTO %s(apply_id,evaluator_role,account_id,agree,reason,eval_time,created_at) VALUES(?,?,?,?,?,?,?)" % ev,
                             (apply_id, role, aid, agree, reason, _now(), _now()))
            # 3 人全部提交后从「待转正评估」自动进入「已公示」
            evals = conn.execute("SELECT DISTINCT evaluator_role FROM %s WHERE apply_id=?" % ev, (apply_id,)).fetchall()
            submitted_roles = {x["evaluator_role"] for x in evals}
            if submitted_roles >= set(EVAL_REVIEW_ROLES) and node == "待转正评估":
                conn.execute("UPDATE %s SET eval_node=?,eval_node_time=?,updated_at=? WHERE id=?" % tbl,
                             ("已公示", _now(), _now(), apply_id))
            conn.commit(); return self._send(200, {"ok": True})
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def _del_upgrade_eval(self, conn, aid, apply_id, kind="upgrade"):
        tbl = KIND_TBL.get(kind, "upgrade_apply"); ev = KIND_EVAL.get(kind, "upgrade_apply_eval")
        r = conn.execute("SELECT * FROM %s WHERE id=?" % tbl, (apply_id,)).fetchone()
        if not r: return self._send(404, {"error": "申请不存在"})
        node = r["eval_node"] or ""
        if node != "待转正评估":
            return self._send(400, {"error": "当前节点为「%s」，仅「待转正评估」阶段可撤回评估" % node})
        is_rev = is_reviewer(conn, aid); is_adm = is_admin(conn, aid)
        user_roles = get_eval_roles(conn, aid)
        if not (is_rev or is_adm or user_roles):
            return self._send(403, {"error": "无权限：仅评审/管理角色或已绑定评审身份者可操作"})
        # 超级管理员可撤回任意角色；其他账号只能撤回自己绑定角色的评估
        if is_super_admin(conn, aid):
            conn.execute("DELETE FROM %s WHERE apply_id=?" % ev, (apply_id,))
        else:
            if not user_roles:
                return self._send(403, {"error": "无权限：您未绑定任何评审角色"})
            placeholders = ",".join("?"*len(user_roles))
            conn.execute("DELETE FROM %s WHERE apply_id=? AND evaluator_role IN (%s)" % (ev, placeholders),
                         (apply_id,) + tuple(user_roles))
        conn.commit(); return self._send(200, {"ok": True})

    def _upload_screenshot(self):
        conn = get_conn()
        try:
            aid = self._require_login(conn)
            if aid is None: return
            ctype = self.headers.get("Content-Type", "")
            if not ctype.startswith("multipart/form-data"):
                return self._send(400, {"error": "请使用 multipart/form-data 上传文件"})
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0:
                return self._send(400, {"error": "请求体为空"})
            body = self.rfile.read(length)
            # Python 3.13 已移除 cgi 模块，改用 email 解析 multipart/form-data
            raw = b"Content-Type: " + ctype.encode("utf-8", "ignore") + b"\r\n\r\n" + body
            msg = BytesParser().parsebytes(raw)
            filename = None; data = None
            for part in msg.walk():
                fn = part.get_filename()
                if fn:
                    filename = fn
                    data = part.get_payload(decode=True)
                    break
            if not filename or data is None:
                return self._send(400, {"error": "缺少文件字段 file 或文件为空"})
            ext = os.path.splitext(filename)[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
                return self._send(400, {"error": "仅支持图片文件（png/jpg/jpeg/gif/webp/bmp）"})
            if len(data) > 10 * 1024 * 1024:
                return self._send(400, {"error": "文件大小超过 10MB 限制"})
            subdir = datetime.datetime.now().strftime("%Y-%m")
            save_dir = os.path.join(SCREENSHOT_DIR, subdir)
            os.makedirs(save_dir, exist_ok=True)
            unique = secrets.token_hex(8)
            base = re.sub(r"[^\w\-_.]", "_", os.path.splitext(os.path.basename(filename))[0])[:32]
            saved = "%s_%s%s" % (unique, base or "img", ext)
            rel = "data/screenshots/%s/%s" % (subdir, saved)
            abs_path = os.path.join(BASE_DIR, rel)
            with open(abs_path, "wb") as f:
                f.write(data)
            return self._send(200, {"ok": True, "path": rel, "url": "/api/screenshots/%s/%s" % (subdir, saved)})
        except Exception as e:
            return self._send(500, {"error": str(e)})
        finally:
            try: conn.close()
            except: pass

    # ---- 组长 / 委员会 批量导入 ----
    def _import_leaders(self, conn, b):
        rows = b.get("rows", [])
        if not rows: return self._send(400, {"error": "无导入数据"})
        now = _now(); added, skipped = 0, 0
        for it in rows:
            aid = (it.get("account_id") or "").strip()
            if not aid: continue
            role = (it.get("role") or "分类组长").strip() or "分类组长"
            time = (it.get("time") or "2026-09-01").strip() or "2026-09-01"
            status = (it.get("status") or "在任").strip() or "在任"
            note = (it.get("note") or "").strip()
            owner = (it.get("owner") or "系统导入").strip()
            if conn.execute("SELECT 1 FROM leader_record WHERE account_id=? AND role=?", (aid, role)).fetchone():
                skipped += 1; continue
            conn.execute("INSERT INTO leader_record(account_id,role,status,time,owner,note,operator,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                         (aid, role, status, time, owner, note, owner, now, now))
            added += 1
        conn.commit(); return self._send(200, dict(ok=True, added=added, skipped=skipped))

    # ---- 指标配置删除 ----
    def _del_config(self, cid):
        conn = get_conn()
        try:
            r = conn.execute("SELECT * FROM assess_config WHERE id=?", (cid,)).fetchone()
            if not r: return self._send(404, {"error": "指标不存在"})
            now = _now()
            conn.execute("DELETE FROM assess_config WHERE id=?", (cid,))
            conn.execute("INSERT INTO change_log(permission_id,action,operator,change_time,detail) VALUES(?,?,?,?,?)",
                         (0, "指标配置删除", "未署名", now, "删除指标：" + (r["name"] or "")))
            conn.commit(); return self._send(200, {"ok": True})
        finally:
            conn.close()

    # ---- 分类扩充审核（组长/委员会权限分级） + 回环授权 ----
    def _grant_category(self, conn, account_id, category, operator, now):
        """回环：在权限台账为账号授予某分类（特色方向）授权；已存在则激活。"""
        if not category: return
        acct = conn.execute("SELECT level FROM account WHERE account_id=?", (account_id,)).fetchone()
        level = acct["level"] if acct else "中审"
        dup = conn.execute("SELECT id FROM permission WHERE account_id=? AND category=? AND recycled=0", (account_id, category)).fetchone()
        if dup:
            conn.execute("UPDATE permission SET status='正常',level=?,updated_at=? WHERE id=?", (level, now, dup["id"]))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                         (dup["id"], "权限激活", account_id, operator, now, "分类扩充通过后激活授权：%s / %s / %s" % (account_id, category, level)))
            return
        # 中审新取得分类权限先进入见习期（制度 5.6：见习 1 个月，期满无严重违规转正）
        prob_until = (datetime.datetime.now() + datetime.timedelta(days=PROBATION_DAYS)).strftime("%Y-%m-%d")
        cur = conn.execute("""INSERT INTO permission(account_id,category,level,status,effect_date,expire_date,source,system_version,operator,created_at,updated_at,probation_until)
                             VALUES(?,?,?,'见习',?,'',?,?,?,?,?,?)""",
                          (account_id, category, level, now[:10], "回环授权", SYSTEM_VERSION, operator, now, now, prob_until))
        pid = cur.lastrowid
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (pid, "权限新增(见习)", account_id, operator, now, "分类扩充/追加通过后授权（见习至 %s）：%s / %s / %s" % (prob_until, account_id, category, level)))

    # ---- 升级 / 扩分类 / 官方名单 / 组长委员会 通用 CRUD ----
    # ---------------------------------------------------------------- 抽查记录（制度 7.1）
    def _spot_list(self, conn, period=None, acct=None):
        where = "WHERE 1=1"; params = []
        if period: where += " AND period=?"; params.append(period)
        if acct: where += " AND account_id=?"; params.append(acct)
        rows = conn.execute("SELECT * FROM spot_check %s ORDER BY period DESC, id DESC" % where, params).fetchall()
        out = [dict(r) for r in rows]
        tot_need = sum(r["sample_need"] or 0 for r in out)
        tot_done = sum(r["sampled"] or 0 for r in out)
        tot_prob = sum(r["problem_versions"] or 0 for r in out)
        return dict(rows=out, summary=dict(
            count=len(out), sample_need=tot_need, sampled=tot_done, problem=tot_prob,
            finish_rate=round(tot_done / tot_need * 100, 1) if tot_need else 0.0,
            problem_rate=round(tot_prob / tot_done * 100, 1) if tot_done else 0.0,
            rule="制度 7.1：自然月内按总评审版本数 10% 抽查，主分类占抽样量 60%，副分类合计 40%"))

    def _add_spot_check(self, conn, b):
        acct = (b.get("account_id") or "").strip()
        period = (b.get("period") or "").strip()
        if not acct:
            return self._send(400, {"error": "缺少被抽查账号"})
        if not period:
            return self._send(400, {"error": "缺少抽查期间（YYYY-MM）"})
        if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (acct,)).fetchone():
            return self._send(400, {"error": "账号不存在：%s" % acct})
        lvl = (b.get("level") or "").strip()
        if lvl and lvl not in VIOLATION_LEVELS:
            return self._send(400, {"error": "违规等级非法：%s（应为 %s 之一）" % (lvl, " / ".join(VIOLATION_LEVELS))})
        total = int(b.get("total_versions") or 0)
        need, main, sub = spot_quota(total)
        now = _now()
        cur = conn.execute(
            """INSERT INTO spot_check(period,account_id,category,total_versions,sample_need,main_need,sub_need,
               sampled,problem_versions,level,handling,is_official,checker,check_time,note,operator,recused,recuser,recuse_reason,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (period, acct, (b.get("category") or "").strip(), total, need, main, sub,
             int(b.get("sampled") or 0), int(b.get("problem_versions") or 0), lvl,
             (b.get("handling") or "").strip(), 1 if b.get("is_official") else 0,
             (b.get("checker") or "").strip(), (b.get("check_time") or now[:10]),
             (b.get("note") or "").strip(), (b.get("operator") or "未署名"),
             1 if b.get("recused") else 0, (b.get("recuser") or "").strip(), (b.get("recuse_reason") or "").strip(),
             now, now))
        conn.commit()
        return self._send(200, {"ok": True, "id": cur.lastrowid, "sample_need": need, "main_need": main, "sub_need": sub})

    def _put_spot_check(self, conn, rid, b):
        r = conn.execute("SELECT * FROM spot_check WHERE id=?", (rid,)).fetchone()
        if not r:
            return self._send(404, {"error": "抽查记录不存在"})
        now = _now()
        lvl = (b.get("level", r["level"]) or "").strip()
        if lvl and lvl not in VIOLATION_LEVELS:
            return self._send(400, {"error": "违规等级非法：%s（应为 %s 之一）" % (lvl, " / ".join(VIOLATION_LEVELS))})
        total = int(b.get("total_versions", r["total_versions"]) or 0)
        need, main, sub = spot_quota(total)
        conn.execute(
            """UPDATE spot_check SET period=?,account_id=?,category=?,total_versions=?,sample_need=?,main_need=?,sub_need=?,
               sampled=?,problem_versions=?,level=?,handling=?,is_official=?,checker=?,check_time=?,note=?,operator=?,recused=?,recuser=?,recuse_reason=?,updated_at=? WHERE id=?""",
            (b.get("period", r["period"]), b.get("account_id", r["account_id"]), b.get("category", r["category"]),
             total, need, main, sub,
             int(b.get("sampled", r["sampled"]) or 0), int(b.get("problem_versions", r["problem_versions"]) or 0),
             lvl, b.get("handling", r["handling"]), 1 if b.get("is_official", r["is_official"]) else 0,
             b.get("checker", r["checker"]), b.get("check_time", r["check_time"]),
             b.get("note", r["note"]), b.get("operator", r["operator"]),
             1 if b.get("recused", r["recused"]) else 0, (b.get("recuser", r["recuser"]) or ""),
             (b.get("recuse_reason", r["recuse_reason"]) or ""), now, rid))
        conn.commit()
        return self._send(200, {"ok": True, "sample_need": need, "main_need": main, "sub_need": sub})

    # ---------------------------------------------------------------- 再训与复权（制度 6.4）
    def _reinstate_list(self, conn, acct=None, status=None):
        where = "WHERE 1=1"; params = []
        if acct: where += " AND account_id=?"; params.append(acct)
        if status: where += " AND status=?"; params.append(status)
        rows = conn.execute("SELECT * FROM reinstate_apply %s ORDER BY id DESC" % where, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            rule = REINSTATE_RULES.get(d["target_level"], REINSTATE_RULES["初审"])
            d["rule"] = rule
            d["ver_ok"] = rule["ver_min"] <= int(d["official_versions"] or 0) <= rule["ver_max"]
            d["acc_ok"] = float(d["accuracy"] or 0) >= rule["accuracy"]
            d["main_ok"] = (not rule["main_min"]) or int(d["main_cat_versions"] or 0) >= rule["main_min"]
            out.append(d)
        return dict(rows=out, levels=list(REINSTATE_RULES.keys()), statuses=REINSTATE_STATUS,
                    rule_note="制度 6.4：复权须先恢复初审再恢复中审，不得跨级；初审官方任务版本 300–600，中审 150–300 且主分类月度≥30；正确率均须≥95%")

    def _add_reinstate(self, conn, b):
        acct = (b.get("account_id") or "").strip()
        lv = (b.get("target_level") or "初审").strip()
        if not acct:
            return self._send(400, {"error": "缺少申请人账号"})
        if lv not in REINSTATE_RULES:
            return self._send(400, {"error": "复权目标等级非法：%s（应为 初审 / 中审）" % lv})
        if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (acct,)).fetchone():
            return self._send(400, {"error": "账号不存在：%s" % acct})
        now = _now()
        # 共同规则 2：失败后半年内不受理
        blk = conn.execute("SELECT block_until FROM reinstate_apply WHERE account_id=? AND COALESCE(block_until,'')!='' ORDER BY id DESC LIMIT 1", (acct,)).fetchone()
        if blk and (blk["block_until"] or "") > now[:10]:
            return self._send(400, {"error": "该账号处于复权限制期，%s 前不受理培训申请（制度 6.4 共同规则2）" % blk["block_until"]})
        # 共同规则 3：本自然年取消评审权超过 2 次不再受理
        year_start = now[:4] + "-01-01"
        cancels = conn.execute(
            "SELECT COUNT(*) c FROM violation_record WHERE account_id=? AND penalty IN ('取消权限','永久封禁') "
            "AND COALESCE(status,'生效')!='已撤销' AND COALESCE(created_at,penalty_time)>=?", (acct, year_start)).fetchone()["c"]
        if cancels > 2:
            return self._send(400, {"error": "该账号本自然年已被取消评审权 %d 次（超过 2 次），不再受理培训申请（制度 6.4 共同规则3）" % cancels})
        # 递进校验：中审须先完成初审复权且满 1 个月
        if lv == "中审":
            prior = conn.execute(
                "SELECT result_time FROM reinstate_apply WHERE account_id=? AND target_level='初审' AND status='已复权' "
                "ORDER BY result_time DESC LIMIT 1", (acct,)).fetchone()
            if not prior:
                return self._send(400, {"error": "不得跨级复权：须先完成「初审」复权（制度 6.4）"})
            pr = (prior["result_time"] or "")[:10]
            if pr:
                try:
                    d0 = datetime.datetime.strptime(pr, "%Y-%m-%d")
                    if (datetime.datetime.now() - d0).days < 30:
                        return self._send(400, {"error": "初审复权（%s）未满 1 个月，暂不可申请中审复权（制度 6.4）" % pr})
                except Exception:
                    pass
        cur = conn.execute(
            """INSERT INTO reinstate_apply(account_id,category,target_level,status,apply_time,official_versions,
               main_cat_versions,accuracy,extend_count,cancel_count,block_until,owner,note,operator,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (acct, (b.get("category") or "").strip(), lv, "待审核", now[:10],
             int(b.get("official_versions") or 0), int(b.get("main_cat_versions") or 0),
             float(b.get("accuracy") or 0), 0, cancels, "",
             (b.get("owner") or acct), (b.get("note") or "").strip(),
             (b.get("operator") or "未署名"), now, now))
        conn.commit()
        return self._send(200, {"ok": True, "id": cur.lastrowid})

    def _put_reinstate(self, conn, rid, b):
        r = conn.execute("SELECT * FROM reinstate_apply WHERE id=?", (rid,)).fetchone()
        if not r:
            return self._send(404, {"error": "复权申请不存在"})
        now = _now()
        lv = (b.get("target_level", r["target_level"]) or "").strip()
        if lv not in REINSTATE_RULES:
            return self._send(400, {"error": "复权目标等级非法：%s" % lv})
        rule = REINSTATE_RULES[lv]
        new_status = b.get("status", r["status"])
        if new_status not in REINSTATE_STATUS:
            return self._send(400, {"error": "状态非法：%s（应为 %s 之一）" % (new_status, " / ".join(REINSTATE_STATUS))})
        ver = int(b.get("official_versions", r["official_versions"]) or 0)
        main_v = int(b.get("main_cat_versions", r["main_cat_versions"]) or 0)
        acc = float(b.get("accuracy", r["accuracy"]) or 0)
        ext = int(b.get("extend_count", r["extend_count"]) or 0)
        block_until = b.get("block_until", r["block_until"]) or ""
        result_time = r["result_time"] or ""
        # 置为已复权：校验门槛（制度 6.4）
        if new_status == "已复权":
            if not (rule["ver_min"] <= ver <= rule["ver_max"]):
                return self._send(400, {"error": "%s复权要求官方任务版本 %d–%d 个，当前 %d 个（制度 6.4）" % (lv, rule["ver_min"], rule["ver_max"], ver)})
            if rule["main_min"] and main_v < rule["main_min"]:
                return self._send(400, {"error": "%s复权要求主分类月度特色/初优评审≥%d 个，当前 %d 个（制度 6.4）" % (lv, rule["main_min"], main_v)})
            if acc < rule["accuracy"]:
                return self._send(400, {"error": "复权期内评审正确率须≥%s%%，当前 %s%%（制度 6.4）" % (rule["accuracy"], acc)})
            # 递进校验
            if rule["need_prior"]:
                prior = conn.execute(
                    "SELECT result_time FROM reinstate_apply WHERE account_id=? AND target_level='初审' AND status='已复权' "
                    "AND id!=? ORDER BY result_time DESC LIMIT 1", (r["account_id"], rid)).fetchone()
                if not prior:
                    return self._send(400, {"error": "不得跨级复权：须先完成「初审」复权（制度 6.4）"})
            result_time = now
            # 恢复权限：置为正常并同步等级
            q = "UPDATE permission SET status='正常', level=?, updated_at=? WHERE account_id=? AND recycled=0 AND status IN ('已回收','停审','降级')"
            params = [lv, now, r["account_id"]]
            if r["category"]:
                q += " AND category=?"; params.append(r["category"])
            conn.execute(q, params)
        # 置为已失败：首次延长 1 个月，再次失败半年内不受理
        if new_status == "已失败":
            ext += 1
            if ext >= 2:
                block_until = (datetime.datetime.now() + datetime.timedelta(days=182)).strftime("%Y-%m-%d")
            result_time = now
        conn.execute(
            """UPDATE reinstate_apply SET account_id=?,category=?,target_level=?,status=?,official_versions=?,
               main_cat_versions=?,accuracy=?,extend_count=?,block_until=?,result_time=?,owner=?,note=?,operator=?,updated_at=? WHERE id=?""",
            (b.get("account_id", r["account_id"]), b.get("category", r["category"]), lv, new_status,
             ver, main_v, acc, ext, block_until, result_time,
             b.get("owner", r["owner"]), b.get("note", r["note"]),
             b.get("operator", r["operator"]), now, rid))
        conn.commit()
        return self._send(200, {"ok": True, "extend_count": ext, "block_until": block_until})

    # ---------------------------------------------------------------- 连续未达标预警（制度 6.1）
    def _underperform(self, conn, months=6):
        months = max(1, min(int(months or 6), 24))
        periods = [r[0] for r in conn.execute(
            "SELECT DISTINCT period FROM assess_record ORDER BY period DESC LIMIT ?", (months,)).fetchall()]
        periods = sorted(periods)
        cfg = conn.execute("SELECT * FROM assess_config ORDER BY sort_order").fetchall()
        out = []
        for row in conn.execute("SELECT DISTINCT account_id FROM assess_record").fetchall():
            acct = row["account_id"]
            streak = 0; max_streak = 0; seq = []
            for p in periods:
                rec = conn.execute("SELECT * FROM assess_record WHERE account_id=? AND period=?", (acct, p)).fetchone()
                ex = conn.execute("SELECT * FROM assess_exemption WHERE account_id=? AND period=?", (acct, p)).fetchone()
                if not rec:
                    streak = 0
                    seq.append(dict(period=p, status="无记录"))
                    continue
                if ex and ex["mode"] == "免考核":
                    seq.append(dict(period=p, status="免考核"))   # 不计入连续月数
                    continue
                d = dict(rec); _, ok, _ = assess_eval(d, cfg)
                if ok:
                    streak = 0
                    seq.append(dict(period=p, status="达标"))
                else:
                    streak += 1
                    max_streak = max(max_streak, streak)
                    seq.append(dict(period=p, status="未达标", veto=1 if d["veto"] else 0))
            if max_streak >= 1:
                actionable = max_streak >= 2
                suggested = ("取消评审权" if max_streak >= 3 else "降级") if actionable else ""
                out.append(dict(account_id=acct, streak=max_streak,
                                action=("降级/取消评审权" if max_streak >= 2 else "提醒"),
                                actionable=actionable, suggested_action=suggested, seq=seq))
        out.sort(key=lambda x: -x["streak"])
        return dict(rows=out, periods=periods, threshold=2,
                    note="制度 6.1：单月未达标予以提醒；连续 2 个月未达标降级或取消评审权（免考核期不计入连续月数）。"
                         "系统仅出预警清单与处置建议，实际降级/取消须管理角色在「连续未达标」页逐条确认执行（确认式，不自动执行）。")

    def _check_veto(self, b):
        """一票否决项校验（制度 5.5）：勾选否决必须选择 8 项法定情形之一。"""
        if not b.get("veto"):
            return None
        reason = (b.get("veto_reason") or "").strip()
        if not reason:
            return "已勾选一票否决，须选择具体否决项（制度 5.5 共 8 项）"
        if reason not in VETO_ITEMS:
            return "否决项非法：%s（须为制度 5.5 规定的 8 项之一）" % reason
        return None

    # ---- 4.4② 再训要求标记（联动复权前置） ----
    def _set_need_retrain(self, conn, account_id, reason):
        """账号因降级/取消权限（6.3）或连续未达标（6.1）被处置后，须先完成再训（6.6 指南复训）方可复权。"""
        if not account_id:
            return
        conn.execute("UPDATE account SET need_retrain=1 WHERE account_id=?", (account_id,))

    # ---- 4.4③ 蝌蚪身份（派生：持有 实习/见习 权限即蝌蚪；转正后丧失） ----
    def _tadpole_list(self, conn):
        rows = conn.execute(
            "SELECT id,account_id,category,level,status,expire_date,probation_until FROM permission "
            "WHERE recycled=0 AND status IN ('实习','见习') ORDER BY account_id, category").fetchall()
        by_acct = {}
        for p in rows:
            acct = p["account_id"]
            if acct not in by_acct:
                by_acct[acct] = dict(account_id=acct, tadpole_status="蝌蚪", permissions=[], tadpole_until="")
            by_acct[acct]["permissions"].append(dict(id=p["id"], category=p["category"], level=p["level"],
                                                     status=p["status"], expire_date=p["expire_date"] or "",
                                                     probation_until=p["probation_until"] or ""))
            until = p["expire_date"] or p["probation_until"] or ""
            if until and (not by_acct[acct]["tadpole_until"] or until > by_acct[acct]["tadpole_until"]):
                by_acct[acct]["tadpole_until"] = until
        return dict(rows=list(by_acct.values()),
                    note="蝌蚪身份 = 持有 实习/见习 权限的新训成员（制度 5.6/4.4③）；转正为正常即丧失蝌蚪身份")

    # ---- 4.4② 再训要求清单 ----
    def _need_retrain_list(self, conn):
        rows = conn.execute("SELECT account_id FROM account WHERE need_retrain=1 ORDER BY account_id").fetchall()
        out = []
        for r in rows:
            acct = r["account_id"]
            reason = ""
            v = conn.execute(
                "SELECT penalty,level FROM violation_record WHERE account_id=? AND penalty IN ('降级','取消权限','永久封禁') "
                "AND COALESCE(status,'生效')='生效' ORDER BY COALESCE(created_at,penalty_time) DESC LIMIT 1", (acct,)).fetchone()
            if v:
                reason = "违规处分（%s%s）" % (v["penalty"], ("/" + v["level"] if v["level"] else ""))
            out.append(dict(account_id=acct, reason=reason))
        return dict(rows=out,
                    note="须先完成「指南复训」(制度 6.6) 且复训状态=已完成，方可申请复权（制度 4.4② 再训要求）")

    # ---- 6.6 指南大版本迭代复训 ----
    def _retrain_list(self, conn, guide_version=None, status=None):
        where = "WHERE 1=1"; params = []
        if guide_version:
            where += " AND guide_version=?"; params.append(guide_version)
        if status:
            where += " AND status=?"; params.append(status)
        rows = conn.execute("SELECT * FROM retrain_record %s ORDER BY id DESC" % where, params).fetchall()
        return dict(rows=[dict(r) for r in rows], statuses=RETRAIN_STATUSES,
                    note="制度 6.6：指南大版本迭代后须组织复训并记录参与人与结果")

    def _add_retrain(self, conn, b):
        gv = (b.get("guide_version") or "").strip()
        if not gv:
            return self._send(400, {"error": "请填写指南版本（如 V20260904B）"})
        now = _now()
        cur = conn.execute(
            """INSERT INTO retrain_record(guide_version,title,participants,start_date,end_date,status,
               pass_count,total_count,operator,note,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (gv, (b.get("title") or "").strip(), (b.get("participants") or "").strip(),
             (b.get("start_date") or "").strip(), (b.get("end_date") or "").strip(),
             (b.get("status") or "待开展").strip(),
             int(b.get("pass_count") or 0), int(b.get("total_count") or 0),
             (b.get("operator") or "未署名"), (b.get("note") or "").strip(), now, now))
        conn.commit()
        return self._send(200, {"ok": True, "id": cur.lastrowid})

    def _put_retrain(self, conn, rid, b):
        r = conn.execute("SELECT * FROM retrain_record WHERE id=?", (rid,)).fetchone()
        if not r:
            return self._send(404, {"error": "复训记录不存在"})
        now = _now()
        st = (b.get("status", r["status"]) or "待开展").strip()
        if st not in RETRAIN_STATUSES:
            return self._send(400, {"error": "复训状态非法：%s（应为 %s 之一）" % (st, " / ".join(RETRAIN_STATUSES))})
        conn.execute(
            """UPDATE retrain_record SET guide_version=?,title=?,participants=?,start_date=?,end_date=?,status=?,
               pass_count=?,total_count=?,operator=?,note=?,updated_at=? WHERE id=?""",
            (b.get("guide_version", r["guide_version"]), b.get("title", r["title"]),
             b.get("participants", r["participants"]), b.get("start_date", r["start_date"]),
             b.get("end_date", r["end_date"]), st,
             int(b.get("pass_count", r["pass_count"]) or 0), int(b.get("total_count", r["total_count"]) or 0),
             b.get("operator", r["operator"]), b.get("note", r["note"]), now, rid))
        # 复训完成：清除参与人的再训要求（制度 4.4②），解除复权前置
        if st == "已完成":
            for acct in [x.strip() for x in (r["participants"] or "").replace("；", ";").split(";") if x.strip()]:
                if conn.execute("SELECT 1 FROM account WHERE account_id=? AND need_retrain=1", (acct,)).fetchone():
                    conn.execute("UPDATE account SET need_retrain=0 WHERE account_id=?", (acct,))
                    conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                                 (0, "再训完成解除", acct, (b.get("operator") or "未署名"), now,
                                  "复训#%s 已完成，解除再训要求（制度 4.4②）" % rid))
        conn.commit()
        return self._send(200, {"ok": True})

    def _del_retrain(self, conn, rid):
        r = conn.execute("SELECT * FROM retrain_record WHERE id=?", (rid,)).fetchone()
        if not r:
            return self._send(404, {"error": "复训记录不存在"})
        conn.execute("DELETE FROM retrain_record WHERE id=?", (rid,))
        conn.commit()
        return self._send(200, {"ok": True})

    # ---- 6.1 连续未达标确认式降级（仅管理角色显式执行，不自动执行） ----
    def _execute_underperform(self, conn, b):
        acct = (b.get("account_id") or "").strip()
        action = (b.get("action") or "").strip()
        if not acct:
            return self._send(400, {"error": "缺少账号"})
        if action not in UNDERPERFORM_ACTIONS:
            return self._send(400, {"error": "处置动作非法：%s（应为 降级 / 取消评审权）" % action})
        if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (acct,)).fetchone():
            return self._send(400, {"error": "账号不存在：%s" % acct})
        # 确认式前置：仅当该账号当前触发连续未达标降级条件（>=2 期）才允许执行，避免误伤
        up = self._underperform(conn, 6)
        hit = next((x for x in up["rows"] if x["account_id"] == acct and x.get("actionable")), None)
        if not hit:
            return self._send(400, {"error": "账号 %s 当前未触发连续未达标降级条件（连续未达标<2期），不可执行" % acct})
        now = _now()
        if action == "降级":
            n = conn.execute("UPDATE permission SET status='降级', updated_at=? WHERE account_id=? AND recycled=0 AND status IN ('正常','考核期','见习','实习')", (now, acct)).rowcount
        else:  # 取消评审权
            n = conn.execute("UPDATE permission SET status='已回收', recycled=1, expire_date=?, updated_at=? WHERE account_id=? AND recycled=0 AND status IN ('正常','考核期','见习','实习')", (now[:10], now, acct)).rowcount
        self._set_need_retrain(conn, acct, "连续未达标%s（制度 6.1）" % action)
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "连续未达标处置", acct, (b.get("operator") or "未署名"), now,
                      "连续未达标 %d 期，管理确认执行：%s，影响权限 %d 条（制度 6.1）；须先完成再训方可复权" % (hit["streak"], action, n)))
        conn.commit()
        return self._send(200, {"ok": True, "action": action, "affected": n, "streak": hit["streak"]})

    def _gen_add(self, conn, meta, b):
        try:
            now = _now()
            # 报名资格与前置校验（制度 4.4 / 6.2）
            # 注：分类扩充月度限额 / 同分类重报间隔 已迁移至 _add_upgrade(kind="expand")；
            # 升级中审 / 分类扩充的不得报名情形统一在此校验（account_id 即申请表单的 apply_id）。
            if meta["t"] == "upgrade_apply":
                ua = (b.get("account_id") or "").strip()
                # C3：不得报名情形（封禁/限制/取消、处罚期内、近6月违规取消等）
                blk, why = self._block_apply_reason(conn, ua)
                if blk:
                    return self._send(403, {"error": why})
            # C2：升级申请前置条件（制度 6.2）
            if meta["t"] == "upgrade_apply":
                ua = (b.get("account_id") or "").strip()
                to_lv = (b.get("to_level") or "").strip()
                if to_lv == "中审":
                    ac = conn.execute("SELECT level FROM account WHERE account_id=?", (ua,)).fetchone()
                    if ac and ac["level"] in ("中审", "高审"):
                        return self._send(409, {"error": "账号当前等级为「%s」，无需再申请中审升级" % ac["level"]})
                    first_j = conn.execute(
                        "SELECT MIN(effect_date) AS d FROM permission WHERE account_id=? AND level='初审' AND recycled=0 "
                        "AND status IN ('正常','考核期','见习','实习')", (ua,)).fetchone()
                    if not first_j or not first_j["d"]:
                        return self._send(400, {"error": "升级中审须先取得初审授权（制度 6.2）"})
                    try:
                        eff = datetime.datetime.strptime(first_j["d"][:10], "%Y-%m-%d")
                    except Exception:
                        eff = None
                    if eff and (datetime.datetime.now() - eff).days < 30:
                        return self._send(400, {"error": "初审授权未满 1 个月，暂不可申请中审（制度 6.2）"})
                elif to_lv == "高审":
                    ac = conn.execute("SELECT level FROM account WHERE account_id=?", (ua,)).fetchone()
                    if not ac or ac["level"] not in ("中审", "高审"):
                        return self._send(400, {"error": "升级高审须先取得中审（制度 6.2）"})
            # 一票否决项校验（制度 5.5）
            if meta["t"] == "assess_record":
                verr = self._check_veto(b)
                if verr:
                    return self._send(400, {"error": verr})
            cols = meta["f"]; vals = []
            for f in cols:
                if meta.get("auto_time") == f:
                    vals.append(now)                      # 申请时间提交时自动生成
                elif meta.get("force_status") and f == "status":
                    vals.append(meta["force_status"])     # 申请人不可自选审核结果
                else:
                    vals.append((b.get(f) or ""))
            vals += [now, now]
            q = "INSERT INTO %s(%s) VALUES(%s)" % (meta["t"], ",".join(cols + ["created_at", "updated_at"]), ",".join("?" * len(vals)))
            cur = conn.execute(q, vals)
            if meta["t"] == "upgrade_apply" and b.get("features") is not None:
                self._save_features(conn, "upgrade", cur.lastrowid, b.get("features"))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                         (0, "申请/名单新增", b.get("account_id") or "", b.get("operator") or "未署名", now, "%s 新增" % meta["t"]))
            conn.commit(); return self._send(200, {"ok": True, "id": cur.lastrowid})
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def _gen_put(self, conn, meta, rid, b):
        r = conn.execute("SELECT * FROM %s WHERE id=?" % meta["t"], (rid,)).fetchone()
        if not r: return self._send(404, {"error": "记录不存在"})
        now = _now()
        # 一票否决项校验（制度 5.5）
        if meta["t"] == "assess_record":
            merged = dict(r); merged.update({k: v for k, v in b.items() if v is not None})
            verr = self._check_veto(merged)
            if verr:
                return self._send(400, {"error": verr})
        # 分类扩充：审核结果仅限审核入口修改，普通保存不改动 status
        skip = set()
        if meta.get("force_status"):
            skip.add("status")
        sets = [f + "=?" for f in meta["f"] if f not in skip] + ["updated_at=?"]
        vals = [(b.get(f, r[f]) or "") for f in meta["f"] if f not in skip] + [now]
        conn.execute("UPDATE %s SET %s WHERE id=?" % (meta["t"], ",".join(sets)), vals + [rid])
        if meta["t"] == "upgrade_apply" and b.get("features") is not None:
            self._save_features(conn, "upgrade", rid, b.get("features"))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "申请/名单修改", b.get("account_id") or r["account_id"], b.get("operator") or "未署名", now, "%s %s 修改" % (meta["t"], rid)))
        # 升级申请审核通过 -> 提升账号等级并同步有效权限等级（回环）
        if meta["t"] == "upgrade_apply" and (b.get("status", r["status"]) == "已通过"):
            new_level = (b.get("to_level") or r["to_level"] or "").strip()
            if new_level:
                conn.execute("UPDATE account SET level=? WHERE account_id=?", (new_level, r["account_id"]))
                conn.execute("UPDATE permission SET level=? WHERE account_id=? AND recycled=0", (new_level, r["account_id"]))
                conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                             (0, "升级通过", r["account_id"], b.get("operator") or "未署名", now, "升级审核通过，等级提升为 %s" % new_level))
            # 中审追加分类：通过即回环创建/激活该分类权限（制度 6.2）
            target_cat = (b.get("target_category") or r["target_category"] or "").strip()
            if target_cat:
                operator = b.get("operator") or r["operator"] or "未署名"
                self._grant_category(conn, r["account_id"], target_cat, operator, now)
        conn.commit(); return self._send(200, {"ok": True})

    def _gen_del(self, conn, meta, rid):
        r = conn.execute("SELECT * FROM %s WHERE id=?" % meta["t"], (rid,)).fetchone()
        if not r: return self._send(404, {"error": "记录不存在"})
        now = _now()
        conn.execute("DELETE FROM %s WHERE id=?" % meta["t"], (rid,))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "申请/名单删除", r["account_id"] or "", "未署名", now, "%s %s 删除" % (meta["t"], rid)))
        conn.commit(); return self._send(200, {"ok": True})

    def _save_features(self, conn, kind, apply_id, features):
        feat = KIND_FEAT.get(kind, "upgrade_apply_feature")
        conn.execute("DELETE FROM %s WHERE apply_id=?" % feat, (apply_id,))
        for fr in (features or []):
            if not isinstance(fr, dict): continue
            conn.execute("INSERT INTO %s(apply_id,entry_name,entry_link,compliant_time,note,created_at) VALUES(?,?,?,?,?,?)" % feat,
                         (apply_id, (fr.get("entry_name") or "").strip(), (fr.get("entry_link") or "").strip(),
                          (fr.get("compliant_time") or "").strip(), (fr.get("note") or "").strip(), _now()))

    # ---------- 官方任务包（名单管理） ----------
    def _list_official_packages(self, conn, kw):
        sql = """SELECT p.*,
            (SELECT COUNT(*) FROM official_task_member m WHERE m.package_id=p.id) AS member_count
            FROM official_task_package p"""
        params = []
        if kw:
            sql += " WHERE p.task_name LIKE ? OR p.task_id LIKE ? OR p.creator LIKE ?"
            params = ["%%%s%%" % kw] * 3
        sql += " ORDER BY p.updated_at DESC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def _get_official_package(self, conn, pid):
        pkg = conn.execute("SELECT * FROM official_task_package WHERE id=?", (pid,)).fetchone()
        if not pkg: return None
        mems = conn.execute("""SELECT m.*, a.display_name
            FROM official_task_member m LEFT JOIN account a ON m.account_id=a.account_id
            WHERE m.package_id=? ORDER BY m.id""", (pid,)).fetchall()
        d = dict(pkg)
        d["members"] = [dict(r) for r in mems]
        return d

    def _parse_official_members(self, body):
        raw = body.get("members") or ""
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        return [x.strip() for x in raw.replace("，", ",").replace("\n", ",").replace("；", ";").split(",") if x.strip()]

    def _add_official_package(self, conn, aid, body):
        if not self._require_admin(conn, aid):
            return self._send(403, {"error": "无权限：需要管理角色"})
        task_name = (body.get("task_name") or "").strip()
        task_id = (body.get("task_id") or "").strip()
        creator = (body.get("creator") or "").strip()
        if not task_name or not task_id or not creator:
            return self._send(400, {"error": "任务名称、任务ID、任务创建者为必填"})
        if conn.execute("SELECT 1 FROM official_task_package WHERE task_id=?", (task_id,)).fetchone():
            return self._send(400, {"error": "任务ID已存在：%s" % task_id})
        accounts = self._parse_official_members(body)
        invalid = [a for a in accounts if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (a,)).fetchone()]
        if invalid:
            return self._send(400, {"error": "以下账号不存在：%s" % ", ".join(invalid)})
        now = _now()
        operator = body.get("operator") or aid
        cur = conn.execute("""INSERT INTO official_task_package
            (task_name, task_id, creator, owner, note, operator, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (task_name, task_id, creator, (body.get("owner") or "").strip(), (body.get("note") or "").strip(), operator, now, now))
        pid = cur.lastrowid
        for a in accounts:
            conn.execute("""INSERT OR IGNORE INTO official_task_member
                (package_id, account_id, required_level, note, operator, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?)""",
                (pid, a, (body.get("required_level") or "").strip(), "", operator, now, now))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "官方任务包新增", "", operator, now, "任务包 %s(%s) 新增，参与人数 %d" % (task_name, task_id, len(accounts))))
        conn.commit()
        return self._send(200, {"ok": True, "id": pid, "member_count": len(accounts)})

    def _put_official_package(self, conn, aid, pid, body):
        if not self._require_admin(conn, aid):
            return self._send(403, {"error": "无权限：需要管理角色"})
        pkg = conn.execute("SELECT * FROM official_task_package WHERE id=?", (pid,)).fetchone()
        if not pkg: return self._send(404, {"error": "任务包不存在"})
        task_name = (body.get("task_name") or "").strip()
        task_id = (body.get("task_id") or "").strip()
        creator = (body.get("creator") or "").strip()
        if not task_name or not task_id or not creator:
            return self._send(400, {"error": "任务名称、任务ID、任务创建者为必填"})
        dup = conn.execute("SELECT 1 FROM official_task_package WHERE task_id=? AND id!=?", (task_id, pid)).fetchone()
        if dup:
            return self._send(400, {"error": "任务ID已存在：%s" % task_id})
        accounts = self._parse_official_members(body)
        invalid = [a for a in accounts if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (a,)).fetchone()]
        if invalid:
            return self._send(400, {"error": "以下账号不存在：%s" % ", ".join(invalid)})
        now = _now()
        operator = body.get("operator") or aid
        conn.execute("""UPDATE official_task_package SET
            task_name=?, task_id=?, creator=?, owner=?, note=?, operator=?, updated_at=?
            WHERE id=?""",
            (task_name, task_id, creator, (body.get("owner") or "").strip(), (body.get("note") or "").strip(), operator, now, pid))
        # 全量替换成员
        conn.execute("DELETE FROM official_task_member WHERE package_id=?", (pid,))
        for a in accounts:
            conn.execute("""INSERT OR IGNORE INTO official_task_member
                (package_id, account_id, required_level, note, operator, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?)""",
                (pid, a, (body.get("required_level") or "").strip(), "", operator, now, now))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "官方任务包修改", "", operator, now, "任务包 %s(%s) 修改，参与人数 %d" % (task_name, task_id, len(accounts))))
        conn.commit()
        return self._send(200, {"ok": True, "id": pid, "member_count": len(accounts)})

    def _del_official_package(self, conn, aid, pid):
        if not self._require_admin(conn, aid):
            return self._send(403, {"error": "无权限：需要管理角色"})
        pkg = conn.execute("SELECT * FROM official_task_package WHERE id=?", (pid,)).fetchone()
        if not pkg: return self._send(404, {"error": "任务包不存在"})
        now = _now()
        conn.execute("DELETE FROM official_task_member WHERE package_id=?", (pid,))
        conn.execute("DELETE FROM official_task_package WHERE id=?", (pid,))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "官方任务包删除", "", aid, now, "任务包 %s(%s) 删除" % (pkg["task_name"], pkg["task_id"])))
        conn.commit()
        return self._send(200, {"ok": True})

    # ---- 超级管理员：设置 / 取消 其余账号的管理员身份 ----
    def _admin_set(self, conn, aid, body, grant):
        if not has_cap(conn, aid, "admin_grant"):
            return self._send(403, {"error": "无权限：仅超级管理员可设置/取消管理员"})
        target = (body.get("account_id") or "").strip()
        role = (body.get("role") or "").strip()
        scope = (body.get("scope") or "").strip()
        if role not in ALL_ADMIN_ROLES:
            return self._send(400, {"error": "角色非法（应为 %s）" % " / ".join(sorted(ALL_ADMIN_ROLES))})
        if not target:
            return self._send(400, {"error": "目标账号为必填"})
        # 管辖范围校验：团队负责人/质量组长→大团队(domain)；特色小组长→二级组(group_name)
        scope_kind = SCOPED_ADMIN_ROLES.get(role)
        if grant and scope_kind:
            if not scope:
                return self._send(400, {"error": "「%s」须指定%s" % (role, scope_kind)})
            if scope_kind == "大团队":
                ok = conn.execute("SELECT 1 FROM category_dict WHERE domain=? LIMIT 1", (scope,)).fetchone()
            else:
                ok = conn.execute("SELECT 1 FROM category_dict WHERE group_name=? LIMIT 1", (scope,)).fetchone()
            if not ok:
                return self._send(400, {"error": "%s「%s」不在分类字典中" % (scope_kind, scope)})
        now = _now()
        if grant:
            ex = conn.execute("SELECT id FROM leader_record WHERE account_id=? AND role=?", (target, role)).fetchone()
            if ex:
                conn.execute("UPDATE leader_record SET status='在任', scope=?, updated_at=? WHERE id=?", (scope, now, ex["id"]))
            else:
                conn.execute("INSERT INTO leader_record(account_id,role,status,time,owner,operator,scope,created_at,updated_at) VALUES(?,?, '在任',?,'',?,?,?,?)",
                             (target, role, now[:10], aid, scope, now, now))
            act = "设置管理员"
        else:
            conn.execute("UPDATE leader_record SET status='离任', updated_at=? WHERE account_id=? AND role=?", (now, target, role))
            act = "取消管理员"
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, act, target, aid, now, "%s：%s -> %s%s" % (act, target, role, ("（%s）" % scope) if scope else "")))
        conn.commit(); return self._send(200, {"ok": True})

    # ---- 评审状态处置申请（多节点审批 + 不得跨权；依附于升级/扩充申请） ----
    def _add_status_strip(self, conn, aid, body):
        target = (body.get("target_account") or "").strip()
        category = (body.get("category") or "").strip()
        reason = (body.get("reason") or "").strip()
        source_type = (body.get("source_type") or "").strip()
        source_id_raw = body.get("source_id")
        source_id = int(source_id_raw) if source_id_raw is not None and str(source_id_raw).isdigit() else None
        if source_type and source_type not in ("upgrade", "expand"):
            return self._send(400, {"error": "来源类型非法（应为 upgrade/expand）"})
        if not target:
            return self._send(400, {"error": "目标账号为必填"})
        if not category:
            return self._send(400, {"error": "审核分类为必填"})
        dept = dept_of(category)
        if not dept:
            return self._send(400, {"error": "未知分类「%s」，无法确定部门（不得跨权校验失败）" % category})
        # 来源校验：升级/扩充申请须存在且目标/分类匹配
        if source_type == "upgrade":
            src = conn.execute("SELECT account_id, target_category FROM upgrade_apply WHERE id=?", (source_id,)).fetchone()
            if not src: return self._send(400, {"error": "来源升级申请不存在"})
            if src["account_id"] != target or src["target_category"] != category:
                return self._send(400, {"error": "处置目标/分类须与来源升级申请一致"})
        elif source_type == "expand":
            src = conn.execute("SELECT account_id, add_category FROM category_expand WHERE id=?", (source_id,)).fetchone()
            if not src: return self._send(400, {"error": "来源分类扩充申请不存在"})
            if src["account_id"] != target or src["add_category"] != category:
                return self._send(400, {"error": "处置目标/分类须与来源分类扩充申请一致"})
        if not _holds_perm_in_category(conn, target, category):
            return self._send(400, {"error": "目标账号在「%s」无有效评审权限，无需处置" % category})
        now = _now()
        cur = conn.execute("""INSERT INTO status_strip_apply(target_account,category,department,reason,status,applicant,source_type,source_id,created_at,updated_at)
                             VALUES(?,?,?,?,'待审核',?,?,?,?,?)""",
                          (target, category, dept, reason, aid, source_type, source_id, now, now))
        pid = cur.lastrowid
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "评审状态处置申请", target, aid, now, "申请处置 %s 在「%s」(%s) 的评审状态" % (target, category, dept)))
        conn.commit(); return self._send(200, {"ok": True, "id": pid})

    def _approve_status_strip(self, conn, aid, sid, body):
        r = conn.execute("SELECT * FROM status_strip_apply WHERE id=?", (sid,)).fetchone()
        if not r:
            return self._send(404, {"error": "申请不存在"})
        if r["status"] != "待审核":
            return self._send(400, {"error": "该申请已终结，不可再审批"})
        kind = (body.get("kind") or "").strip()
        now = _now()
        if kind == "cat_lead":
            # 小组长（按分类）：不得跨权——审批人须在该分类持有有效权限
            if not (has_cap(conn, aid, "strip_approve_catlead") and _holds_perm_in_category(conn, aid, r["category"])):
                return self._send(403, {"error": "无权限：小组长仅可审批本人所属分类（不得跨权）"})
            col = "cat_lead_approver"
        elif kind == "quality_lead":
            # 质量组长（按部门，非必须）：不得跨权——审批人须在该部门持有有效权限
            if not (has_cap(conn, aid, "strip_approve_quality") and _holds_perm_in_dept(conn, aid, r["department"])):
                return self._send(403, {"error": "无权限：质量组长仅可审批本部门（不得跨权）"})
            col = "quality_lead_approver"
        elif kind == "review_lead":
            # 评审相关负责人 = 超级管理员（Adzwlqxm）
            if not has_cap(conn, aid, "strip_approve_review"):
                return self._send(403, {"error": "无权限：评审相关负责人（Adzwlqxm）方可审批"})
            col = "review_lead_approver"
        else:
            return self._send(400, {"error": "审批节点非法（应为 cat_lead/quality_lead/review_lead）"})
        if r[col]:
            return self._send(400, {"error": "该节点已由 %s 审批" % r[col]})
        conn.execute("UPDATE status_strip_apply SET %s=?, updated_at=? WHERE id=?" % col, (aid, now, sid))
        upd = conn.execute("SELECT * FROM status_strip_apply WHERE id=?", (sid,)).fetchone()
        # 通过条件：分类组长（必须）+ 评审负责人（必须）；质量组长非必须
        if upd["cat_lead_approver"] and upd["review_lead_approver"]:
            conn.execute("UPDATE status_strip_apply SET status='已通过', updated_at=? WHERE id=?", (now, sid))
            conn.execute("UPDATE permission SET status='已回收', recycled=1, updated_at=? WHERE account_id=? AND category=? AND recycled=0",
                         (now, upd["target_account"], upd["category"]))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                         (0, "评审状态处置执行", upd["target_account"], aid, now, "三节点审批通过，回收 %s 在「%s」的审核权限" % (upd["target_account"], upd["category"])))
        conn.commit(); return self._send(200, {"ok": True})

    # ---- 系统功能权限：个人主页 / 梳理 / 超级管理员单独开通撤销 ----
    def _active_categories(self, conn, account_id):
        rows = conn.execute(
            "SELECT category, level, status FROM permission WHERE account_id=? AND recycled=0 AND status NOT IN ('已回收','停审','降级') ORDER BY category",
            (account_id,)).fetchall()
        return [dict(r) for r in rows]

    def _cap_matrix(self, conn, account_id):
        out = []
        for c in CAPS:
            ov = cap_override(conn, account_id, c["key"])
            out.append(dict(key=c["key"], name=c["name"], tier=c["tier"], desc=c["desc"],
                            has=has_cap(conn, account_id, c["key"]),
                            override=(ov if ov is not None else None)))
        return out

    def _my_capabilities(self, conn, aid):
        if not aid:
            return dict(account_id=None, tier="", capabilities=[], categories=[])
        r = conn.execute("SELECT account_id, level, status FROM account WHERE account_id=?", (aid,)).fetchone()
        return dict(account_id=aid, level=r["level"] if r else "", status=r["status"] if r else "",
                    tier=tier_of(conn, aid),
                    is_reviewer=has_cap(conn, aid, "upgrade_review"),
                    is_admin=has_cap(conn, aid, "system_admin"),
                    is_senior=has_cap(conn, aid, "violation_register"),
                    is_super_admin=has_cap(conn, aid, "admin_grant"),
                    capabilities=self._cap_matrix(conn, aid),
                    categories=self._active_categories(conn, aid))

    def _admin_account_capabilities(self, conn, target):
        r = conn.execute("SELECT account_id, level, status FROM account WHERE account_id=?", (target,)).fetchone()
        if not r:
            return dict(account_id=target, error="账号不存在", capabilities=[], categories=[])
        return dict(account_id=target, level=r["level"], status=r["status"], tier=tier_of(conn, target),
                    is_reviewer=has_cap(conn, target, "upgrade_review"),
                    is_admin=has_cap(conn, target, "system_admin"),
                    is_senior=has_cap(conn, target, "violation_register"),
                    is_super_admin=has_cap(conn, target, "admin_grant"),
                    capabilities=self._cap_matrix(conn, target),
                    categories=self._active_categories(conn, target))

    def _admin_cap_set(self, conn, aid, body, grant):
        if not has_cap(conn, aid, "admin_grant"):
            return self._send(403, {"error": "无权限：仅超级管理员可单独开通/撤销账号权限"})
        target = (body.get("account_id") or "").strip()
        key = (body.get("capability") or "").strip()
        if key not in CAPS_MAP:
            return self._send(400, {"error": "未知的系统功能权限：%s" % key})
        if not target:
            return self._send(400, {"error": "目标账号为必填"})
        if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (target,)).fetchone():
            return self._send(400, {"error": "目标账号不存在"})
        now = _now()
        reason = (body.get("reason") or "").strip()
        granted = 1 if grant else 0
        conn.execute("""INSERT INTO account_capability(account_id,capability,granted,operator,reason,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?)
                        ON CONFLICT(account_id,capability) DO UPDATE SET granted=excluded.granted, operator=excluded.operator, reason=excluded.reason, updated_at=excluded.updated_at""",
                     (target, key, granted, aid, reason, now, now))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "权限开通" if grant else "权限撤销", target, aid, now,
                      "%s：%s -> %s（%s）" % ("开通" if grant else "撤销", target, CAPS_MAP[key]["name"], reason or "无备注")))
        conn.commit(); return self._send(200, {"ok": True, "granted": granted})

    def _admin_cap_bulk(self, conn, aid, body):
        if not has_cap(conn, aid, "admin_grant"):
            return self._send(403, {"error": "无权限：仅超级管理员可批量配置权限"})
        target = (body.get("account_id") or "").strip()
        tier = (body.get("tier") or "").strip()
        action = (body.get("action") or "").strip()  # grant / revoke
        if tier not in TIERS:
            return self._send(400, {"error": "层级非法（应为 %s）" % " / ".join(TIERS)})
        if action not in ("grant", "revoke"):
            return self._send(400, {"error": "操作非法（应为 grant/revoke）"})
        if not target:
            return self._send(400, {"error": "目标账号为必填"})
        if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (target,)).fetchone():
            return self._send(400, {"error": "目标账号不存在"})
        now = _now(); reason = (body.get("reason") or "").strip()
        granted = 1 if action == "grant" else 0
        keys = [c["key"] for c in CAPS if c["tier"] == tier]
        for k in keys:
            conn.execute("""INSERT INTO account_capability(account_id,capability,granted,operator,reason,created_at,updated_at)
                            VALUES(?,?,?,?,?,?,?)
                            ON CONFLICT(account_id,capability) DO UPDATE SET granted=excluded.granted, operator=excluded.operator, reason=excluded.reason, updated_at=excluded.updated_at""",
                         (target, k, granted, aid, reason, now, now))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "权限批量%s" % action, target, aid, now,
                      "按层级 %s %s %d 项系统功能权限（%s）" % (tier, action, len(keys), reason or "无备注")))
        conn.commit(); return self._send(200, {"ok": True, "count": len(keys)})

    # ---- 个人中心：修改密码 ----
    def _change_pw(self, conn, aid, body):
        old = body.get("old_password") or ""
        new = (body.get("new_password") or "").strip()
        if len(new) < 6:
            return self._send(400, {"error": "新密码长度至少 6 位"})
        r = conn.execute("SELECT * FROM account WHERE account_id=?", (aid,)).fetchone()
        if not r:
            return self._send(404, {"error": "账号不存在"})
        # 校验旧密码（默认密码规则或已设散列）
        ok = False
        if r["password"]:
            ok = (r["password"] == hash_pw(old))
        else:
            ok = (old == (aid + "@2026"))
        if not ok:
            return self._send(400, {"error": "原密码错误"})
        now = _now()
        conn.execute("UPDATE account SET password=? WHERE account_id=?", (hash_pw(new), aid))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "修改密码", aid, aid, now, "账号 %s 修改登录密码" % aid))
        conn.commit(); return self._send(200, {"ok": True})

    def _request_password_reset(self, conn, body):
        """忘记密码：无需登录提交恢复申请；向超级管理员发送站内信提醒。"""
        account_id = (body.get("account_id") or "").strip()
        contact = (body.get("contact") or "").strip()
        if not account_id:
            return self._send(400, {"error": "请填写账号（百科ID）"})
        if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (account_id,)).fetchone():
            return self._send(404, {"error": "账号不存在：%s，请核对百科ID" % account_id})
        # 7 天内仅可申请一次（无论上次是否已处理）
        recent = conn.execute("SELECT status, created_at FROM password_reset_request WHERE account_id=? ORDER BY id DESC LIMIT 1", (account_id,)).fetchone()
        if recent and recent["created_at"]:
            try:
                last = datetime.datetime.strptime(recent["created_at"][:19], "%Y-%m-%d %H:%M:%S")
                diff = datetime.datetime.now() - last
                if diff.total_seconds() < 7 * 86400:
                    remain_sec = 7 * 86400 - diff.total_seconds()
                    remain_days = int(remain_sec // 86400) + (1 if remain_sec % 86400 else 0)
                    tip = "，该申请%s" % ("仍在待处理中" if recent["status"] == "待处理" else "已于近期处理")
                    return self._send(400, {"error": "7 天内仅可提交一次密码恢复申请%s；请约 %d 天后再试，或直接联系管理员处理" % (tip, remain_days)})
            except ValueError:
                pass
        now = _now()
        conn.execute("INSERT INTO password_reset_request(account_id,contact,status,created_at) VALUES(?,?,'待处理',?)",
                     (account_id, contact, now))
        supers = sorted(SUPER_ADMIN_ACCOUNTS)
        auto_send_message(conn, "pwd_reset",
                          "密码恢复申请：%s" % account_id,
                          "账号「%s」提交了密码恢复申请%s。请前往「基础数据 → 账号（评审员）」编辑该账号并重置随机密码。" % (account_id, ("（联系方式：%s）" % contact) if contact else ""),
                          accounts=supers, scope_type="user", scope_target=",".join(supers))
        conn.commit()
        return self._send(200, {"ok": True, "message": "申请已提交，请等待管理员重置密码（重置后请向管理员获取新密码）"})

    def _reset_password(self, conn, aid, body):
        """超级管理员为账号重置 12 位随机密码；明文仅在响应中返回一次。"""
        if not is_super_admin(conn, aid):
            return self._send(403, {"error": "无权限：仅超级管理员可重置密码"})
        target = (body.get("account_id") or "").strip()
        if not target:
            return self._send(400, {"error": "目标账号为必填"})
        if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (target,)).fetchone():
            return self._send(404, {"error": "账号不存在：%s" % target})
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
        new_pw = "".join(secrets.choice(alphabet) for _ in range(12))
        now = _now()
        conn.execute("UPDATE account SET password=? WHERE account_id=?", (hash_pw(new_pw), target))
        conn.execute("UPDATE password_reset_request SET status='已处理', handled_at=?, handled_by=?, note='已重置随机密码' WHERE account_id=? AND status='待处理'",
                     (now, aid, target))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "重置密码", target, aid, now, "超级管理员 %s 为账号 %s 重置 12 位随机密码" % (aid, target)))
        conn.commit()
        return self._send(200, {"ok": True, "new_password": new_pw})

    # ---- 评审量分类明细（主/副分类判定数据源）----
    def _set_cat_detail(self, conn, body):
        account_id = (body.get("account_id") or "").strip()
        period = (body.get("period") or "").strip()
        items = body.get("items", [])  # [{category, versions}]
        if not account_id or not period:
            return self._send(400, {"error": "账号与考核周期为必填"})
        if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (account_id,)).fetchone():
            return self._send(400, {"error": "账号不存在"})
        now = _now(); added = 0
        for it in items:
            cat = (it.get("category") or "").strip()
            ver = int(it.get("versions") or 0)
            if not cat:
                continue
            if not conn.execute("SELECT 1 FROM category_dict WHERE category=?", (cat,)).fetchone():
                return self._send(400, {"error": "分类「%s」不在分类字典中" % cat})
            conn.execute("""INSERT INTO assess_category_detail(account_id,period,category,versions)
                            VALUES(?,?,?,?) ON CONFLICT(account_id,period,category) DO UPDATE SET versions=excluded.versions""",
                        (account_id, period, cat, ver))
            added += 1
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "分类评审量录入", account_id, "已登录用户", now, "%s %s 录入 %d 个分类评审量" % (account_id, period, added)))
        conn.commit(); return self._send(200, {"ok": True, "count": added})

    # ---- 违规/处分记录 ----
    # ---- 违规挂起 / 恢复 联动 ----
    def _suspend_perm_for_violation(self, conn, vid, account_id, category, operator, target_status=None):
        """严重/重大违规、或处分措施为「停审/降级」生效时，挂起该账号在对应分类的有效权限，并记录原状态，供申诉成立/期限届满时精准恢复。"""
        if not category:
            return
        now = _now()
        target = target_status or SUSPEND_STATUS
        perm = conn.execute(
            "SELECT id,status FROM permission WHERE account_id=? AND category=? "
            "AND status NOT IN ('已回收','停审','降级') AND recycled=0 LIMIT 1",
            (account_id, category)).fetchone()
        if not perm:
            return
        prev = perm["status"]
        conn.execute("UPDATE permission SET status=?, updated_at=? WHERE id=?", (target, now, perm["id"]))
        conn.execute("UPDATE violation_record SET perm_id=?, perm_prev_status=? WHERE id=?", (perm["id"], prev, vid))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (perm["id"], "违规挂起", account_id, operator or "未署名", now,
                      "因%s分类违规/处分，权限(perm_id=%s)由%s挂起为%s" % (category, perm["id"], prev, target)))

    def _revoke_perm_for_violation(self, conn, vid, account_id, category, operator):
        """处分措施为「取消权限/永久封禁」生效时，回收该账号在对应分类的权限（终态，不自动恢复）。"""
        if not category:
            return
        now = _now()
        perm = conn.execute(
            "SELECT id,status FROM permission WHERE account_id=? AND category=? "
            "AND status NOT IN ('已回收') AND recycled=0 LIMIT 1",
            (account_id, category)).fetchone()
        if not perm:
            return
        prev = perm["status"]
        conn.execute("UPDATE permission SET status='已回收', updated_at=? WHERE id=?", (now, perm["id"]))
        conn.execute("UPDATE violation_record SET perm_id=?, perm_prev_status=? WHERE id=?", (perm["id"], prev, vid))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (perm["id"], "违规回收", account_id, operator or "未署名", now,
                      "因%s分类处分（取消权限/永久封禁），权限(perm_id=%s)由%s回收" % (category, perm["id"], prev)))

    def _penalty_target(self, penalty, level):
        """返回处分措施对应的权限目标状态；None 表示不联动权限。"""
        p = (penalty or "").strip()
        if p in ("停审", "降级"):
            return p
        if p in ("取消权限", "永久封禁"):
            return "已回收"
        if p == "" and level in SEVERE_LEVELS:
            return SUSPEND_STATUS  # 兼容历史：未填措施但属严重/重大，默认停审
        return None

    def _apply_penalty_effect(self, conn, vid, account_id, category, penalty, level, operator):
        """依据处分措施对权限产生联动（挂起/回收/无），仅在有违规分类时生效。"""
        if not category:
            return
        target = self._penalty_target(penalty, level)
        if target == "已回收":
            self._revoke_perm_for_violation(conn, vid, account_id, category, operator)
            self._set_need_retrain(conn, account_id, "违规处分（%s，制度 6.3）" % penalty)
        elif target in (SUSPEND_STATUS, "降级"):
            self._suspend_perm_for_violation(conn, vid, account_id, category, operator, target_status=target)
            if target == "降级":
                self._set_need_retrain(conn, account_id, "违规处分（降级，制度 6.3）")

    def _restore_perm_for_violation(self, conn, vid):
        """违规被撤销（申诉成立/手动撤销）时，恢复被挂起的权限到原状态。"""
        v = conn.execute("SELECT * FROM violation_record WHERE id=?", (vid,)).fetchone()
        if not v or not v["perm_id"]:
            return
        now = _now()
        cur = conn.execute("SELECT status FROM permission WHERE id=?", (v["perm_id"],)).fetchone()
        if cur and cur["status"] in (SUSPEND_STATUS, "降级"):
            restored = v["perm_prev_status"] or "正常"
            conn.execute("UPDATE permission SET status=?, updated_at=? WHERE id=?", (restored, now, v["perm_id"]))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                         (v["perm_id"], "违规恢复", v["account_id"], "系统(申诉)", now,
                          "违规#%s撤销，权限(perm_id=%s)恢复为%s" % (vid, v["perm_id"], restored)))
        conn.execute("UPDATE violation_record SET perm_id=0, perm_prev_status='' WHERE id=?", (vid,))

    def _create_referrer_liability(self, conn, vid, account_id, category, level, penalty, operator):
        """制度 7.4：被推荐人（报名 qq）违规且处分生效时，自动关联其推荐人生成连带责任记录。"""
        if not account_id:
            return
        ref = conn.execute(
            "SELECT referrer FROM registration WHERE qq=? AND referrer IS NOT NULL AND referrer!='' "
            "ORDER BY id DESC LIMIT 1", (account_id,)).fetchone()
        if not ref:
            return
        referrer = (ref["referrer"] or "").strip()
        if not referrer or referrer == account_id:
            return
        now = _now()
        try:
            conn.execute(
                "INSERT INTO referrer_liability(violation_id,violator_account,referrer_account,category,level,penalty,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,'待处理',?,?)",
                (vid, account_id, referrer, category, level, penalty, now, now))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                         (0, "推荐人连带责任", referrer, operator or "未署名", now,
                          "被推荐人 %s 违规（违规#%s），推荐人 %s 承担连带责任" % (account_id, vid, referrer)))
        except Exception:
            pass  # UNIQUE(violation_id) 已存在则忽略

    def _restore_expired_penalties(self, conn):
        """处分期限届满自动恢复（仅 停审/降级 这类带期限的处分）：到期未人工续期则恢复被挂起权限。"""
        now = _now()[:10]
        rows = conn.execute(
            "SELECT id FROM violation_record WHERE penalty IN (?,?) AND penalty_term>0 "
            "AND penalty_due IS NOT NULL AND penalty_due!='' AND penalty_due<=? "
            "AND status='生效' AND (restored_at IS NULL OR restored_at='')",
            (SUSPEND_STATUS, "降级", now)).fetchall()
        for r in rows:
            v = conn.execute("SELECT * FROM violation_record WHERE id=?", (r["id"],)).fetchone()
            if v and v["perm_id"]:
                self._restore_perm_for_violation(conn, v["id"])
            conn.execute("UPDATE violation_record SET restored_at=? WHERE id=?", (now, r["id"]))
            conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                         (0, "处分期满恢复", v["account_id"] if v else "", "系统(期限流转)", now,
                          "处分#%s 期限届满（%s），自动恢复权限" % (r["id"], v["penalty_due"] if v else "")))

    def _violation_stats(self, conn):
        """违规统计（制度 7.2 监督）：按账号/分类/月份聚合，便于识别高频违规账号与趋势。"""
        total = conn.execute("SELECT COUNT(*) c FROM violation_record").fetchone()["c"]
        active = conn.execute("SELECT COUNT(*) c FROM violation_record WHERE COALESCE(status,'生效')='生效'").fetchone()["c"]
        revoked = conn.execute("SELECT COUNT(*) c FROM violation_record WHERE status='已撤销'").fetchone()["c"]
        by_level = {}
        for lv in VIOLATION_LEVELS:
            by_level[lv] = conn.execute("SELECT COUNT(*) c FROM violation_record WHERE level=?", (lv,)).fetchone()["c"]
        by_account = [dict(r) for r in conn.execute(
            "SELECT account_id, COUNT(*) cnt, "
            "SUM(CASE WHEN COALESCE(status,'生效')='生效' THEN 1 ELSE 0 END) active_cnt, "
            "MAX(created_at) last_time FROM violation_record GROUP BY account_id ORDER BY cnt DESC, account_id").fetchall()]
        by_category = [dict(r) for r in conn.execute(
            "SELECT category, COUNT(*) cnt FROM violation_record WHERE category IS NOT NULL AND category!='' "
            "GROUP BY category ORDER BY cnt DESC, category").fetchall()]
        by_month = [dict(r) for r in conn.execute(
            "SELECT substr(COALESCE(created_at,penalty_time),1,7) ym, COUNT(*) cnt FROM violation_record "
            "WHERE COALESCE(created_at,penalty_time) IS NOT NULL AND COALESCE(created_at,penalty_time)!='' "
            "GROUP BY ym ORDER BY ym").fetchall()]
        return dict(summary=dict(total=total, active=active, revoked=revoked, by_level=by_level),
                    by_account=by_account, by_category=by_category, by_month=by_month)

    def _block_apply_reason(self, conn, qq):
        """制度 4.4 不得报名的情形；返回 (blocked:bool, reason:str)。

        已系统化的情形：①账号处于封禁/限制/取消状态（永久封禁/已回收）；
        ②账号处于停审/降级且处分期限未过（处罚期内）；③近6个月内存在违规取消/处分记录。
        未系统化（待再训/蝌蚪身份模块落地后补）：再训流程未完成、丧失蝌蚪身份。"""
        if not qq:
            return (False, "")
        ac = conn.execute("SELECT status FROM account WHERE account_id=?", (qq,)).fetchone()
        if ac:
            st = ac["status"]
            if st in ("永久封禁", "已回收"):
                return (True, "账号处于「%s」状态，不得报名（制度 4.4 封禁/限制/取消）" % st)
            if st in ("停审", "降级"):
                pen = conn.execute(
                    "SELECT penalty_due FROM violation_record WHERE account_id=? AND COALESCE(status,'生效')='生效' "
                    "AND penalty_due IS NOT NULL AND penalty_due!='' ORDER BY penalty_due DESC LIMIT 1", (qq,)).fetchone()
                if pen and pen["penalty_due"] and pen["penalty_due"] >= _now()[:10]:
                    return (True, "账号处于「%s」处罚期内（至 %s），不得报名（制度 4.4）" % (st, pen["penalty_due"]))
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT penalty,level FROM violation_record WHERE account_id=? AND COALESCE(status,'生效')!='已撤销' AND COALESCE(created_at,penalty_time)>=? "
            "AND (penalty IN ('取消权限','永久封禁') OR (level IN ('严重违规','重大违规') AND penalty IN ('取消权限','永久封禁','停审','降级'))) "
            "ORDER BY COALESCE(created_at,penalty_time) DESC LIMIT 1", (qq, cutoff)).fetchone()
        if row:
            tag = (row["penalty"] or "") + ((" / " + row["level"]) if row["level"] else "")
            return (True, "近6个月内存在违规取消/处分记录（%s），未满6个月不得报名（制度 4.4）" % tag)
        return (False, "")

    def _add_violation(self, conn, body):
        account_id = (body.get("account_id") or "").strip()
        if not account_id:
            return self._send(400, {"error": "账号为必填"})
        level = (body.get("level") or "一般违规").strip()
        if level not in VIOLATION_LEVELS:
            return self._send(400, {"error": "违规等级非法"})
        penalty = (body.get("penalty") or "").strip()
        if penalty and penalty not in PENALTY_TYPES:
            return self._send(400, {"error": "处分措施非法（应为 %s 之一）" % " / ".join(PENALTY_TYPES)})
        category = (body.get("category") or "").strip()
        try:
            term = int(body.get("penalty_term") or 0)
        except (TypeError, ValueError):
            term = 0
        penalty_time = (body.get("penalty_time") or _now()[:10])
        penalty_due = ""
        if penalty in PENALTY_TERMED and term > 0:
            try:
                dt = datetime.datetime.strptime(penalty_time, "%Y-%m-%d") + datetime.timedelta(days=term)
                penalty_due = dt.strftime("%Y-%m-%d")
            except Exception:
                penalty_due = ""
        now = _now()
        cur = conn.execute("""INSERT INTO violation_record(account_id,level,reason,penalty,penalty_time,referrer,operator,note,category,perm_id,perm_prev_status,status,penalty_term,penalty_due,restored_at,created_at,updated_at)
                             VALUES(?,?,?,?,?,?,?,?,?,0,'','生效',?,?,?,?,?)""",
                         (account_id, level, (body.get("reason") or "").strip(), penalty, penalty_time,
                          (body.get("referrer") or "").strip(), (body.get("operator") or "未署名"),
                          (body.get("note") or "").strip(), category, term, penalty_due, "", now, now))
        vid = cur.lastrowid
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "违规登记", account_id, body.get("operator") or "未署名", now, "%s 登记%s：%s" % (account_id, level, (body.get("reason") or "")[:50])))
        # 处分措施联动权限（停审/降级挂起、取消权限/永久封禁回收、严重/重大默认停审）
        if category:
            self._apply_penalty_effect(conn, vid, account_id, category, penalty, level, body.get("operator") or "未署名")
        # 推荐人连带责任（制度 7.4）：被推荐人违规，自动关联其推荐人
        self._create_referrer_liability(conn, vid, account_id, category, level, penalty, body.get("operator") or "未署名")
        conn.commit(); return self._send(200, {"ok": True, "id": vid})

    def _put_violation(self, conn, vid, body):
        r = conn.execute("SELECT * FROM violation_record WHERE id=?", (vid,)).fetchone()
        if not r:
            return self._send(404, {"error": "记录不存在"})
        now = _now()
        level = (body.get("level", r["level"]) or "一般违规").strip()
        if level not in VIOLATION_LEVELS:
            return self._send(400, {"error": "违规等级非法"})
        penalty = (body.get("penalty", r["penalty"]) or "").strip()
        if penalty and penalty not in PENALTY_TYPES:
            return self._send(400, {"error": "处分措施非法（应为 %s 之一）" % " / ".join(PENALTY_TYPES)})
        category = (body.get("category", r["category"]) or "").strip()
        status = (body.get("status", r["status"]) or "生效").strip()
        try:
            term = int(body.get("penalty_term", r["penalty_term"]) or 0)
        except (TypeError, ValueError):
            term = 0
        penalty_time = (body.get("penalty_time", r["penalty_time"]) or now[:10])
        penalty_due = ""
        if penalty in PENALTY_TERMED and term > 0:
            try:
                dt = datetime.datetime.strptime(penalty_time, "%Y-%m-%d") + datetime.timedelta(days=term)
                penalty_due = dt.strftime("%Y-%m-%d")
            except Exception:
                penalty_due = ""
        conn.execute("""UPDATE violation_record SET level=?,reason=?,penalty=?,penalty_time=?,referrer=?,operator=?,note=?,category=?,status=?,penalty_term=?,penalty_due=?,updated_at=? WHERE id=?""",
                     (level, (body.get("reason", r["reason"])), penalty, penalty_time,
                      (body.get("referrer", r["referrer"])), (body.get("operator") or r["operator"]),
                      (body.get("note", r["note"])), category, status, term, penalty_due, now, vid))
        if status == "已撤销":
            self._restore_perm_for_violation(conn, vid)
            conn.execute("UPDATE referrer_liability SET status='已免除', updated_at=? WHERE violation_id=?", (now, vid))
        elif category:
            new_target = self._penalty_target(penalty, level)
            cur_effect = None
            if r["perm_id"]:
                cp = conn.execute("SELECT status FROM permission WHERE id=?", (r["perm_id"],)).fetchone()
                cur_effect = cp["status"] if cp else None
            if r["perm_id"]:
                if new_target is None or new_target != cur_effect:
                    self._restore_perm_for_violation(conn, vid)
                    if new_target:
                        self._apply_penalty_effect(conn, vid, r["account_id"], category, penalty, level, body.get("operator") or r["operator"])
            else:
                if new_target:
                    self._apply_penalty_effect(conn, vid, r["account_id"], category, penalty, level, body.get("operator") or r["operator"])
            # 推荐人连带责任：生效且有违规分类，确保已生成
            self._create_referrer_liability(conn, vid, r["account_id"], category, level, penalty, body.get("operator") or r["operator"])
        conn.commit(); return self._send(200, {"ok": True})

    def _del_violation(self, conn, vid):
        r = conn.execute("SELECT * FROM violation_record WHERE id=?", (vid,)).fetchone()
        if not r:
            return self._send(404, {"error": "记录不存在"})
        now = _now()
        conn.execute("DELETE FROM violation_record WHERE id=?", (vid,))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "违规记录删除", r["account_id"], "未署名", now, "删除违规记录：%s" % r["account_id"]))
        conn.commit(); return self._send(200, {"ok": True})

    def _put_referrer_liability(self, conn, lid, body):
        r = conn.execute("SELECT * FROM referrer_liability WHERE id=?", (lid,)).fetchone()
        if not r:
            return self._send(404, {"error": "记录不存在"})
        now = _now()
        status = (body.get("status", r["status"]) or "待处理").strip()
        if status not in ("待处理", "已处理", "已免除"):
            return self._send(400, {"error": "状态非法"})
        handled_by = body.get("handled_by", r["handled_by"]) or ""
        handled_time = (body.get("handled_time") or (now[:10] if status == "已处理" else r["handled_time"])) or ""
        conn.execute("UPDATE referrer_liability SET status=?,handled_by=?,handled_time=?,note=?,updated_at=? WHERE id=?",
                     (status, handled_by, handled_time, (body.get("note", r["note"]) or ""), now, lid))
        conn.commit(); return self._send(200, {"ok": True})

    # ---- 申诉管理 ----
    def _add_appeal(self, conn, body):
        account_id = (body.get("account_id") or "").strip()
        if not account_id:
            return self._send(400, {"error": "账号为必填"})
        now = _now()
        cur = conn.execute("""INSERT INTO appeal_record(ref_type,ref_id,account_id,appeal_time,handler,conclusion,suspended,note,recused,recuser,recuse_reason,created_at,updated_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         ((body.get("ref_type") or ""), int(body.get("ref_id") or 0), account_id, now[:10],
                          (body.get("handler") or ""), (body.get("conclusion") or ""), 1 if body.get("suspended") else 0,
                          (body.get("note") or ""), 1 if body.get("recused") else 0, (body.get("recuser") or ""),
                          (body.get("recuse_reason") or ""), now, now))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "申诉登记", account_id, "已登录用户", now, "%s 提起申诉（关联 %s#%s）" % (account_id, body.get("ref_type") or "", body.get("ref_id") or "")))
        conn.commit(); return self._send(200, {"ok": True, "id": cur.lastrowid})

    def _put_appeal(self, conn, aid, body):
        r = conn.execute("SELECT * FROM appeal_record WHERE id=?", (aid,)).fetchone()
        if not r:
            return self._send(404, {"error": "记录不存在"})
        now = _now()
        conclusion = (body.get("conclusion", r["conclusion"]) or "").strip()
        ref_type = (body.get("ref_type", r["ref_type"]) or "").strip()
        ref_id = int(body.get("ref_id", r["ref_id"]) or 0)
        # 已有结论则不再“进行中”，解除转正暂缓
        suspended = 0 if conclusion else (1 if body.get("suspended", r["suspended"]) else 0)
        conn.execute("""UPDATE appeal_record SET ref_type=?,ref_id=?,account_id=?,appeal_time=?,handler=?,conclusion=?,suspended=?,note=?,recused=?,recuser=?,recuse_reason=?,updated_at=? WHERE id=?""",
                     (ref_type, ref_id, (body.get("account_id", r["account_id"])),
                      (body.get("appeal_time", r["appeal_time"])), (body.get("handler", r["handler"])), conclusion,
                      suspended, (body.get("note", r["note"])),
                      1 if body.get("recused", r["recused"]) else 0, (body.get("recuser", r["recuser"]) or ""),
                      (body.get("recuse_reason", r["recuse_reason"]) or ""), now, aid))
        # 申诉成立且关联违规 → 撤销该违规并恢复其挂起的权限
        if conclusion == "成立" and ref_type == "violation" and ref_id:
            v = conn.execute("SELECT * FROM violation_record WHERE id=?", (ref_id,)).fetchone()
            if v and v["status"] != "已撤销":
                conn.execute("UPDATE violation_record SET status='已撤销', updated_at=? WHERE id=?", (now, ref_id))
                self._restore_perm_for_violation(conn, ref_id)
                conn.execute("UPDATE referrer_liability SET status='已免除', updated_at=? WHERE violation_id=?", (now, ref_id))
        conn.commit(); return self._send(200, {"ok": True})

    def _del_appeal(self, conn, aid):
        r = conn.execute("SELECT * FROM appeal_record WHERE id=?", (aid,)).fetchone()
        if not r:
            return self._send(404, {"error": "记录不存在"})
        now = _now()
        conn.execute("DELETE FROM appeal_record WHERE id=?", (aid,))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (0, "申诉记录删除", r["account_id"], "未署名", now, "删除申诉记录：%s" % r["account_id"]))
        conn.commit(); return self._send(200, {"ok": True})

    # ---- 7.3 回避提示 ----
    def _recuse_hint(self, conn, account_id, handler):
        """制度 7.3：与申诉人/被评词条有直接利益、同分类竞争、师徒/推荐关系的应回避。"""
        if not account_id or not handler:
            return None
        if account_id == handler:
            return "处理人即被处理人本人，须回避"
        if conn.execute("SELECT 1 FROM registration WHERE qq=? AND referrer=?", (account_id, handler)).fetchone():
            return "与账号 %s 存在推荐/师徒关系，应主动回避（制度 7.3）" % account_id
        if conn.execute("SELECT 1 FROM referrer_liability WHERE violator_account=? AND referrer_account=?", (account_id, handler)).fetchone():
            return "与账号 %s 存在推荐连带责任关系，应主动回避（制度 7.3）" % account_id
        return None

    # ---- 3.8 分类休眠检测（细化口径：有逐分类评审量明细时按「近 N 月该分类无评审量」判定；否则回退账号级考核记录） ----
    def _dormant_list(self, conn):
        from datetime import datetime as _dt, timedelta as _td
        now = _dt.now()
        d = now.replace(day=1)
        yms = []
        for _ in range(max(1, DORMANT_MONTHS)):
            yms.append(d.strftime("%Y-%m"))
            d = (d - _td(days=1)).replace(day=1)
        qm = ",".join("?" * len(yms))
        # 逐分类评审量明细可用时，优先按「该分类评审量」严格判定（制度 3.8）
        has_detail = conn.execute("SELECT 1 FROM assess_category_detail LIMIT 1").fetchone() is not None
        rows = conn.execute(
            "SELECT id,account_id,category,level,status FROM permission WHERE recycled=0 AND status IN ('正常','考核期','见习','实习')").fetchall()
        cands = []
        for p in rows:
            acct = p["account_id"]; cat = p["category"]
            if conn.execute("SELECT 1 FROM assess_exemption WHERE account_id=? AND mode='免考核' AND period IN (%s)" % qm, [acct] + yms).fetchone():
                continue
            if has_detail:
                if conn.execute(
                        "SELECT 1 FROM assess_category_detail WHERE account_id=? AND category=? AND period IN (%s) AND versions>0" % qm,
                        [acct, cat] + yms).fetchone():
                    continue
                reason = "近%d个自然月该分类无评审量（制度 3.8）" % DORMANT_MONTHS
            else:
                if conn.execute("SELECT 1 FROM assess_record WHERE account_id=? AND period IN (%s)" % qm, [acct] + yms).fetchone():
                    continue
                reason = "近%d个自然月无考核记录（代理口径）" % DORMANT_MONTHS
            cands.append(dict(id=p["id"], account_id=acct, category=cat, level=p["level"], status=p["status"], reason=reason))
        return cands

    def _set_dormant(self, conn, pid, body):
        r = conn.execute("SELECT * FROM permission WHERE id=?", (pid,)).fetchone()
        if not r:
            return self._send(404, {"error": "权限记录不存在"})
        now = _now()
        conn.execute("UPDATE permission SET status='休眠', updated_at=? WHERE id=?", (now, pid))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (pid, "分类休眠", r["account_id"], (body.get("operator") or "未署名"), now, "连续2月无评审量→休眠（制度3.8）；恢复走6.4再训"))
        conn.commit()
        return self._send(200, {"ok": True, "status": "休眠"})

    # ---- 5.6 实习状态系统化 ----
    def _internship_list(self, conn):
        from datetime import datetime as _dt
        today = _dt.now().strftime("%Y-%m-%d")
        rows = conn.execute("SELECT id,account_id,category,level,status,expire_date,internship_start FROM permission WHERE recycled=0 AND status='实习'").fetchall()
        out = []
        for p in rows:
            acct = p["account_id"]
            sev = conn.execute("SELECT 1 FROM violation_record WHERE account_id=? AND level IN ('严重违规','重大违规') AND status='生效'", (acct,)).fetchone()
            expired = bool(p["expire_date"]) and p["expire_date"] <= today
            out.append(dict(id=p["id"], account_id=acct, category=p["category"], level=p["level"],
                            expire_date=p["expire_date"] or "", internship_start=p["internship_start"] or "",
                            expired=expired, suggest_promote=bool(expired and not sev)))
        return out

    def _internship_set(self, conn, pid, body):
        r = conn.execute("SELECT * FROM permission WHERE id=?", (pid,)).fetchone()
        if not r:
            return self._send(404, {"error": "权限记录不存在"})
        now = _now()
        st = (body.get("status") or r["status"])
        if st not in PERM_STATUSES:
            return self._send(400, {"error": "非法状态：%s" % st})
        if st == "实习":
            from datetime import datetime as _dt, timedelta as _td
            expire = (_dt.now() + _td(days=30)).strftime("%Y-%m-%d")
            conn.execute("UPDATE permission SET status='实习', internship_start=?, expire_date=?, updated_at=? WHERE id=?", (now[:10], expire, now, pid))
            detail = "置实习，实习期至 %s（制度5.6）" % expire
        else:
            conn.execute("UPDATE permission SET status=?, expire_date='', internship_start='', updated_at=? WHERE id=?", (st, now, pid))
            detail = "实习权限变更为 %s" % st
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (pid, "实习状态变更", r["account_id"], (body.get("operator") or "未署名"), now, detail))
        conn.commit()
        return self._send(200, {"ok": True, "status": st, "expire_date": expire if st == "实习" else ""})

    # ---- 见习转正 ----
    def _promote_perm(self, conn, body):
        pid = int(body.get("id") or 0)
        r = conn.execute("SELECT * FROM permission WHERE id=?", (pid,)).fetchone()
        if not r:
            return self._send(404, {"error": "权限记录不存在"})
        if r["status"] != "见习":
            return self._send(400, {"error": "仅见习状态可转正"})
        now = datetime.datetime.now()
        until = r["probation_until"] or ""
        if until and until > now.strftime("%Y-%m-%d"):
            return self._send(400, {"error": "见习期未届满（%s 届满）" % until})
        # 见习期内存在严重/重大违规则不准转正（处罚期未过或尚未填处罚时间的记为未结案）
        SEVERE = ("严重违规", "重大违规")
        sev = conn.execute(
            "SELECT 1 FROM violation_record WHERE account_id=? AND level IN (?,?) "
            "AND (status IS NULL OR status='生效') "
            "AND (penalty_time IS NULL OR penalty_time='' OR penalty_time>=?) LIMIT 1",
            (r["account_id"], SEVERE[0], SEVERE[1],
             (now - datetime.timedelta(days=PROBATION_DAYS)).strftime("%Y-%m-%d"))).fetchone()
        if sev:
            return self._send(400, {"error": "见习期内存在严重/重大违规且尚未结案，不予转正"})
        # 存在进行中的申诉（暂停处理）→ 转正暂缓，待申诉结论
        pend = conn.execute("SELECT 1 FROM appeal_record WHERE account_id=? AND suspended=1 LIMIT 1",
                            (r["account_id"],)).fetchone()
        if pend:
            return self._send(400, {"error": "存在进行中的申诉，转正暂缓"})
        conn.execute("UPDATE permission SET status='正常', updated_at=? WHERE id=?", (now.strftime("%Y-%m-%d %H:%M:%S"), pid))
        conn.execute("INSERT INTO change_log(permission_id,action,account_id,operator,change_time,detail) VALUES(?,?,?,?,?,?)",
                     (pid, "见习转正", r["account_id"], body.get("operator") or "系统", now.strftime("%Y-%m-%d %H:%M:%S"),
                      "分类 %s 见习期满转正为正常" % r["category"]))
        conn.commit(); return self._send(200, {"ok": True})

    def log_message(self, *a): pass

def _f(v):
    try: return float(v)
    except: return 0.0

def migrate():
    """启动时的轻量数据自愈迁移，保证枚举与最新规则一致。"""
    conn = get_conn()
    try:
        n = conn.execute("UPDATE account SET status='正常' WHERE status='在册'").rowcount
        if n:
            print("数据迁移：%d 个账号状态 在册→正常" % n)
        n2 = conn.execute("UPDATE account SET status='正常' WHERE status IS NULL OR status=''").rowcount
        if n2:
            print("数据迁移：%d 个账号空状态→正常" % n2)
        # 账号表新增字段（幂等）
        acct_cols = {r[1] for r in conn.execute("PRAGMA table_info(account)")}
        for col, typ in [("is_test", "INTEGER DEFAULT 0"), ("last_login_time", "TEXT"), ("last_login_ip", "TEXT"), ("last_login_device", "TEXT")]:
            if col not in acct_cols:
                conn.execute("ALTER TABLE account ADD COLUMN %s %s" % (col, typ))
                print("数据迁移：account 表新增列 %s" % col)
        # 自动识别并标记测试账号（名字/ID 包含测试特征）
        test_patterns = ["测试", "ceshi", "test", "123456789", "12345678", "ceshi2", "ceshi3", "ceshi4", "ceshi5"]
        pat_sql = " OR ".join(["account_id LIKE ? OR display_name LIKE ?" for _ in test_patterns])
        params = []
        for p in test_patterns:
            params.extend(["%%%s%%" % p] * 2)
        n_test = conn.execute("UPDATE account SET is_test=1 WHERE is_test=0 AND (%s)" % pat_sql, params).rowcount
        if n_test:
            print("数据迁移：自动标记 %d 个测试账号" % n_test)
        # 历史报名自动建号账号：尚未取得正式权限的，等级由「初审」回退为「待转正」，待评估通过后再转正
        n_pending = conn.execute("""
            UPDATE account SET level='待转正', note=CASE
                WHEN note LIKE '%报名账号补建%' THEN '报名账号补建（待转正）'
                WHEN note LIKE '%初审报名自动建号%' THEN '初审报名自动建号（待转正）'
                ELSE note END
            WHERE level='初审' AND (note LIKE '%报名账号补建%' OR note LIKE '%初审报名自动建号%')
              AND account_id NOT IN (SELECT DISTINCT account_id FROM permission WHERE recycled=0)
        """).rowcount
        if n_pending:
            print("数据迁移：%d 个报名自动建号账号 初审→待转正" % n_pending)
        n3 = conn.execute("UPDATE permission SET status='待复权' WHERE status='执行复权中'").rowcount
        if n3:
            print("数据迁移：%d 条权限状态 执行复权中→待复权" % n3)
        n4 = conn.execute("UPDATE account SET status='待复权' WHERE status='执行复权中'").rowcount
        if n4:
            print("数据迁移：%d 个账号状态 执行复权中→待复权" % n4)
        # 评估已完成但结果仍为空/待评估的历史数据：按角色评估记录推导
        # （任一角色「不同意」→不通过；≥3 个角色且全部「同意」→通过转正；其余保持待评估）
        fixed = 0
        for tbl, ev in (("upgrade_apply", "upgrade_apply_eval"), ("category_expand", "category_expand_eval")):
            for row in conn.execute("SELECT id FROM %s WHERE eval_node='评估完成' AND (eval_result IS NULL OR eval_result='' OR eval_result='待评估')" % tbl).fetchall():
                ag = [x[0] for x in conn.execute("SELECT agree FROM %s WHERE apply_id=?" % ev, (row["id"],)).fetchall()]
                if not ag: continue
                if any(a == "不同意" for a in ag): res = "不通过"
                elif len(ag) >= 3 and all(a == "同意" for a in ag): res = "通过转正"
                else: continue
                conn.execute("UPDATE %s SET eval_result=?, eval_result_time=COALESCE(NULLIF(eval_result_time,''),?) WHERE id=?" % tbl,
                             (res, _now(), row["id"]))
                fixed += 1
        if fixed:
            print("数据迁移：%d 条已完成申请补齐评估结果" % fixed)
        # 历史报名申请账号补建（否则「待转正评估」等须本人登录的节点无法操作，流程卡死）
        now_ = _now()
        for row in conn.execute("SELECT DISTINCT apply_id FROM registration WHERE apply_id IS NOT NULL AND apply_id!=''").fetchall():
            aid_ = row["apply_id"]
            if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (aid_,)).fetchone():
                conn.execute("INSERT INTO account(account_id,display_name,level,status,join_date,note) VALUES(?,?,?,?,?,?)",
                             (aid_, aid_, "待转正", "正常", now_[:10], "报名账号补建（待转正）"))
                print("数据迁移：补建报名账号 %s（待转正，初始密码 %s@2026）" % (aid_, aid_))
        # 建立/补全高频查询索引（幂等；随数据增长避免列表/台账/日志查询变慢）
        _idx_specs = [
            ("idx_account_status", "account(status)"),
            ("idx_account_level", "account(level)"),
            ("idx_account_is_test", "account(is_test)"),
            ("idx_permission_recycled_acct", "permission(recycled, account_id)"),
            ("idx_permission_status", "permission(status)"),
            ("idx_change_log_account", "change_log(account_id)"),
            ("idx_change_log_operator", "change_log(operator)"),
            ("idx_change_log_time", "change_log(change_time)"),
            ("idx_login_log_account", "login_log(account_id)"),
            ("idx_login_log_time", "login_log(login_time)"),
            ("idx_leader_record_account", "leader_record(account_id)"),
            ("idx_account_capability_account", "account_capability(account_id)"),
            ("idx_registration_apply", "registration(apply_id)"),
            ("idx_upgrade_apply_account", "upgrade_apply(account_id)"),
            ("idx_status_strip_account", "status_strip_apply(target_account)"),
            ("idx_password_reset_account", "password_reset_request(account_id)"),
        ]
        for _in, _def in _idx_specs:
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS %s ON %s" % (_in, _def))
            except sqlite3.Error as _e:
                print("索引跳过 %s: %s" % (_in, _e))
        _idx_n = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'").fetchone()[0]
        print("数据迁移：确保高频索引就绪（自建索引 %d 个）" % _idx_n)
        conn.commit()
    finally:
        conn.close()


# 新团队岗位人选（来源：新团队人员明细.xlsx，2026-09 任命）
# 大团队(域名与 category_dict.domain 一致) → 负责人 / 质量组长(副负责人/质量负责人) / 特色小组长(二级组)
TEAM_SEED = {
    "大文娱": {
        "负责人": "LionheartY", "质量组长": "易尘Eason",
        "groups": {"影视音综": "Retingber", "娱乐人物": "愛東的賢", "ACGN": "新日暮里跤王", "体育": "无所谓的下限"},
    },
    "人文历史": {
        "负责人": "lhl889", "质量组长": "A信服谎言A",
        "groups": {"地理": "gfy326956493", "历史": "小麒涵", "文学": "EQLWGRX"},
    },
    "科技工程": {
        "负责人": "快乐无极限3838", "质量组长": "TR小米哥",
        "groups": {"军事": "清风亦客", "交通": "林冥xxk", "工程/航天": "糯糯咕噜", "科技": "玩心Z少年"},
    },
    "科教自然": {
        "负责人": "迷茫的大将军", "质量组长": "辣条让我堕落",
        # xlsx「高校专业特色小组长」对应 category_dict 二级组「学科专业」
        "groups": {"教育与科学研究": "繁华落尽小涛", "动植物": "椿兮如霖", "化学": "Lucky布瓜", "学科专业": "大罗与互联网"},
    },
}
# 评审委员会成员（委员会整体负责人）
COMMITTEE_SEED = ["Voyageur70", "小航jason"]
# 评审相关负责人（eval_role_assign）
EVAL_LEAD_SEED = [("评审相关负责人", "Adzwlqxm", "")]


def migrate_team_config():
    """团队配置迁移：
    1) leader_record 补 scope 列（管辖范围：团队负责人/质量组长→大团队；特色小组长→二级组）；
    2) 将 3 个原挂在「科技工程」组下的交通类分类归并至「交通」二级组（与《评审权限统计表》口径一致）；
    3) 按 TEAM_SEED 幂等播种 团队负责人/质量组长/特色小组长/评审委员会成员 及评审角色绑定。
    """
    conn = get_conn()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(leader_record)")}
        if "scope" not in cols:
            conn.execute("ALTER TABLE leader_record ADD COLUMN scope TEXT DEFAULT ''")
        # 交通二级组归并（幂等）
        n = conn.execute("UPDATE category_dict SET group_name='交通' WHERE group_name='科技工程' AND category IN ('铁路线路','城市轨道交通线路','港口口岸（码头）')").rowcount
        if n:
            print("数据迁移：%d 个分类归并至二级组「交通」" % n)
        now = _now()
        seeded = 0
        def _ensure_acct(aid):
            if not conn.execute("SELECT 1 FROM account WHERE account_id=?", (aid,)).fetchone():
                conn.execute("INSERT INTO account(account_id,display_name,level,status,join_date,note) VALUES(?,?,?,?,?,?)",
                             (aid, aid, "中审", "正常", now[:10], "团队配置自动建号"))
        for domain, cfg in TEAM_SEED.items():
            for role, aid in (("团队负责人", cfg["负责人"]), ("质量组长", cfg["质量组长"])):
                _ensure_acct(aid)
                ex = conn.execute("SELECT id,scope FROM leader_record WHERE account_id=? AND role=?", (aid, role)).fetchone()
                if ex:
                    conn.execute("UPDATE leader_record SET status='在任', scope=?, updated_at=? WHERE id=?", (domain, now, ex["id"]))
                else:
                    conn.execute("INSERT INTO leader_record(account_id,role,status,time,owner,note,operator,scope,created_at,updated_at) VALUES(?,?, '在任',?,'','','系统',?,?,?)",
                                 (aid, role, now[:10], domain, now, now))
                seeded += 1
        for domain, cfg in TEAM_SEED.items():
            for gname, aid in cfg["groups"].items():
                _ensure_acct(aid)
                ex = conn.execute("SELECT id FROM leader_record WHERE account_id=? AND role=?", (aid, EXTRA_ADMIN_ROLE)).fetchone()
                if ex:
                    conn.execute("UPDATE leader_record SET status='在任', scope=?, updated_at=? WHERE id=?", (gname, now, ex["id"]))
                else:
                    conn.execute("INSERT INTO leader_record(account_id,role,status,time,owner,note,operator,scope,created_at,updated_at) VALUES(?,?, '在任',?,'','','系统',?,?,?)",
                                 (aid, EXTRA_ADMIN_ROLE, now[:10], gname, now, now))
                seeded += 1
        for aid in COMMITTEE_SEED:
            _ensure_acct(aid)
            ex = conn.execute("SELECT id FROM leader_record WHERE account_id=? AND role='评审委员会成员'", (aid,)).fetchone()
            if ex:
                conn.execute("UPDATE leader_record SET status='在任', updated_at=? WHERE id=?", (now, ex["id"]))
            else:
                conn.execute("INSERT INTO leader_record(account_id,role,status,time,owner,note,operator,scope,created_at,updated_at) VALUES(?, '评审委员会成员', '在任',?,'','','系统','',?,?)",
                             (aid, now[:10], now, now))
            seeded += 1
        for role, aid, cat in EVAL_LEAD_SEED:
            _ensure_acct(aid)
            if not conn.execute("SELECT 1 FROM eval_role_assign WHERE role=? AND account_id=? AND category=?", (role, aid, cat)).fetchone():
                conn.execute("INSERT INTO eval_role_assign(role,account_id,category,created_at,updated_at) VALUES(?,?,?,?,?)",
                             (role, aid, cat, now, now))
            seeded += 1
        conn.commit()
        if seeded:
            print("团队配置播种完成：%d 项（团队负责人/质量组长/特色小组长/评审委员会成员/评审相关负责人）" % seeded)
    finally:
        conn.close()


def migrate_violation_fields():
    """为违规/申诉联动补足字段（违规挂起权限、申诉撤销违规、处分期限流转）。"""
    conn = get_conn()
    try:
        # violation_record：补 category / perm_id / perm_prev_status / status
        cols = {r[1] for r in conn.execute("PRAGMA table_info(violation_record)")}
        for col, ddl in [
            ("category", "TEXT DEFAULT ''"),
            ("perm_id", "INTEGER DEFAULT 0"),
            ("perm_prev_status", "TEXT DEFAULT ''"),
            ("status", "TEXT DEFAULT '生效'"),
            ("penalty_term", "INTEGER DEFAULT 0"),
            ("penalty_due", "TEXT DEFAULT ''"),
            ("restored_at", "TEXT DEFAULT ''"),
        ]:
            if col not in cols:
                conn.execute("ALTER TABLE violation_record ADD COLUMN %s %s" % (col, ddl))
        # referrer_liability：若不存在则建表（含唯一约束）
        if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='referrer_liability'").fetchone():
            conn.execute("""CREATE TABLE referrer_liability(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                violation_id INTEGER, violator_account TEXT, referrer_account TEXT,
                category TEXT, level TEXT, penalty TEXT, status TEXT DEFAULT '待处理',
                handled_by TEXT, handled_time TEXT, note TEXT,
                created_at TEXT, updated_at TEXT,
                UNIQUE(violation_id))""")
        conn.commit()
    finally:
        conn.close()

def migrate_phase19():
    """Phase XIX：抽查记录（7.1）与再训复权（6.4）表迁移，兼容既有数据库。"""
    conn = get_conn()
    try:
        if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='spot_check'").fetchone():
            conn.execute("""CREATE TABLE spot_check(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT, account_id TEXT, category TEXT,
                total_versions INTEGER DEFAULT 0,
                sample_need INTEGER DEFAULT 0, main_need INTEGER DEFAULT 0, sub_need INTEGER DEFAULT 0,
                sampled INTEGER DEFAULT 0, problem_versions INTEGER DEFAULT 0,
                level TEXT DEFAULT '', handling TEXT DEFAULT '', is_official INTEGER DEFAULT 0,
                checker TEXT, check_time TEXT, note TEXT,
                operator TEXT, created_at TEXT, updated_at TEXT)""")
        if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reinstate_apply'").fetchone():
            conn.execute("""CREATE TABLE reinstate_apply(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT, category TEXT, target_level TEXT DEFAULT '初审',
                status TEXT DEFAULT '待审核', apply_time TEXT,
                official_versions INTEGER DEFAULT 0, main_cat_versions INTEGER DEFAULT 0,
                accuracy REAL DEFAULT 0, prior_reinstated_at TEXT,
                extend_count INTEGER DEFAULT 0, cancel_count INTEGER DEFAULT 0,
                block_until TEXT, result_time TEXT, owner TEXT, note TEXT,
                operator TEXT, created_at TEXT, updated_at TEXT)""")
        # Phase XX：7.3 回避字段（appeal_record / spot_check）
        acols = {r[1] for r in conn.execute("PRAGMA table_info(appeal_record)")}
        for col, ddl in [("recused", "INTEGER DEFAULT 0"), ("recuser", "TEXT DEFAULT ''"), ("recuse_reason", "TEXT DEFAULT ''")]:
            if col not in acols:
                conn.execute("ALTER TABLE appeal_record ADD COLUMN %s %s" % (col, ddl))
        scols = {r[1] for r in conn.execute("PRAGMA table_info(spot_check)")}
        for col, ddl in [("recused", "INTEGER DEFAULT 0"), ("recuser", "TEXT DEFAULT ''"), ("recuse_reason", "TEXT DEFAULT ''")]:
            if col not in scols:
                conn.execute("ALTER TABLE spot_check ADD COLUMN %s %s" % (col, ddl))
        # Phase XX：5.6 实习期跟踪字段
        pcols = {r[1] for r in conn.execute("PRAGMA table_info(permission)")}
        if "internship_start" not in pcols:
            conn.execute("ALTER TABLE permission ADD COLUMN internship_start TEXT DEFAULT ''")
        conn.commit()
    finally:
        conn.close()

def migrate_phase21():
    """Phase XXI：6.6 指南复训记录表（retrain_record）、4.4 再训要求字段（account.need_retrain）。"""
    conn = get_conn()
    try:
        if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='retrain_record'").fetchone():
            conn.execute("""CREATE TABLE retrain_record(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guide_version TEXT DEFAULT '',
                title TEXT DEFAULT '',
                participants TEXT DEFAULT '',
                start_date TEXT, end_date TEXT,
                status TEXT DEFAULT '待开展',
                pass_count INTEGER DEFAULT 0, total_count INTEGER DEFAULT 0,
                operator TEXT, note TEXT,
                created_at TEXT, updated_at TEXT)""")
        acols = {r[1] for r in conn.execute("PRAGMA table_info(account)")}
        if "need_retrain" not in acols:
            conn.execute("ALTER TABLE account ADD COLUMN need_retrain INTEGER DEFAULT 0")
        conn.commit()
    finally:
        conn.close()

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    init_db()
    migrate()
    migrate_team_config()
    migrate_violation_fields()
    migrate_phase19()
    migrate_phase21()
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    # 多线程处理：单个请求（如大导出、慢查询）阻塞时不再拖垮全局；
    # daemon_threads 保证进程可随时退出，request_queue_size 提高瞬时并发排队能力。
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer.request_queue_size = 128
    server = ThreadingHTTPServer((host, port), Handler)
    net_desc = "所有网卡(0.0.0.0)" if host == "0.0.0.0" else host
    print("权限统计与考核系统已启动： http://%s:%d（多线程模式，监听%s，便于部署到服务器后对外访问）" % (host, port, net_desc))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("已停止")

if __name__ == "__main__":
    main()
