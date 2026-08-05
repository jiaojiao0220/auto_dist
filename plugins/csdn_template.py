# CSDN 自动化插件
#
# 分发流程:
#   1. 点击"创作"按钮 (可能在新标签页打开编辑器)
#   2. 输入标题
#   3. 粘贴内容 (HTML, 含图片)
#   4. 选择标签
#   5. 关闭标签选择
#   6. 点击发布
#
# page: Playwright Page 对象
# context: Playwright BrowserContext 对象
# title: 文章标题 (字符串)
# content: HTML内容 (含图片, 从Word解析) 或纯文本

import time
import logging

logger = logging.getLogger(__name__)


def on_open(page, context):
    """浏览器打开时调用"""
    page.goto("https://www.csdn.net")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass


def is_logged_in(page):
    """
    检查是否已登录CSDN
    通过检查工具栏是否有"登录"按钮来判断
    """
    try:
        page.wait_for_selector("#csdn-toolbar", timeout=10000)
        toolbar = page.query_selector("#csdn-toolbar")
        if toolbar:
            text = toolbar.inner_text()
            if "登录" in text and "退出登录" not in text:
                return False
            return True
        return False
    except Exception as e:
        logger.warning(f"检查登录状态时出错: {e}")
        return False


def login(page, context):
    """自动登录流程"""
    try:
        page.goto("https://passport.csdn.net/login")
        print("请在浏览器中完成登录...")
    except Exception:
        pass
    try:
        page.wait_for_url("**/www.csdn.net**", timeout=300000)
        print("登录成功!")
    except Exception:
        print("登录超时，请重试")


def distribute(page, title, content):
    """
    分发内容到CSDN

    title: 文章标题
    content: HTML内容 (含图片) 或纯文本
    """
    print(f"========== 开始分发 ==========")
    pass
    pass

    # ========== 1. 点击"创作"按钮 / 导航到编辑器 ==========
    print("[1/6] 打开编辑器...")
    editor_page = None

    current_url = page.url or ""
    pass

    if "editor.csdn.net" in current_url or "/md" in current_url:
        pass
        editor_page = page
    else:
        try:
            page.wait_for_selector("#csdn-toolbar", timeout=10000)
            create_btn = page.locator('xpath=//*[@id="csdn-toolbar"]/div/div/div[3]/div/div[4]/a')
            create_btn.wait_for(state="visible", timeout=10000)

            context = page.context
            pages_before = len(context.pages)

            create_btn.click()
            pass

            time.sleep(3)

            if len(context.pages) > pages_before:
                editor_page = context.pages[-1]
                pass
                try:
                    editor_page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass
            else:
                editor_page = page
                pass
                try:
                    editor_page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass

        except Exception as e:
            pass
            pass
            try:
                page.goto("https://editor.csdn.net/md")
                editor_page = page
                try:
                    editor_page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass
                pass
            except Exception as e2:
                raise Exception(f"无法打开编辑器: {e} / {e2}")

    pass
    try:
        editor_page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(2)

    # ========== 2. 输入标题 ==========
    print("[2/6] 输入标题...")
    title_entered = False

    title_selectors = [
        ('xpath', '//*[@id="txtTitle"]'),
        ('css', '#txtTitle'),
        ('css', 'input[placeholder*="标题"]'),
        ('css', 'input[placeholder*="title"]'),
        ('css', '.article-bar input'),
    ]

    for selector_type, selector in title_selectors:
        try:
            if selector_type == 'xpath':
                loc = editor_page.locator(f'xpath={selector}')
            else:
                loc = editor_page.locator(selector)

            pass
            loc.wait_for(state="visible", timeout=10000)
            loc.click()
            time.sleep(0.3)
            loc.fill("")
            loc.type(title, delay=30)
            print(f"  ✓ 已输入标题: {title}")
            title_entered = True
            break
        except Exception as e:
            print(f"  ✗ 定位失败: {e}")
            continue

    if not title_entered:
        pass
        try:
            inputs_info = editor_page.evaluate('() => Array.from(document.querySelectorAll("input")).map(i => ({id: i.id, name: i.name, placeholder: i.placeholder, class: i.className})).slice(0, 10)')
            pass
        except Exception:
            pass
        raise Exception("输入标题失败: 所有选择器都无法定位标题输入框")

    time.sleep(1)

    # ========== 3. 粘贴内容 ==========
    print("[3/6] 粘贴内容...")
    try:
        _paste_content(editor_page, content)
        print("  ✓ 内容已粘贴")
    except Exception as e:
        print(f"  ✗ 粘贴内容失败: {e}")

    time.sleep(3)

    # ========== 4. 选择标签 ==========
    print("[4/6] 选择标签...")
    try:
        tag_btn = editor_page.locator('xpath=//*[@id="moreDiv"]/div[1]/div[2]/div/div[1]/span/button/span')
        tag_btn.wait_for(state="visible", timeout=10000)
        tag_btn.click()
        pass
        time.sleep(2)

        first_tag = editor_page.locator('xpath=//*[@id="pane-0"]/span[1]/span')
        first_tag.wait_for(state="visible", timeout=5000)
        first_tag.click()
        pass
        time.sleep(1)
    except Exception as e:
        pass

    # ========== 5. 关闭标签选择 ==========
    print("[5/6] 关闭标签选择...")
    try:
        close_btn = editor_page.locator('xpath=//*[@id="el_mcm-id-3441-7"]/div/div[4]/button/svg')
        if close_btn.is_visible():
            close_btn.click()
            pass
        else:
            editor_page.keyboard.press("Escape")
            pass
    except Exception:
        try:
            editor_page.keyboard.press("Escape")
            pass
        except Exception:
            pass

    time.sleep(1)

    # ========== 6. 点击发布 ==========
    print("[6/6] 点击发布...")
    try:
        publish_btn = editor_page.locator('xpath=//*[@id="moreDiv"]/div[13]/div/div/div[2]/button[3]/span')
        publish_btn.wait_for(state="visible", timeout=10000)
        publish_btn.click()
        print("  已点击发布按钮")
    except Exception as e:
        pass
        try:
            editor_page.click('text=发布文章', timeout=5000)
            pass
        except Exception:
            raise Exception(f"找不到发布按钮: {e}")

    time.sleep(5)
    print(f"========== 分发完成: {title} ==========")
    return "发布成功"


def _paste_content(page, content):
    """将HTML内容粘贴到富文本编辑器"""
    try:
        page.evaluate("""
            async (html) => {
                const blob = new Blob([html], {type: 'text/html'});
                const textBlob = new Blob([html.replace(/<[^>]+>/g, '')], {type: 'text/plain'});
                const item = new ClipboardItem({
                    'text/html': blob,
                    'text/plain': textBlob
                });
                await navigator.clipboard.write([item]);
            }
        """, content)

        editor_located = False
        for selector in [
            'xpath=/html/body',
            '.editor-content',
            '[contenteditable="true"]',
            '.ProseMirror',
            '.ql-editor',
            '#editor',
            'article[contenteditable]',
            '.markdown-editor',
        ]:
            try:
                if selector.startswith('xpath'):
                    el = page.locator(selector)
                else:
                    el = page.locator(selector).first
                if el.is_visible():
                    el.click()
                    editor_located = True
                    pass
                    break
            except Exception:
                continue

        if editor_located:
            time.sleep(0.5)
            page.keyboard.press("Control+V")
            time.sleep(2)
            return
    except Exception as e:
        pass

    try:
        page.evaluate("""
            (html) => {
                var editor = document.querySelector('[contenteditable="true"]')
                    || document.querySelector('.ProseMirror')
                    || document.querySelector('.ql-editor')
                    || document.body;
                if (editor) {
                    editor.focus();
                    document.execCommand('insertHTML', false, html);
                }
            }
        """, content)
        time.sleep(1)
        return
    except Exception as e:
        pass

    pass
    import re
    plain_text = re.sub(r'<[^>]+>', '\n', content)
    plain_text = re.sub(r'\n{3,}', '\n\n', plain_text).strip()
    try:
        page.keyboard.type(plain_text, delay=10)
    except Exception as e:
        raise Exception(f"所有粘贴方式均失败: {e}")


def on_close(page, context):
    """浏览器关闭时调用"""
    print("CSDN浏览器关闭")
