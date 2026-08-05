# 百家号 (baijiahao) 自动化插件
#
# 分发流程:
#   1. 打开编辑器页面 (授权状态下直接进入文章编辑页)
#   2. 输入标题 (用户提供 XPath, 限 2-64 个字)
#   3. 写入内容 (用户提供 XPath: /html/body/p, 富文本编辑区)
#   4. 点击发布按钮 (用户提供 XPath)
#
# 登录态由 Playwright 持久化上下文 (user_data_dir) 自动保存到本地,
# 首次未授权时跳转到百度登录页手动登录一次即可。
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
EDIT_URL = "https://baijiahao.baidu.com/builder/rc/edit?type=news&is_from_cms=1"
LOGIN_URL = "https://passport.baidu.com/v2/?login"

# 用户提供的精确 XPath (最高优先级)
TITLE_XPATH = '//*[@id="newsTextArea"]/div/div/div/div/div/div/div[1]/div/div[1]/div[1]'
CONTENT_XPATH = '/html/body/p'
PUBLISH_XPATH = '//*[@id="root"]/div/div[1]/div/div[2]/div/div/div[2]/div/span/span[2]/div[4]/button'

# 百家号标题限制: 2-64 个字
TITLE_MAX_LEN = 64
TITLE_MIN_LEN = 2


def on_open(page, context):
    """浏览器打开时调用, 导航到编辑页面"""
    print("导航到百家号编辑页面...")
    try:
        page.goto(EDIT_URL, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        try:
            page.goto(EDIT_URL, timeout=30000)
        except Exception as e:
            print(f"打开编辑页失败: {e}")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(2)


def is_logged_in(page, context=None):
    """
    检查是否已登录百家号

    授权状态下直接进入文章编辑页 (URL 含 builder/rc/edit, 且能找到标题框);
    未授权时跳转到 passport.baidu.com 登录页。
    """
    import time as _time

    current_url = (page.url or "").lower()

    # 明确登录页 → 未登录
    if "passport.baidu.com" in current_url or "/passport/" in current_url or "wappass" in current_url:
        print("检测到百度登录页, 未登录")
        return False

    # 未在百家号域名 → 导航到编辑页再判断
    if "baijiahao.baidu.com" not in current_url:
        try:
            page.goto(EDIT_URL, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            try:
                page.goto(EDIT_URL, timeout=20000)
            except Exception:
                return False
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        _time.sleep(2)
        current_url = (page.url or "").lower()
        if "passport.baidu.com" in current_url or "wappass" in current_url:
            print("重定向到百度登录页, 未登录")
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
    if "builder/rc/edit" in current_url or "baijiahao" in current_url:
        print("URL 在百家号编辑页, 视为已登录")
        return True
    return False


def login(page, context):
    """登录流程: 跳转百度登录页, 由用户在浏览器中完成授权, 登录态自动持久化"""
    print("跳转百度登录页, 请在浏览器中完成扫码/账号登录...")
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        try:
            page.goto(LOGIN_URL, timeout=30000)
        except Exception as e:
            print(f"打开登录页失败: {e}")
            return
    # 等待用户登录成功后回到百家号 (最长 5 分钟)
    try:
        page.wait_for_url("**/baijiahao.baidu.com/**", timeout=300000)
        print("登录成功! 已进入百家号")
    except Exception:
        print("登录超时, 请检查浏览器窗口或重试")


def distribute(page, context, title, content):
    """
    分发内容到百家号

    title: 文章标题
    content: HTML内容 (含图片) 或纯文本
    """
    # 标题限 2~64 个字, 超长截断 / 过短补默认
    if title:
        old_title = title
        if len(title) > TITLE_MAX_LEN:
            title = title[:TITLE_MAX_LEN]
            print(f"  标题超长 ({len(old_title)} 字 > {TITLE_MAX_LEN} 字), 截断为: {title}")
        if len(title) < TITLE_MIN_LEN:
            title = (title + "未命名文章")[:TITLE_MAX_LEN]
            print(f"  标题过短, 已补默认: {title}")

    print("========== 开始分发到百家号 ==========")

    # ========== 1. 确保在编辑页 ==========
    print("[1/4] 打开/确认编辑页...")
    editor_page = page
    current_url = (page.url or "").lower()
    if "baijiahao" not in current_url or "passport" in current_url:
        try:
            editor_page.goto(EDIT_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            try:
                editor_page.goto(EDIT_URL, timeout=30000)
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

    # ========== 2. 输入标题 ==========
    print("[2/4] 输入标题...")
    title_entered = False
    title_locators = [
        (f'xpath={TITLE_XPATH}', TITLE_XPATH),
        ('[contenteditable="true"][class*="title"], [data-placeholder*="标题"], [placeholder*="标题"]', None),
        ('#newsTextArea [contenteditable="true"]', None),
        ('input[placeholder*="标题"]', None),
    ]
    for selector, _desc in title_locators:
        try:
            loc = editor_page.locator(selector).first
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
                    let el = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    if (!el) {
                        el = document.querySelector('[contenteditable="true"]');
                    }
                    if (el) {
                        el.focus();
                        el.textContent = title;
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
                '() => Array.from(document.querySelectorAll("textarea, input, [contenteditable]")).map(i => ({tag: i.tagName, id: i.id, placeholder: i.placeholder || i.getAttribute("data-placeholder") || "", class: i.className})).slice(0, 10)'
            )
            print(f"  [调试] 页面输入元素: {info}")
        except Exception:
            pass
        raise Exception("输入标题失败: 所有选择器都无法定位标题输入框")

    time.sleep(1)
    _capture_page_hints(editor_page, "标题输入后")

    # ========== 3. 写入内容 ==========
    print("[3/4] 写入内容...")
    try:
        _write_content(editor_page, content)
        print("  ✓ 内容已写入")
    except Exception as e:
        print(f"  ✗ 写入内容失败: {e}")

    time.sleep(2)
    _capture_page_hints(editor_page, "内容写入后")

    # ========== 4. 点击发布 ==========
    print("[4/4] 点击发布...")
    publish_clicked = False
    try:
        publish_btn = editor_page.locator(f'xpath={PUBLISH_XPATH}')
        publish_btn.wait_for(state="visible", timeout=10000)
        publish_btn.click(force=True, timeout=5000)
        print("  已点击发布按钮")
        publish_clicked = True
    except Exception as e:
        print(f"  ✗ 点击发布失败: {e}")
        # 兜底: 按文本查找
        for text in ["发布", "发表"]:
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
        raise Exception("找不到发布按钮")

    # 捕获发布后的页面提示 (发布成功/失败/校验错误等)
    time.sleep(2)
    _capture_page_hints(editor_page, "发布后")

    time.sleep(5)
    print(f"========== 分发完成: {title} ==========")
    return "发布成功"


def _strip_base64_images(html: str) -> str:
    """
    剥离 HTML 中的 base64 内嵌图片 <img src="data:...;base64,...">

    Word 解析会把图片转成 base64 内嵌, 单张可达几十万字符, 导致平台报
    "正文长度超过限制"。多数平台不支持内嵌图, 直接移除 img 标签保留文本。
    """
    if not html or "data:image" not in html:
        return html
    cleaned = re.sub(r'<img[^>]*src="data:image[^"]*"[^>]*>', "", html, flags=re.IGNORECASE)
    if "data:image" in cleaned:
        cleaned = re.sub(r'<img[^>]*base64[^>]*>', "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _write_content(page, content):
    """
    写入文章内容到富文本编辑区

    优先 execCommand insertHTML, 兜底剪贴板粘贴, 再兜底纯文本逐字输入。
    Word 解析的 base64 内嵌图片先剥离, 避免正文超限。
    """
    clean_content = _strip_base64_images(content)
    if clean_content != content:
        print(f"  已剥离 {content.count('<img')} 个内嵌 base64 图片")

    # 定位内容编辑区 (用户提供 XPath: /html/body/p)
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

    # 先点击聚焦
    try:
        content_el.click(force=True, timeout=5000)
        time.sleep(0.5)
    except Exception:
        pass

    # 方式1: execCommand insertHTML (富文本保留格式)
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
            clean_content,
        )
        time.sleep(1)
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
            clean_content,
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
    plain_text = re.sub(r"<[^>]+>", "\n", clean_content)
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


def _capture_page_hints(page, label="页面提示"):
    """
    捕获页面上出现的提示信息 (toast/message/错误文本等), 打印到日志供前端展示
    """
    try:
        hints = page.evaluate(
            """() => {
                const sels = [
                    '.byte-toast', '.byte-toast-content', '.byte-message', '.byte-message-content',
                    '.byte-tooltip', '.semi-toast', '.semi-toast-content',
                    '.ant-message', '.ant-message-notice-content',
                    '[class*="toast"]', '[class*="Toast"]',
                    '[class*="message"]', '[class*="Message"]',
                    '[class*="notice"]', '[class*="Notice"]',
                    '[class*="error"]', '[class*="Error"]',
                    '[class*="tip"]', '[class*="Tip"]',
                    '.toast', '.toast-message', '[class*="toast-message"]',
                ];
                const out = [];
                const seen = new Set();
                for (const sel of sels) {
                    try {
                        for (const el of document.querySelectorAll(sel)) {
                            const style = window.getComputedStyle(el);
                            if (style.display === 'none' || style.visibility === 'hidden') continue;
                            const rect = el.getBoundingClientRect();
                            if (rect.width === 0 && rect.height === 0) continue;
                            const t = (el.innerText || el.textContent || '').trim();
                            if (t && t.length > 1 && t.length < 200 && !seen.has(t)) {
                                seen.add(t);
                                out.push(t);
                            }
                        }
                    } catch (e) {}
                }
                return out;
            }"""
        )
        if hints:
            for h in hints:
                warn = any(k in h for k in ["超", "限", "错误", "失败", "不能", "不可", "请", "无效", "超过", "最多"])
                print(f"  [{label}] {'⚠' if warn else 'ℹ'} {h}")
            return True
        return False
    except Exception as e:
        print(f"  [捕获页面提示失败] {e}")
        return False


def on_close(page, context):
    """浏览器关闭时调用"""
    print("百家号浏览器关闭")
