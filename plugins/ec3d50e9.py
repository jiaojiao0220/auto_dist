# CSDN 自动化插件
#
# 分发流程:
#   1. 点击"创作"按钮 (可能在新标签页打开编辑器)
#   2. 检查并点击富文本编辑器按钮 (切换到富文本模式)
#   3. 输入标题
#   4. 粘贴内容 (HTML, 含图片)
#   5. 选择标签
#   6. 关闭标签选择
#   7. 点击发布
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


def is_logged_in(page, context=None):
    """
    检查是否已登录CSDN
    通过多种方式检测登录状态，确保结果可靠
    """
    import time as _time

    # 确保在 CSDN 主站上检查（其他页面可能没有工具栏）
    current_url = page.url or ""
    if "csdn.net" not in current_url or "passport.csdn.net" in current_url:
        pass
        try:
            page.goto("https://www.csdn.net", wait_until="domcontentloaded", timeout=15000)
        except Exception:
            try:
                page.goto("https://www.csdn.net")
            except Exception:
                pass

    # 等待页面基本加载
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        pass

    # 最多重试 3 次
    for attempt in range(3):
        try:
            # 方法1: 检查工具栏
            try:
                page.wait_for_selector("#csdn-toolbar", timeout=8000)
            except Exception:
                if attempt < 2:
                    pass
                    _time.sleep(2)
                    continue

            toolbar = page.query_selector("#csdn-toolbar")
            if toolbar:
                text = toolbar.inner_text()
                # 如果有"登录"按钮且没有"退出"/"我的"等字样 → 未登录
                has_login_btn = "登录" in text
                has_user_indicator = any(kw in text for kw in ["退出", "我的", "消息", "创作", "会员"])
                if has_login_btn and not has_user_indicator:
                    pass
                    return False
                if has_user_indicator:
                    pass
                    return True
                # 文字不明确，继续用其他方法
            else:
                if attempt < 2:
                    pass
                    _time.sleep(2)
                    continue

            # 方法2: 检查 cookies 中是否有登录态
            try:
                cookies = context.cookies() if context else page.context.cookies()
                has_user_cookie = any(
                    c["name"] in ("UserName", "userInfo", "uuid_tt_dd", "ssxmod_itna")
                    and c.get("value", "")
                    for c in cookies
                    if "csdn.net" in c.get("domain", "")
                )
                if has_user_cookie:
                    pass
                    return True
            except Exception:
                pass

            # 方法3: 检查页面是否有用户头像等元素
            try:
                avatar = page.query_selector(".toolbar-submenu-box .avatar, .user-avatar, [class*='avatar']")
                if avatar:
                    pass
                    return True
            except Exception:
                pass

            if attempt < 2:
                pass
                _time.sleep(2)
                continue

            # 最后一次尝试仍无法确定
            pass
            return False

        except Exception as e:
            pass
            if attempt < 2:
                _time.sleep(2)
                continue
            return False

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


def distribute(page, context, title, content):
    """
    分发内容到CSDN

    page: Playwright Page 对象 (初始页面)
    context: Playwright BrowserContext 对象 (用于管理多标签页)
    title: 文章标题
    content: HTML内容 (含图片) 或纯文本
    """
    print(f"========== 开始分发 ==========")
    pass
    pass

    # ========== 0. 清理上次分发遗留的编辑器标签页 ==========
    pages_to_close = []
    for p in context.pages:
        if p == page:
            continue
        purl = p.url or ""
        if "editor.csdn.net/md" in purl or "mp.csdn.net/mp_blog/creation/editor" in purl:
            pages_to_close.append(p)
    for p in pages_to_close:
        try:
            p.close()
        except Exception:
            pass
    if pages_to_close:
        time.sleep(1)

    # ========== 1. 打开编辑器（点击"创作" → 新标签；再点"富文本" → 富文本编辑器新标签） ==========
    # 说明：方案A 的"直接 goto 富文本地址"在无头下会落回 CSDN 通用页（诊断只看到"搜CSDN"顶栏），无法定位编辑器，
    # 故回退为点击按钮的路线。新标签页一律用"轮询 context.pages"检测（第十七次验证，无头下比 expect_page 可靠）。
    print("[1/6] 打开编辑器...")
    editor_page = page
    current_url = page.url or ""

    if "editor.csdn.net" in current_url or "/md" in current_url or "mp.csdn.net" in current_url:
        editor_page = page
    else:
        try:
            page.wait_for_selector("#csdn-toolbar", timeout=10000)
            create_btn = page.locator('xpath=//*[@id="csdn-toolbar"]/div/div/div[3]/div/div[4]/a')
            create_btn.wait_for(state="visible", timeout=10000)

            # 记录点击前的页面对象，轮询检测新打开的标签页（无头下比 expect_page 可靠）
            pages_before_ids = {id(p) for p in context.pages}
            create_btn.click()

            new_editor = None
            for _ in range(30):  # 最多约 15 秒
                for p in context.pages:
                    if id(p) in pages_before_ids:
                        continue
                    purl = p.url or ""
                    if "editor.csdn.net" in purl or "mp.csdn.net" in purl:
                        new_editor = p
                        break
                if new_editor is None:
                    for p in context.pages:
                        if id(p) in pages_before_ids:
                            continue
                        new_editor = p
                        break
                if new_editor is not None:
                    try:
                        new_editor.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    editor_page = new_editor
                    break
                time.sleep(0.5)

            # 兜底：若没有新标签，则原地跳转到 Markdown 编辑器
            if editor_page == page:
                try:
                    page.goto("https://editor.csdn.net/md")
                    editor_page = page
                except Exception:
                    pass
        except Exception as e:
            try:
                page.goto("https://editor.csdn.net/md")
                editor_page = page
            except Exception:
                raise Exception(f"无法打开编辑器: {e}")

    # 点击"富文本编辑器"按钮 → 切换到富文本编辑器页
    print("  点击富文本编辑器按钮...")

    # 富文本编辑器页面的 URL 标记与地址
    RICH_EDITOR_MARKER = "mp.csdn.net/mp_blog/creation/editor"
    RICH_EDITOR_URL = "https://mp.csdn.net/mp_blog/creation/editor"

    def _find_rich_editor(exclude_ids):
        """在 context.pages 中找出富文本编辑器页面；exclude_ids 不为空时只查新开的页面"""
        best = None
        for p in context.pages:
            if exclude_ids is not None and id(p) in exclude_ids:
                continue
            purl = p.url or ""
            if RICH_EDITOR_MARKER in purl:
                return p  # 精确命中富文本编辑器，直接返回
            # 兜底：接受任意 csdn 新标签（无头下优先取最先出现的新标签）
            if exclude_ids is not None and "csdn.net" in purl and best is None:
                best = p
        return best

    # 记录点击前的页面，用于检测"新打开的标签页"
    pages_before_ids = {id(p) for p in context.pages}

    # 尝试点击"富文本"按钮（无头下用 force=True 绕过可见性/稳定性检查，
    # 否则按钮可能被动画/遮罩挡住导致点击不真正触发、新标签打不开）
    rte_selectors = [
        'xpath=//nav//button[contains(., "富文本")]',
        'xpath=//button[contains(., "富文本")]',
        'xpath=/html/body/div[1]/div[1]/div[2]/div/div[1]/div[1]/nav/div[1]/button[4]',
        'css=nav button:nth-child(4)',
    ]
    for sel in rte_selectors:
        try:
            btn = editor_page.locator(sel)
            if btn.count() > 0:
                btn.first.click(force=True, timeout=5000)
                break
        except Exception:
            continue

    # 轮询等待富文本编辑器新标签页出现（无头模式比 expect_page 可靠）
    switched = False
    for _ in range(20):  # 最多约 10 秒
        found = _find_rich_editor(pages_before_ids)
        if found is not None:
            try:
                found.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            editor_page = found
            switched = True
            break
        time.sleep(0.5)

    # 兜底：无头下"富文本"按钮可能未成功打开新标签，则直接在当前页 goto 富文本编辑器地址
    # （不再依赖"开新标签"这个无头下不可靠的动作，加载到同一页即可，txtTitle 仍在富文本编辑器上）
    if not switched:
        print("  ⚠ 未检测到富文本新标签页，尝试直接导航到富文本编辑器...")
        try:
            editor_page.goto(RICH_EDITOR_URL, wait_until="domcontentloaded", timeout=20000)
            switched = True
        except Exception as e:
            print(f"  ⚠ 导航到富文本编辑器失败: {e}")

    if not switched:
        # 最后在现有页面中再找一次
        fallback = _find_rich_editor(None)
        if fallback is not None:
            editor_page = fallback
            switched = True

    if switched:
        print("  ✓ 已切换到富文本编辑器页")

    # 强制解析：进入标题输入前，再次确保 editor_page 指向富文本编辑器页。
    # 直接修复"检测到新标签页却不操作它"的问题——无论如何都用富文本编辑器页操作。
    final_rich = _find_rich_editor(None)
    if final_rich is not None:
        editor_page = final_rich

    try:
        editor_page.bring_to_front()
    except Exception:
        pass
    try:
        editor_page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(2)
    print(f"  当前编辑器页面: {editor_page.url}")

    # ========== 2. 输入标题 ==========
    print("[2/6] 输入标题...")
    title_entered = False

    # 选择器优先级：用户确认富文本编辑器页面标题即 //*[@id="txtTitle"]，放在首位；
    # 其余作为兜底。全部不中则走 JS 兜底。
    title_locators = [
        '//*[@id="txtTitle"]',
        '#txtTitle',
        'textarea#txtTitle',
        'input[placeholder*="标题"]',
        'input#txtTitle',
        'input.article-title',
        '[class*="article-title"] input',
        'textarea[placeholder*="标题"]',
    ]

    for sel in title_locators:
        try:
            loc = editor_page.locator(sel).first
            loc.wait_for(state="visible", timeout=8000)
            loc.click()
            time.sleep(0.3)
            # 清空已有内容
            editor_page.keyboard.press("Control+A")
            time.sleep(0.1)
            editor_page.keyboard.press("Delete")
            time.sleep(0.2)
            editor_page.keyboard.type(title, delay=30)
            time.sleep(0.5)
            print(f"  ✓ 已输入标题: {title}")
            title_entered = True
            break
        except Exception as e:
            print(f"  ✗ 定位失败: {sel} -> {e}")
            continue

    # 兜底：用 JS 直接定位"标题"输入框并写入（兼容 React 受控组件）
    if not title_entered:
        try:
            result = editor_page.evaluate('''(title) => {
                const inputs = Array.from(document.querySelectorAll('input, textarea'));
                const t = inputs.find(i =>
                    (i.placeholder || '').includes('标题') ||
                    (i.placeholder || '').toLowerCase().includes('title') ||
                    (i.id || '').toLowerCase().includes('title') ||
                    (i.name || '').toLowerCase().includes('title'));
                if (!t) return 'NO_TITLE_INPUT';
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(t, title);
                t.dispatchEvent(new Event('input', { bubbles: true }));
                t.dispatchEvent(new Event('change', { bubbles: true }));
                return 'OK';
            }''', title)
            if result == 'OK':
                print(f"  ✓ 已输入标题(JS兜底): {title}")
                title_entered = True
            else:
                print(f"  ⚠ JS兜底未找到标题输入框: {result}")
        except Exception as e:
            print(f"  ✗ JS兜底失败: {e}")

    if not title_entered:
        # 诊断: 打印当前页输入框信息 + 截图，便于据真实 DOM 修正选择器
        try:
            inputs_info = editor_page.evaluate('''() => {
                let inputs = Array.from(document.querySelectorAll("input, textarea, [contenteditable]"));
                return inputs.slice(0, 20).map(i => ({
                    tag: i.tagName, id: i.id, name: i.name,
                    placeholder: i.placeholder || "", class: i.className || "",
                    contenteditable: i.contentEditable, visible: i.offsetParent !== null
                }));
            }''')
            for info in inputs_info:
                print(f"    [input] {info}")
        except Exception:
            pass
        try:
            editor_page.screenshot(path="C:/Users/Admin/WorkBuddy/2026-08-04-09-33-27/debug_screenshot.png")
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
        tag_btn = editor_page.locator('button:has-text("添加标签"), #moreDiv button, [class*="tag"] button').first
        tag_btn.wait_for(state="visible", timeout=8000)
        tag_btn.click()
        time.sleep(2)

        # 选择第一个标签
        first_tag = editor_page.locator('[class*="tag"] span, #pane-0 span').first
        first_tag.wait_for(state="visible", timeout=5000)
        first_tag.click()
        time.sleep(1)
    except Exception as e:
        print(f"  ⚠ 选择标签失败(可忽略): {e}")

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
    publish_clicked = False
    # 用户确认富文本编辑器发布按钮即该 XPath，放在首位；其余作为兜底。
    publish_locators = [
        '//*[@id="moreDiv"]/div[13]/div/div/div[2]/button[3]/span',
        'button:has-text("发布")',
        'button:has-text("发布文章")',
        'text=发布文章',
        '[class*="publish"] button',
    ]
    for sel in publish_locators:
        try:
            btn = editor_page.locator(sel).first
            btn.wait_for(state="visible", timeout=8000)
            btn.click()
            print("  已点击发布按钮")
            publish_clicked = True
            break
        except Exception as e:
            print(f"  ✗ 发布按钮定位失败: {sel} -> {e}")
            continue
    if not publish_clicked:
        raise Exception("找不到发布按钮")

    time.sleep(5)
    print(f"========== 分发完成: {title} ==========")
    return "发布成功"


def _paste_content(page, content):
    """
    将HTML内容粘贴到富文本编辑器

    策略:
    1. 优先使用剪贴板API粘贴HTML (保留格式和图片)
    2. 如果剪贴板失败，使用 execCommand insertHTML
    3. 如果都失败，使用 fill 直接输入纯文本
    """
    # 方法1: 使用剪贴板API
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

        # 尝试多种方式定位编辑器
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

    # 方法2: 使用 execCommand insertHTML
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

    # 方法2.5: 直接设置 contenteditable 的 innerHTML (headless 下剪贴板常不可用，此方式最可靠)
    try:
        page.evaluate("""(html) => {
            var editor = document.querySelector('[contenteditable="true"]')
                || document.querySelector('.ProseMirror')
                || document.querySelector('.ql-editor')
                || document.querySelector('.editor-content');
            if (editor) {
                editor.focus();
                editor.innerHTML = html;
                editor.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }""", content)
        time.sleep(1)
        return
    except Exception as e:
        pass

    # 方法3: 直接输入纯文本
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
