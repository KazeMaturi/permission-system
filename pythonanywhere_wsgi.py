# PythonAnywhere WSGI 文件模板
# 用法：把本文件【全部内容】复制到 PythonAnywhere 控制台
#       Dashboard → Web → 你的域名 → WSGI configuration file
#       默认路径：/var/www/<你的PA用户名>_pythonanywhere_com_wsgi.py
# 然后点页面右上角「Reload <你的域名>」。
import sys
import os

# 项目在 PythonAnywhere 上的绝对路径（按实际用户名修改）
PROJECT_DIR = "/home/<你的PA用户名>/permission-system"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

# 部署环境切换（"区分口"）：决定 app.py 使用哪个数据库文件。
#   - 不设置 / prod  -> permission.db      （生产 / 上线环境）
#   - test           -> permission_test.db （对外测试环境）
# 推荐在 PythonAnywhere 控制台 Web 页「Environment variables」里设置 DEPLOY_ENV，
# 无需改本文件。下面这行仅作本地覆盖示例（默认注释掉）：
# os.environ["DEPLOY_ENV"] = "test"

# 复用 wsgi.py 中的零侵入 WSGI 适配层（业务逻辑完全不变）
from wsgi import application
