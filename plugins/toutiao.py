# 今日头条 (toutiao) 自动化插件
#
# 分发流程:
#   1. 打开编辑器页面 (授权状态下直接进入图文编辑页)
#   2. 输入标题 (用户提供 XPath)
#   3. 写入内容 (用户提供 XPath, 富文本编辑区)
#   4. 选择无封面 (用户提供 XPath)
#   5. 点击预览发布按钮 (用户提供 XPath: .../div[3]/div/button[3])
#   6. 点击确定发布按钮 (用户提供 XPath: .../div[3]/div/button[2]/span)
#
# 注意: 头条编辑页有 AI 助手抽屉 (byte-drawer-mask) 会拦截点击,
#       进入页面后先尝试 Esc 关闭, 所有关键点击使用 force=True 绕过遮罩。
#
# 登录态由 Playwright 持久化上下文 (user_data_dir) 自动保存到本地,
# 首次未授权时 goto 到 https://mp.toutiao.com/auth/page/login 手动登录一次即可。
#
# page: Playwright Page 对象
# context: Playwright BrowserContext 对象
# title: 文章标题 (字符串)
# content: HTML内容 (含图片, 从Word解析) 或纯文本

import time
import re
import logging

logger = logging.getLogger(__name__)

# ===================== 常量 =====================
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
LOGIN_URL = "https://mp.toutiao.com/auth/page/login"

# 用户提供的精确 XPath (最高优先级)
TITLE_XPATH = '//*[@id="root"]/div/div[1]/div/div[1]/div[3]/div/div/div[2]/div/div/div/textarea'
CONTENT_XPATH = '//*[@id="root"]/div/div[1]/div/div[1]/div[4]/div/div[1]/p'
PUBLISH_XPATH = '//*[@id="root"]/div/div[1]/div/div[3]/div/button[3]/span'


def on_open(page, context):
    """浏览器打开时调用, 导航到编辑页面"""
    print("导航到今日头条编辑页面...")
    try:
        page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        try:
            page.goto(PUBLISH_URL, timeout=30000)
        except Exception as e:
            print(f"打开编辑页失败: {e}")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(2)


def is_logged_in(page, context=None):
    """
    检查是否已登录今日头条

    授权状态下直接进入图文编辑页 (URL 含 publish, 且能找到标题输入框);
    未授权时会被重定向到登录页 mp.toutiao.com/auth/page/login。
    """
    import time as _time

    current_url = (page.url or "").lower()

    # 明确登录页 → 未登录
    if "auth/page/login" in current_url or "/auth/" in current_url:
        print("检测到登录页, 未登录")
        return False

    # 未在头条域名 → 导航到编辑页再判断
    if "toutiao.com" not in current_url:
        try:
            page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            try:
                page.goto(PUBLISH_URL, timeout=20000)
            except Exception:
                return False
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        _time.sleep(2)
        current_url = (page.url or "").lower()
        if "auth/page/login" in current_url or "/auth/" in current_url:
            print("重定向到登录页, 未登录")
            return False

    # 尝试定位标题输入框 → 找到即已登录 (编辑页特征)
    for attempt in range(3):
        try:
            title_box = page.locator(f'xpath={TITLE_XPATH}')
            title_box.wait_for(state="visible", timeout=8000)
            print("检测到编辑页标题输入框, 已登录")
            return True
        except Exception:
            if attempt < 2:
                _time.sleep(2)
                continue
    # 标题框找不到, 再兜底判断 URL 是否在编辑页
    if "publish" in current_url:
        print("URL 在编辑页, 视为已登录")
        return True
    return False


def login(page, context):
    """登录流程: 跳转登录页, 由用户在浏览器中完成授权, 登录态自动持久化"""
    print("跳转今日头条登录页, 请在浏览器中完成扫码/账号登录...")
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        try:
            page.goto(LOGIN_URL, timeout=30000)
        except Exception as e:
            print(f"打开登录页失败: {e}")
            return
    # 等待用户登录成功后回到编辑页 (最长 5 分钟)
    try:
        page.wait_for_url("**/profile_v4/**", timeout=300000)
        print("登录成功! 已进入头条后台")
    except Exception:
        print("登录超时, 请检查浏览器窗口或重试")


def distribute(page, context, title, content):
    """
    分发内容到今日头条

    title: 文章标题
    content: HTML内容 (含图片) 或纯文本
    """
    print("========== 开始分发到今日头条 ==========")

    # ========== 1. 确保在编辑页 ==========
    print("[1/5] 打开/确认编辑页...")
    editor_page = page
    current_url = (page.url or "").lower()
    if "publish" not in current_url or "auth/" in current_url:
        try:
            editor_page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            try:
                editor_page.goto(PUBLISH_URL, timeout=30000)
            except Exception as e:
                raise Exception(f"无法打开编辑页: {e}")
        try:
            editor_page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(3)
    # 等待标题输入框出现
    try:
        editor_page.locator(f'xpath={TITLE_XPATH}').wait_for(state="visible", timeout=20000)
        print("  ✓ 已进入编辑页")
    except Exception:
        raise Exception("未找到标题输入框, 可能未登录或页面结构变化")

    # 头条编辑页有 AI 助手抽屉 (byte-drawer-mask), 其遮罩会拦截标题/内容区域的点击,
    # 先尝试用 Esc 关闭, 无法关闭时后续点击一律用 force=True 绕过拦截
    _close_ai_drawer(editor_page)

    # ========== 2. 输入标题 ==========
    print("[2/5] 输入标题...")
    title_entered = False
    title_locators = [
        (f'xpath={TITLE_XPATH}', TITLE_XPATH),
        ('textarea[placeholder*="标题"]', None),
        ('input[placeholder*="标题"]', None),
        ('textarea[class*="title"]', None),
        ('[contenteditable="true"][data-placeholder*="标题"]', None),
    ]
    for selector, _desc in title_locators:
        try:
            loc = editor_page.locator(selector)
            loc.wait_for(state="visible", timeout=5000)
            loc.click(force=True, timeout=5000)
            time.sleep(0.3)
            loc.fill("")
            loc.type(title, delay=30)
            print(f"  ✓ 已输入标题: {title}")
            title_entered = True
            break
        except Exception as e:
            print(f"  ✗ 定位失败({selector[:50]}): {e}")
            continue

    if not title_entered:
        # 兜底: 用 JS 直接赋值 (React 受控组件需要触发 input 事件)
        try:
            editor_page.evaluate(
                """(args) => {
                    const xpath = args.xpath, title = args.title;
                    let el = document.querySelector('textarea[placeholder*="标题"]');
                    if (!el) {
                        el = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    }
                    if (el) {
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                        setter.call(el, title);
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        return true;
                    }
                    return false;
                }""",
                {"xpath": TITLE_XPATH, "title": title},
            )
            print("  ✓ 已通过 JS 输入标题")
            title_entered = True
        except Exception as e:
            print(f"  ✗ JS 输入标题失败: {e}")

    if not title_entered:
        # 打印调试信息
        try:
            info = editor_page.evaluate(
                '() => Array.from(document.querySelectorAll("textarea, input")).map(i => ({tag: i.tagName, id: i.id, placeholder: i.placeholder, class: i.className})).slice(0, 10)'
            )
            print(f"  [调试] 页面输入框: {info}")
        except Exception:
            pass
        raise Exception("输入标题失败: 所有选择器都无法定位标题输入框")

    time.sleep(1)

    # ========== 3. 写入内容 ==========
    print("[3/5] 写入内容...")
    try:
        _write_content(editor_page, content)
        print("  ✓ 内容已写入")
    except Exception as e:
        print(f"  ✗ 写入内容失败: {e}")

    time.sleep(2)

    # ========== 4. 选择无封面 ==========
    print("[4/5] 选择无封面...")
    no_cover_clicked = False
    try:
        no_cover = editor_page.locator(
            'xpath=//*[@id="root"]/div/div[1]/div/div[2]/div[2]/div[1]/div/div[2]/div/div/label[3]/span/div'
        )
        no_cover.wait_for(state="visible", timeout=10000)
        no_cover.click(force=True, timeout=5000)
        print("  ✓ 已选择无封面")
        no_cover_clicked = True
    except Exception as e:
        print(f"  ✗ 选择无封面失败: {e}")
        # 兜底: 按文字找"无封面"
        try:
            label = editor_page.locator('label:has-text("无封面"), [class*="cover"] label:has-text("无")').last
            label.click(force=True, timeout=3000)
            print("  ✓ 已通过文字选择无封面")
            no_cover_clicked = True
        except Exception:
            pass

    time.sleep(1)

    # ========== 5. 点击预览发布 ==========
    print("[5/5] 点击预览发布...")
    publish_clicked = False
    try:
        publish_btn = editor_page.locator(f'xpath={PUBLISH_XPATH}')
        publish_btn.wait_for(state="visible", timeout=10000)
        publish_btn.click(force=True, timeout=5000)
        print("  已点击预览发布按钮")
        publish_clicked = True
    except Exception as e:
        print(f"  ✗ 点击预览发布失败: {e}")
        # 兜底: 按文本查找
        for text in ["发布", "预览", "发表"]:
            try:
                btn = editor_page.locator(f'button:has-text("{text}")').last
                btn.wait_for(state="visible", timeout=3000)
                btn.click(force=True, timeout=3000)
                print(f"  已通过文本[{text}]点击发布")
                publish_clicked = True
                break
            except Exception:
                continue

    if not publish_clicked:
        raise Exception("找不到预览发布按钮")

    # 等待弹窗/跳转, 处理可能的"确认发布"弹窗
    time.sleep(2)
    _confirm_publish_if_needed(editor_page)

    time.sleep(5)
    print(f"========== 分发完成: {title} ==========")
    return "发布成功"


def _close_ai_drawer(page):
    """
    关闭头条编辑页的 AI 助手抽屉

    头条页面存在 <div class="byte-drawer-mask"> / .ai-assistant-drawer,
    其遮罩会拦截标题/内容区域的 pointer events, 导致 click 一直重试超时。
    先按 Esc 尝试关闭; 若仍在, 尝试点击遮罩空白处关闭。
    """
    try:
        page.keyboard.press("Escape")
        time.sleep(0.8)
    except Exception:
        pass
    try:
        mask = page.locator(".byte-drawer-mask")
        if mask.count() > 0 and mask.first.is_visible():
            # 点击遮罩本身(边缘)关闭抽屉
            box = mask.first.bounding_box()
            if box:
                page.mouse.click(box["x"] + 5, box["y"] + box["height"] / 2)
                time.sleep(0.8)
                print("  ✓ 已关闭 AI 助手抽屉")
    except Exception:
        pass


def _write_content(page, content):
    """
    写入文章内容到富文本编辑区

    头条编辑区为 contenteditable, 优先使用 execCommand insertHTML,
    兜底使用剪贴板粘贴, 再兜底纯文本逐字输入。
    """
    _close_ai_drawer(page)
    # 定位内容编辑区 (用户提供 XPath, 是一个 <p> 元素, 一般位于 contenteditable 容器内)
    content_el = None
    for selector in [
        f'xpath={CONTENT_XPATH}',
        '[contenteditable="true"]',
        '.ProseMirror',
        '.ql-editor',
        '[contenteditable="true"] p',
    ]:
        try:
            loc = page.locator(selector).first
            if loc.is_visible():
                content_el = loc
                break
        except Exception:
            continue

    if content_el is None:
        raise Exception("找不到内容编辑区")

    # 先点击聚焦 (force 绕过遮罩拦截)
    try:
        content_el.click(force=True, timeout=5000)
        time.sleep(0.5)
    except Exception:
        pass

    # 方式1: execCommand insertHTML (富文本保留格式/图片)
    try:
        page.evaluate(
            """(html) => {
                const el = document.querySelector('[contenteditable="true"]') || document.querySelector('.ProseMirror') || document.querySelector('.ql-editor');
                if (el) {
                    el.focus();
                    const sel = window.getSelection();
                    sel.selectAllChildren(el);
                    document.execCommand('delete', false, null);
                    document.execCommand('insertHTML', false, html);
                    return true;
                }
                return false;
            }""",
            content,
        )
        time.sleep(1)
        # 验证内容是否写入
        text = _get_content_text(page)
        if text and len(text.strip()) > 5:
            return
    except Exception as e:
        print(f"  execCommand 方式失败: {e}")

    # 方式2: 剪贴板粘贴
    try:
        page.evaluate(
            """async (html) => {
                const blob = new Blob([html], {type: 'text/html'});
                const textBlob = new Blob([html.replace(/<[^>]+>/g, '')], {type: 'text/plain'});
                const item = new ClipboardItem({'text/html': blob, 'text/plain': textBlob});
                await navigator.clipboard.write([item]);
            }""",
            content,
        )
        try:
            content_el.click(force=True, timeout=5000)
        except Exception:
            pass
        time.sleep(0.5)
        page.keyboard.press("Control+V")
        time.sleep(2)
        text = _get_content_text(page)
        if text and len(text.strip()) > 5:
            return
    except Exception as e:
        print(f"  剪贴板方式失败: {e}")

    # 方式3: 纯文本逐字输入
    plain_text = re.sub(r"<[^>]+>", "\n", content)
    plain_text = re.sub(r"\n{3,}", "\n\n", plain_text).strip()
    try:
        page.keyboard.type(plain_text, delay=5)
        time.sleep(1)
        return
    except Exception as e:
        raise Exception(f"所有写入内容方式均失败: {e}")


def _get_content_text(page):
    """获取内容编辑区的文本, 用于验证是否写入成功"""
    try:
        return page.evaluate(
            """() => {
                const el = document.querySelector('[contenteditable="true"]') || document.querySelector('.ProseMirror') || document.querySelector('.ql-editor');
                return el ? el.innerText : '';
            }"""
        )
    except Exception:
        return ""


# 确定发布按钮 (预览发布后的确认弹窗, 用户提供 XPath, 最高优先级)
CONFIRM_XPATH = '//*[@id="root"]/div/div[1]/div/div[3]/div/button[2]/span'


def _confirm_publish_if_needed(page):
    """
    点击预览发布后, 等待预览发布界面加载完成, 再点击确定发布按钮

    关键点: 点击预览发布后界面需要时间加载(按钮处于 loading / 文本仍为
    "预览并发布"), 必须等加载完成、按钮文本变为"发布"后才能点击。
    期间同一 XPath 可能匹配到 2 个元素(loading 包装 span + 正常 span),
    因此用 .first 规避 strict mode, 并按文本排除"预览"状态。
    """
    # 1) 轮询等待预览界面加载完成 + 点击确定发布 (最长 30s, 每 1s 检查)
    #    精确匹配文本, 排除 "预览并发布" / "定时发布" 等非目标按钮
    CONFIRM_TEXTS = ("发布", "确定发布", "确认发布", "发表")
    for attempt in range(30):
        try:
            btn = page.locator(f'xpath={CONFIRM_XPATH}').first
            if btn.is_visible():
                text = (btn.inner_text() or "").strip()
                # 只有精确匹配确认文本才点击, 避免误点"定时发布"/"预览并发布"
                if text in CONFIRM_TEXTS:
                    btn.click(force=True, timeout=3000)
                    print(f"  ✓ 已点击确定发布按钮 (文本: {text})")
                    return
        except Exception:
            pass
        time.sleep(1)

    # 2) 兜底: 遍历可见按钮, 精确匹配确认文本, 排除"预览并发布"/"定时发布"
    try:
        for _ in range(10):
            buttons = page.locator("button:visible")
            count = buttons.count()
            for i in range(count):
                try:
                    b = buttons.nth(i)
                    text = (b.inner_text() or "").strip()
                    if text in CONFIRM_TEXTS:
                        b.click(force=True, timeout=3000)
                        print(f"  ✓ 已点击确定发布按钮 (兜底, 文本: {text})")
                        return
                except Exception:
                    continue
            time.sleep(1)
    except Exception:
        pass

    # 3) 仍未找到, 提示人工确认 (不再误点"预览并发布")
    print("  ⚠ 未找到确定发布按钮, 已跳过确认 (请人工在浏览器中确认发布)")


def on_close(page, context):
    """浏览器关闭时调用"""
    print("今日头条浏览器关闭")
