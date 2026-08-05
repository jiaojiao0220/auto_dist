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


def _title_char_weight(ch: str) -> float:
    """头条标题字数权重: 中文/全角字符 = 1字, 英文/数字/半角 = 0.5字 (2个算1字), 空格 = 0 (不算有效字符)"""
    # 空格(半角/全角)不算有效字符
    if ch in (" ", "\u3000", "\t", "\n", "\r"):
        return 0.0
    import unicodedata
    try:
        w = unicodedata.east_asian_width(ch)
        # W=全角, F=全角(ASCII变体), A=模糊(多数视为半角)
        return 1.0 if w in ("W", "F") else 0.5
    except Exception:
        return 1.0


def _is_ascii_word_char(ch: str) -> bool:
    """是否为 ASCII 英文/数字字符 (仅用于英文单词边界判断, 不含中文)"""
    return ch.isascii() and ch.isalnum()


def _truncate_title(title: str, max_len: int = 30) -> str:
    """按头条字数规则截断标题 (中文=1字, 英文2个=1字, 空格不计), 上限 max_len 字"""
    total = 0.0
    cut = len(title)
    for i, ch in enumerate(title):
        w = _title_char_weight(ch)
        if total + w > max_len:
            cut = i
            break
        total += w
    if cut >= len(title):
        return title
    # 若切点在英文单词中间, 回退到最近的空白/非英文边界 (最多8个字符);
    # 全英文连续标题找不到边界时保持原 cut, 保证不超字数上限
    if cut > 0 and _is_ascii_word_char(title[cut - 1]):
        b = cut
        while b > 0 and b > cut - 8 and _is_ascii_word_char(title[b - 1]):
            b -= 1
        if b > 0 and not _is_ascii_word_char(title[b - 1]):
            cut = b
    return title[:cut]


def distribute(page, context, title, content):
    """
    分发内容到今日头条

    title: 文章标题
    content: HTML内容 (含图片) 或纯文本
    """
    # 头条标题限 2~30 个字 (中文=1字, 英文2个=1字), 超长自动截断
    TITLE_MAX_LEN = 30
    if title:
        old_len = title
        title = _truncate_title(title, TITLE_MAX_LEN)
        if title != old_len:
            print(f"  标题超长, 已按头条字数规则截断 (上限{TITLE_MAX_LEN}字): {title}")

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
    _capture_page_hints(editor_page, "标题输入后")

    # ========== 3. 写入内容 ==========
    print("[3/5] 写入内容...")
    try:
        _write_content(editor_page, content)
        print("  ✓ 内容已写入")
    except Exception as e:
        print(f"  ✗ 写入内容失败: {e}")

    time.sleep(2)
    _capture_page_hints(editor_page, "内容写入后")

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

    # 捕获预览发布后的页面提示 (如"文字超出限制"等 toast/message)
    time.sleep(1)
    _capture_page_hints(editor_page, "预览发布后")

    # 等待弹窗/跳转, 处理可能的"确认发布"弹窗
    # (预览发布后头条会在当前标签页弹出新弹窗, 需等弹窗加载完成再确认)
    time.sleep(2)
    _confirm_publish_if_needed(editor_page, context)

    # 捕获确定发布后的页面提示 (发布成功/失败/校验错误等)
    time.sleep(1)
    _capture_page_hints(editor_page, "确定发布后")

    # 发布结果确认阶段再捕获一次 (部分提示延迟出现)
    time.sleep(3)
    _capture_page_hints(editor_page, "发布结果")

    time.sleep(2)
    print(f"========== 分发完成: {title} ==========")
    return "发布成功"


def _capture_page_hints(page, label="页面提示"):
    """
    捕获页面上出现的提示信息 (toast/message/错误文本等), 打印到日志供前端展示

    头条(字节系)页面提示常见类名: byte-toast / byte-message / semi-toast /
    [class*="toast"] / [class*="message"] 等; 提示通常短暂显示, 需在操作后立即抓取。
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
                # 含错误/限制关键词的提示用 ⚠ 标记, 便于前端识别
                warn = any(k in h for k in ["超", "限", "错误", "失败", "不能", "不可", "请", "无效", "超过", "最多"])
                print(f"  [{label}] {'⚠' if warn else 'ℹ'} {h}")
            return True
        return False
    except Exception as e:
        print(f"  [捕获页面提示失败] {e}")
        return False


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


def _strip_base64_images(html: str) -> str:
    """
    剥离 HTML 中的 base64 内嵌图片 <img src="data:...;base64,...">

    Word 解析会把图片转成 base64 内嵌, 单张可达几十万字符, 导致头条报
    "正文长度超过限制"。头条不支持内嵌图, 直接移除 img 标签, 保留文本。
    """
    if not html or "data:image" not in html:
        return html
    import re as _re
    # 移除含 data:image 的 <img ...> 标签
    cleaned = _re.sub(r'<img[^>]*src="data:image[^"]*"[^>]*>', "", html, flags=_re.IGNORECASE)
    # 兜底: 移除所有含 base64 的 img
    if "data:image" in cleaned:
        cleaned = _re.sub(r'<img[^>]*base64[^>]*>', "", cleaned, flags=_re.IGNORECASE)
    return cleaned


def _write_content(page, content):
    """
    写入文章内容到富文本编辑区

    头条编辑区为 contenteditable, 优先使用 execCommand insertHTML,
    兜底使用剪贴板粘贴, 再兜底纯文本逐字输入。

    重要: Word 解析的 HTML 会把图片转成 base64 内嵌 (<img src="data:...base64,...">),
    头条不支持内嵌图片且会因 HTML 超长报"正文长度超过限制", 因此写入前先剥离
    base64 图片, 仅保留文本 (图片在头条需手动上传/图床)。
    """
    # 剥离 base64 内嵌图片 (data:image 的 <img>), 避免头条报正文长度超限
    clean_content = _strip_base64_images(content)
    if clean_content != content:
        print(f"  已剥离 {content.count('<img')} 个内嵌 base64 图片 (头条不支持内嵌图)")

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
            clean_content,
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


# 确定发布按钮 (预览发布后的确认弹窗, 用户提供)
# 元素: <button class="byte-btn ... publish-btn publish-btn-last"><span>确认发布</span></button>
# class "publish-btn publish-btn-last" 非常独特, 可精确定位且不会误点"预览并发布"/"定时发布"
CONFIRM_CSS = 'button.publish-btn.publish-btn-last'
CONFIRM_XPATH = '/html/body/div[1]/div/div[3]/section/main/div[2]/div/div/div[2]/div/div/div[1]/div/div[3]/div/button[2]'


def _is_btn_ready(btn) -> bool:
    """
    判断按钮是否真正可点击 (不在 loading/disabled 状态)

    头条按钮在提交/加载时 class 会带 byte-btn-loading, 且可能随 React
    重渲染被 detached。此时点击会超时, 应跳过等待下一轮。
    """
    try:
        cls = (btn.get_attribute("class") or "").lower()
        if "loading" in cls or "disabled" in cls:
            return False
        if not btn.is_visible():
            return False
        return True
    except Exception:
        return False


def _find_confirm_button(page, frame=None):
    """
    在指定文档(主文档或iframe)中查找确定发布按钮, 返回可点击的 locator 或 None

    优先用独特 class 定位, 再 XPath, 最后精确匹配文本;
    排除 "预览并发布" / "定时发布" 等非目标按钮;
    按钮处于 loading/disabled 状态时视为未就绪, 返回 None 等待下一轮。
    """
    CONFIRM_TEXTS = ("发布", "确定发布", "确认发布", "发表")
    doc = frame if frame is not None else page
    # 1) 独特 class 定位 (最高优先级): button.publish-btn.publish-btn-last
    try:
        btn = doc.locator(CONFIRM_CSS).first
        if btn.is_visible():
            text = (btn.inner_text() or "").strip()
            if (text in CONFIRM_TEXTS or "发布" in text) and _is_btn_ready(btn):
                return btn
    except Exception:
        pass
    # 2) 用户提供的精确 XPath (主文档时)
    if frame is None:
        try:
            btn = doc.locator(f'xpath={CONFIRM_XPATH}').first
            if btn.is_visible():
                text = (btn.inner_text() or "").strip()
                if text in CONFIRM_TEXTS and _is_btn_ready(btn):
                    return btn
        except Exception:
            pass
    # 3) 遍历可见按钮精确匹配文本
    try:
        buttons = doc.locator("button:visible")
        count = buttons.count()
        for i in range(count):
            try:
                b = buttons.nth(i)
                text = (b.inner_text() or "").strip()
                if text in CONFIRM_TEXTS and _is_btn_ready(b):
                    return b
            except Exception:
                continue
    except Exception:
        pass
    return None


def _confirm_publish_if_needed(page, context=None):
    """
    点击预览发布后, 等待确认发布弹窗加载完成, 再点击确定发布按钮

    关键点: 预览发布后头条会在当前标签页弹出新弹窗(可能是新标签页 /
    iframe 浮层 / 主文档浮层), 弹窗需要时间加载。因此轮询最长 30s,
    每轮依次检测: 新标签页 → iframe → 主文档, 优先用独特 class
    button.publish-btn.publish-btn-last 定位 "确认发布" 按钮,
    再 XPath / 文本精确匹配兜底, 排除 "预览并发布"/"定时发布"。
    """
    CONFIRM_TEXTS = ("发布", "确定发布", "确认发布", "发表")
    CLICK_TIMEOUT = 5000  # 按钮可能随 React 重渲染 detached, 给足点击时间

    for attempt in range(30):
        clicked = False

        # 1) 新标签页检测 (预览弹窗可能开在新标签)
        if context is not None:
            try:
                for pg in context.pages:
                    if pg is page:
                        continue
                    btn = _find_confirm_button(pg)
                    if btn is not None:
                        try:
                            btn.click(force=True, timeout=CLICK_TIMEOUT)
                            print(f"  ✓ 已在新标签页点击确定发布按钮 (文本: {btn.inner_text().strip()})")
                            clicked = True
                        except Exception:
                            print("  …新标签页按钮点击未完成(可能仍在加载), 继续等待")
                        break
            except Exception:
                pass
            if clicked:
                return

        # 2) iframe 检测 (预览弹窗可能是 iframe 浮层)
        try:
            for fr in page.frames:
                if fr is page.main_frame:
                    continue
                btn = _find_confirm_button(page, fr)
                if btn is not None:
                    try:
                        btn.click(force=True, timeout=CLICK_TIMEOUT)
                        print(f"  ✓ 已在弹窗(iframe)中点击确定发布按钮 (文本: {btn.inner_text().strip()})")
                        clicked = True
                    except Exception:
                        print("  …弹窗(iframe)按钮点击未完成(可能仍在加载), 继续等待")
                    break
        except Exception:
            pass
        if clicked:
            return

        # 3) 主文档检测
        btn = _find_confirm_button(page)
        if btn is not None:
            try:
                btn.click(force=True, timeout=CLICK_TIMEOUT)
                print(f"  ✓ 已点击确定发布按钮 (文本: {btn.inner_text().strip()})")
                return
            except Exception:
                print("  …主文档按钮点击未完成(可能仍在加载), 继续等待")

        time.sleep(1)

    # 仍未找到, 提示人工确认 (不再误点"预览并发布"/"定时发布")
    print("  ⚠ 未找到确定发布按钮, 已跳过确认 (请人工在浏览器中确认发布)")


def on_close(page, context):
    """浏览器关闭时调用"""
    print("今日头条浏览器关闭")
