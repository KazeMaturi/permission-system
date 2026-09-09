# PythonAnywhere WSGI 文件模板 ——【对外测试应用专用】
# 与 pythonanywhere_wsgi.py 唯一区别：强制 DEPLOY_ENV=test，
# 使 app.py 使用 permission_test.db（与生产的 permission.db 完全隔离）。
#
# 用法：在 PythonAnywhere 新建第二个 Web app（如 <你的PA用户名>-test.pythonanywhere.com），
# 把本文件【全部内容】粘贴到该 app 的 WSGI configuration file
# （路径 /var/www/<测试域名>_pythonanywhere_com_wsgi.py），然后点 Reload。
# 注意：项目目录仍指向同一个 ~/permission-system（代码共用，仅数据库文件不同）。
import sys
import os

# 项目在 PythonAnywhere 上的绝对路径（按实际用户名修改）
PROJECT_DIR = "/home/<你的PA用户名>/permission-system"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

# 关键区分口：测试应用使用独立数据库 permission_test.db
os.environ["DEPLOY_ENV"] = "test"

# 复用 wsgi.py 中的零侵入 WSGI 适配层（业务逻辑完全不变）
from wsgi import application
