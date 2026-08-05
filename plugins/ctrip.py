# 携程 (ctrip) 自动化插件
#
# 两种发布方式:
#   1. 图文 (publishPictureText) - 本次实现:
#      前置: 本地携程根目录/图文/ 下每个文件夹 = 一个图文块 (图片 + word文档)
#      流程: 打开图文编辑页 -> 上传图片(≤20张) -> 输入标题 -> 输入内容
#            -> 从内容提取地址并选择 -> 点击发布
#   2. 视频 - 接口预留 (待补充 XPath 后实现)
#
# page: Playwright Page 对象
# context: Playwright BrowserContext 对象
#
# distribute 接收:
#   title: 文章标题 (手动分发时)
#   content: HTML内容 (手动分发时)
#   folder_path: 图文文件夹路径 (文件夹内图片 + word, 携程图文发布用)

import os
import re
import time
import glob
import logging

logger = logging.getLogger(__name__)

# ===================== 常量 =====================
PICTURE_TEXT_URL = "https://we.ctrip.com/publish/publishPictureText"
VIDEO_URL = "https://we.ctrip.com/publish/publishVideo"  # 视频发布页 (预留)

# 用户提供的精确 XPath
UPLOAD_XPATH = '//*[@id="root"]/section/section/main/div/div/div/div[1]/div[3]/div/div/span/div/span/div'
TITLE_XPATH = '//*[@id="root"]/section/section/main/div/div/div/div[1]/div[4]/div[2]/div/div[2]/div/div/div/div'
CONTENT_XPATH = '//*[@id="root"]/section/section/main/div/div/div/div[1]/div[5]/div[3]/div/div[2]/div'
ADDRESS_XPATH = '//*[@id="root"]/section/section/main/div/div/div/div[1]/div[9]/div/div'
PUBLISH_XPATH = '//*[@id="root"]/section/section/main/div/div/div/div[1]/div[14]/div/button[2]'

MAX_IMAGES = 20  # 图文最多 20 张图片


def on_open(page, context):
    """浏览器打开时调用, 导航到图文编辑页面"""
    print("导航到携程图文编辑页面...")
    try:
        page.goto(PICTURE_TEXT_URL, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        try:
            page.goto(PICTURE_TEXT_URL, timeout=30000)
        except Exception as e:
            print(f"打开编辑页失败: {e}")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(2)


def is_logged_in(page, context=None):
    """
    检查是否已登录携程 (we.ctrip.com)

    已登录: 页面能进入编辑器 (能找到上传区/标题输入框);
    未登录: 跳转到登录页 (passport.ctrip.com 或页面出现"登录"按钮)。
    """
    import time as _time

    current_url = (page.url or "").lower()

    # 明确登录页 → 未登录
    if "passport.ctrip.com" in current_url or "/login" in current_url or "accounts.ctrip" in current_url:
        print("检测到携程登录页, 未登录")
        return False

    # 未在 we.ctrip.com → 导航到图文编辑页再判断
    if "we.ctrip.com" not in current_url:
        try:
            page.goto(PICTURE_TEXT_URL, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            try:
                page.goto(PICTURE_TEXT_URL, timeout=20000)
            except Exception:
                return False
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        _time.sleep(2)
        current_url = (page.url or "").lower()
        if "passport.ctrip.com" in current_url or "/login" in current_url:
            print("重定向到登录页, 未登录")
            return False

    # 尝试定位上传区/标题输入框 → 找到即已登录 (编辑页特征)
    for attempt in range(3):
        try:
            # 标题输入框或上传区
            loc = page.locator(f'xpath={TITLE_XPATH}').first
            loc.wait_for(state="visible", timeout=8000)
            print("检测到携程图文编辑页, 已登录")
            return True
        except Exception:
            try:
                loc = page.locator(f'xpath={UPLOAD_XPATH}').first
                loc.wait_for(state="visible", timeout=5000)
                print("检测到携程图文上传区, 已登录")
                return True
            except Exception:
                if attempt < 2:
                    _time.sleep(2)
                    continue
    # 兜底: URL 在 we.ctrip.com 且非登录页
    if "we.ctrip.com" in current_url:
        print("URL 在携程平台, 视为已登录")
        return True
    return False


def login(page, context):
    """登录流程: 跳转携程登录页, 由用户完成扫码/账号登录, 登录态自动持久化"""
    print("跳转携程登录页, 请在浏览器中完成登录...")
    try:
        page.goto("https://passport.ctrip.com/user/login", wait_until="domcontentloaded", timeout=30000)
    except Exception:
        try:
            page.goto("https://accounts.ctrip.com/member/login", timeout=30000)
        except Exception as e:
            print(f"打开登录页失败: {e}")
            return
    try:
        page.wait_for_url("**/we.ctrip.com/**", timeout=300000)
        print("登录成功! 已进入携程")
    except Exception:
        print("登录超时, 请检查浏览器窗口或重试")


def distribute(page, context, title=None, content=None, folder_path=None):
    """
    分发内容到携程

    图文方式: folder_path 指向图文文件夹 (含图片 + word文档),
    优先使用 folder_path; 手动分发时使用 title/content。
    """
    if not folder_path:
        # 手动分发模式: 只有标题+内容 (无图片)
        print("注意: 未提供图文文件夹, 使用手动标题/内容分发 (无图片)")
        return _distribute_picture_text(page, context, title, content, image_paths=[])

    # 读取文件夹: 图片 + word
    import doc_parser
    folder = str(folder_path)
    print(f"========== 开始分发到携程 (图文) ==========")
    print(f"文件夹: {folder}")

    # 收集图片
    image_paths = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp", "*.bmp"):
        image_paths.extend(glob.glob(os.path.join(folder, ext)))
    image_paths.sort()
    print(f"  图片数量: {len(image_paths)} 张 (上限 {MAX_IMAGES} 张)")

    # 读取 word 文档
    word_files = glob.glob(os.path.join(folder, "*.docx")) + glob.glob(os.path.join(folder, "*.doc"))
    if not word_files:
        raise Exception(f"文件夹中未找到 Word 文档: {folder}")
    word_file = word_files[0]
    print(f"  Word 文档: {os.path.basename(word_file)}")

    parsed = doc_parser.parse_docx(word_file)
    f_title = parsed.get("title", "")
    f_content = parsed.get("html_content", "")
    print(f"  标题: {f_title}")
    print(f"  内容长度: {len(f_content)} 字符")

    return _distribute_picture_text(page, context, f_title, f_content, image_paths)


def _distribute_picture_text(page, context, title, content, image_paths):
    """携程图文发布流程"""
    if not title:
        raise Exception("标题为空, 无法发布")

    # ========== 1. 确保在图文编辑页 ==========
    print("[1/6] 打开/确认图文编辑页...")
    editor_page = page
    current_url = (page.url or "").lower()
    if "publishPictureText" not in current_url:
        try:
            editor_page.goto(PICTURE_TEXT_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            try:
                editor_page.goto(PICTURE_TEXT_URL, timeout=30000)
            except Exception as e:
                raise Exception(f"无法打开图文编辑页: {e}")
        try:
            editor_page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(3)
    try:
        editor_page.locator(f'xpath={UPLOAD_XPATH}').wait_for(state="visible", timeout=20000)
        print("  ✓ 已进入图文编辑页")
    except Exception:
        raise Exception("未找到上传区, 可能未登录或页面结构变化")

    # ========== 2. 上传图片 ==========
    print("[2/6] 上传图片...")
    if image_paths:
        upload_images = image_paths[:MAX_IMAGES]
        if len(image_paths) > MAX_IMAGES:
            print(f"  ⚠ 图片超过 {MAX_IMAGES} 张, 仅上传前 {MAX_IMAGES} 张")
        _upload_images(editor_page, upload_images)
        print(f"  ✓ 已上传 {len(upload_images)} 张图片")
    else:
        print("  无图片, 跳过上传步骤")

    time.sleep(2)

    # ========== 3. 输入标题 ==========
    print("[3/6] 输入标题...")
    title_entered = False
    title_locators = [
        (f'xpath={TITLE_XPATH}', TITLE_XPATH),
        ('textarea[placeholder*="标题"], input[placeholder*="标题"], [contenteditable="true"][data-placeholder*="标题"]', None),
        # 兜底: 排除正文/内容占位符的 contenteditable, 避免选中内容框
        ('#root [contenteditable="true"]:not([data-placeholder*="正文"]):not([data-placeholder*="内容"]):not([data-placeholder*="写"])', None),
    ]
    for selector, _d in title_locators:
        try:
            loc = editor_page.locator(selector).first
            loc.wait_for(state="visible", timeout=5000)
            loc.click(force=True, timeout=5000)
            time.sleep(0.3)
            loc.fill("")
            loc.type(title, delay=30)
            print(f"  ✓ 已输入标题: {title[:50]}{'...' if len(title) > 50 else ''}")
            title_entered = True
            break
        except Exception as e:
            print(f"  ✗ 定位失败({selector[:40]}): {e}")
            continue

    if not title_entered:
        try:
            editor_page.evaluate(
                """(args) => {
                    const title = args.title;
                    let el = null;
                    try {
                        el = document.evaluate(args.xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    } catch (e) {}
                    if (!el) {
                        el = document.querySelector('#root [contenteditable="true"][data-placeholder*="标题"], #root [contenteditable="true"]:not([data-placeholder*="正文"]):not([data-placeholder*="内容"])');
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
        raise Exception("输入标题失败: 无法定位标题输入框")

    time.sleep(1)

    # ========== 4. 输入内容 ==========
    print("[4/6] 输入内容...")
    try:
        _write_content(editor_page, content)
        print("  ✓ 内容已写入")
    except Exception as e:
        print(f"  ✗ 写入内容失败: {e}")

    time.sleep(2)

    # ========== 5. 提取地址并输入 ==========
    print("[5/6] 处理地址...")
    address = _extract_address(content)
    if address:
        print(f"  从内容提取到地址: {address}")
        try:
            _input_address(editor_page, address)
            print("  ✓ 地址已输入并选择")
        except Exception as e:
            print(f"  ✗ 地址处理失败: {e}")
    else:
        print("  内容中无地址, 跳过")

    time.sleep(1)

    # ========== 6. 点击发布 ==========
    print("[6/6] 点击发布...")
    publish_clicked = False
    try:
        publish_btn = editor_page.locator(f'xpath={PUBLISH_XPATH}')
        publish_btn.wait_for(state="visible", timeout=10000)
        publish_btn.click(force=True, timeout=5000)
        print("  已点击发布按钮")
        publish_clicked = True
    except Exception as e:
        print(f"  ✗ 点击发布失败: {e}")
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

    time.sleep(5)
    print(f"========== 分发完成: {title[:50]} ==========")
    return "发布成功"


def _upload_images(page, image_paths):
    """通过文件选择器上传图片, 上传完成后关闭文件对话框"""
    try:
        # 点击上传按钮打开文件对话框
        upload_btn = page.locator(f'xpath={UPLOAD_XPATH}')
        upload_btn.wait_for(state="visible", timeout=10000)
        upload_btn.click(force=True, timeout=5000)
        time.sleep(1)

        # 使用 Playwright 的 file chooser 处理文件选择
        from playwright.sync_api import sync_playwright
        try:
            with page.expect_file_chooser(timeout=10000) as fc_info:
                upload_btn.click(force=True, timeout=5000)
            file_chooser = fc_info.value
            file_chooser.set_files(image_paths)
            print(f"  ✓ 已选择 {len(image_paths)} 张图片")
        except Exception:
            # 兜底: 直接用 input[type=file] 设置文件
            try:
                file_input = page.locator('input[type="file"]').first
                file_input.set_input_files(image_paths)
                print(f"  ✓ 已通过 input[type=file] 上传 {len(image_paths)} 张图片")
            except Exception as e2:
                raise Exception(f"图片上传失败: {e2}")

        # 等待上传完成, 然后关闭文件对话框/取消选择状态
        time.sleep(3)
        try:
            # 按 Esc 关闭可能残留的文件对话框/取消焦点
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass
        # 若页面上还有"确认/完成/关闭"类的上传确认弹窗, 尝试关闭
        try:
            for text in ["确认", "完成", "确定", "关闭", "取消", "Done"]:
                btn = page.locator(f'button:has-text("{text}")').last
                if btn.is_visible():
                    btn.click(force=True, timeout=2000)
                    print(f"  已关闭上传确认弹窗[{text}]")
                    break
        except Exception:
            pass
    except Exception as e:
        raise Exception(f"上传图片失败: {e}")


def _write_content(page, content):
    """
    写入内容到富文本编辑区

    重要: 标题框和内容框都是 contenteditable, 必须用用户提供的 CONTENT_XPATH
    精确区分 (标题在 div[4], 内容在 div[5]), 绝不能 fallback 到通用
    [contenteditable="true"] (会选到标题框导致标题内容写到一块)。
    """
    # 定位内容编辑区: 只认用户提供的 CONTENT_XPATH, 兜底也排除标题区
    content_el = None
    for selector in [
        f'xpath={CONTENT_XPATH}',
        '#root [contenteditable="true"][data-placeholder*="正文"], #root [contenteditable="true"][data-placeholder*="内容"], #root [contenteditable="true"][data-placeholder*="写"]',
        '#root [contenteditable="true"]:not([data-placeholder*="标题"])',
        '.ProseMirror',
        '.ql-editor',
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

    try:
        content_el.click(force=True, timeout=5000)
        time.sleep(0.5)
    except Exception:
        pass

    # 方式1: execCommand insertHTML (按 XPath 精确定位内容区)
    try:
        page.evaluate(
            """(args) => {
                const html = args.html, xpath = args.xpath;
                // 优先按用户 XPath 定位内容区
                let el = null;
                try {
                    el = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                } catch (e) {}
                if (!el) {
                    // 兜底: 非标题的 contenteditable
                    el = document.querySelector('#root [contenteditable="true"][data-placeholder*="正文"], #root [contenteditable="true"][data-placeholder*="内容"], #root [contenteditable="true"]:not([data-placeholder*="标题"])');
                }
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
            {"html": content, "xpath": CONTENT_XPATH},
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
    """获取内容编辑区的文本 (按 CONTENT_XPATH 精确读取, 不读标题框)"""
    try:
        return page.evaluate(
            """(xpath) => {
                let el = null;
                try {
                    el = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                } catch (e) {}
                if (!el) {
                    el = document.querySelector('#root [contenteditable="true"][data-placeholder*="正文"], #root [contenteditable="true"][data-placeholder*="内容"], #root [contenteditable="true"]:not([data-placeholder*="标题"])');
                }
                return el ? el.innerText : '';
            }""",
            CONTENT_XPATH,
        )
    except Exception:
        return ""


def _extract_address(content):
    """
    从内容中提取地址

    优先匹配常见地址格式:
    - "地址: XXX" / "地点: XXX" / "位置: XXX"
    - 含省/市/区/路/街等关键词的句子
    返回提取的地址字符串, 无则返回 None。
    """
    if not content:
        return None
    # 去 HTML 标签
    text = re.sub(r"<[^>]+>", "", content)
    text = re.sub(r"\s+", " ", text).strip()

    # 1) 显式标签: 地址/地点/位置
    for pattern in [
        r"(?:地址|地点|位置|位于)[:：]\s*([^。；;，,\n]+)",
        r"(?:地址|地点|位置|位于)\s+([^。；;，,\n]+)",
    ]:
        m = re.search(pattern, text)
        if m and m.group(1).strip():
            return m.group(1).strip()

    # 2) 含省市区路街的句子
    addr_kw = re.compile(
        r"[\u4e00-\u9fa5]{2,8}(?:省|市|区|县)[\u4e00-\u9fa5]{0,8}(?:路|街|道|巷|号|大厦|广场|中心|公园|酒店|商场|园)[\u4e00-\u9fa5]{0,15}"
    )
    m = addr_kw.search(text)
    if m:
        return m.group(0).strip()

    return None


def _input_address(page, address):
    """输入地址并在下拉列表中选择最接近的地址"""
    try:
        addr_box = page.locator(f'xpath={ADDRESS_XPATH}')
        addr_box.wait_for(state="visible", timeout=10000)
        addr_box.click(force=True, timeout=5000)
        time.sleep(0.5)
        addr_box.fill("")
        addr_box.type(address, delay=50)
        print(f"  已输入地址: {address}")
    except Exception as e:
        print(f"  ✗ 地址输入框定位失败: {e}")
        # 兜底
        try:
            loc = page.locator('input[placeholder*="地址"], input[placeholder*="位置"], [contenteditable="true"][data-placeholder*="地址"]').first
            loc.click(force=True, timeout=3000)
            loc.fill("")
            loc.type(address, delay=50)
            print("  已通过兜底选择器输入地址")
        except Exception as e2:
            raise Exception(f"地址输入失败: {e2}")

    # 等待下拉列表出现, 选择第一个选项 (最接近的地址)
    time.sleep(2)
    selected = False
    for attempt in range(10):
        try:
            # 常见下拉选项选择器
            selectors = [
                '[class*="option"]:visible',
                '[class*="dropdown"] [class*="item"]:visible',
                '[class*="search"] [class*="result"]:visible',
                '[class*="list"] li:visible',
                'ul[class*="dropdown"] li:visible',
            ]
            for sel in selectors:
                try:
                    options = page.locator(sel)
                    count = options.count()
                    if count > 0:
                        options.first.click(force=True, timeout=3000)
                        print(f"  ✓ 已选择下拉地址选项 (共{count}个, 取第一个)")
                        selected = True
                        break
                except Exception:
                    continue
            if selected:
                break
        except Exception:
            pass
        time.sleep(1)

    if not selected:
        print("  ⚠ 未找到地址下拉选项, 可能地址未匹配 (请人工确认)")


# ========== 视频发布 (预留) ==========

def distribute_video(page, context, video_path=None, title=None, content=None):
    """
    视频分发 - 接口预留

    待补充: 携程视频发布页 XPath 与上传流程
    """
    print("携程视频分发功能开发中 (接口已预留)")
    raise NotImplementedError("视频分发尚未实现, 请等待后续版本")


def on_close(page, context):
    """浏览器关闭时调用"""
    print("携程浏览器关闭")
