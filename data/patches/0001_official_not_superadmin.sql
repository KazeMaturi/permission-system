-- 补丁 0001：官方账号仅作管理员展示，非超级管理员、无系统管理权限（#307 纠偏）
-- 适用范围：所有环境（test / prod）。幂等，可重复执行。
-- 来源：本地对 du曦尧 撤销 system_admin/admin_grant 的修正，需同步到云端各环境。
-- 说明：官方账号的"超级管理员"身份由代码 is_super_admin() 控制，不依赖库内
--       admin_grant / system_admin；此处仅撤销此前被手动授予的 system_admin 与
--       admin_grant（若有），其余运营类能力保持不变。

UPDATE account_capability SET granted=0
WHERE account_id='du曦尧' AND capability='system_admin';

UPDATE account_capability SET granted=0
WHERE account_id='du曦尧' AND capability='admin_grant';
