"""全局配置 - 路径和常量"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.resolve()

# 平台配置目录 (JSON 文件)
PLATFORMS_DIR = BASE_DIR / "platforms"

# 插件代码目录 (Python 文件)
PLUGINS_DIR = BASE_DIR / "plugins"

# 浏览器数据目录 (持久化 cookies/localStorage)
BROWSER_DATA_DIR = BASE_DIR / "browser_data"

# 上传文件临时目录
UPLOAD_DIR = BASE_DIR / "uploads"

# 前端静态文件目录
WEB_DIR = BASE_DIR / "web"

# 确保目录存在
for d in [PLATFORMS_DIR, PLUGINS_DIR, BROWSER_DATA_DIR, UPLOAD_DIR, WEB_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 服务器配置
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8765"))

# 默认插件模板
DEFAULT_PLUGIN_TEMPLATE = '''# {name} 自动化插件
#
# 可用函数 (均为可选, 按需实现):
#
# on_open(page, context)           - 浏览器打开时调用, 通常用于导航到页面
# is_logged_in(page)               - 检查是否已登录, 返回 True / False
# login(page, context)             - 自动登录流程
# distribute(page, title, content) - 分发内容到平台
# on_close(page, context)          - 浏览器关闭时调用
#
# page: Playwright Page 对象    https://playwright.dev/python/docs/api/class-page
# context: Playwright BrowserContext 对象
# title: 字符串, 文档标题 (手动分发时可能为 None)
# content: 字符串, HTML内容 (从Word解析) 或纯文本 (手动输入)


def on_open(page, context):
    """浏览器打开时调用"""
    page.goto("{url}")


def is_logged_in(page):
    """检查是否已登录, 返回 True 或 False"""
    # TODO: 根据平台实际特征判断登录状态
    return False


def login(page, context):
    """自动登录流程 (留空则需用户手动登录)"""
    pass


def distribute(page, title, content):
    """分发内容到平台
    title: 文章标题
    content: HTML内容 (含图片) 或纯文本
    """
    pass
'''
