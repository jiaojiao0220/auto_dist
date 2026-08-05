# 原创力文档 (book118) 自动化插件
#
# 与 CSDN 等内容分发平台不同，book118 是文件上传型平台：
#   - distribute 接收 file_path 参数 (原始 .docx 文件路径)
#   - 通过文件选择器上传文件，而非粘贴内容
#   - 上传后文件移动到已发布目录
#
# page: Playwright Page 对象
# context: Playwright BrowserContext 对象
# title: 文档标题 (从 Word 第一段解析)
# content: HTML内容 (从 Word 解析, book118 不使用此参数)
# file_path: 原始文件路径 (book118 上传用)

import os
import time
import shutil
import logging

logger = logging.getLogger(__name__)

# ===================== 路径配置 =====================
ROOT_DIR = r"E:\Program\data\原创力"
PENDING_DIR = os.path.join(ROOT_DIR, "预发布文档")
PUBLISHED_DIR = os.path.join(ROOT_DIR, "已发布文档")

# 确保目录存在
os.makedirs(PENDING_DIR, exist_ok=True)
os.makedirs(PUBLISHED_DIR, exist_ok=True)


def on_open(page, context):
    """浏览器打开时调用，导航到上传页面"""
    print("导航到原创力上传页面...")
    page.goto("https://max.book118.com/user_center_v1/doc/Index/index.html#upload")
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    time.sleep(2)
    pass


def is_logged_in(page, context=None):
    """
    检查是否已登录原创力
    通过检测页面上是否有"登录"按钮来判断
    """
    import time as _time

    # 确保在 book118 页面上
    current_url = page.url or ""
    if "book118.com" not in current_url:
        pass
        try:
            page.goto("https://max.book118.com/", wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass

    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        pass

    # 最多重试 3 次
    for attempt in range(3):
        try:
            # 方法1: 检查是否有登录按钮 (未登录时显示)
            login_btn_xpath = 'xpath=//*[@id="main"]/div/div[2]/div[1]/dl[1]/dd[2]/span[2]/a[1]'
            try:
                login_btn = page.wait_for_selector(login_btn_xpath, timeout=5000)
                if login_btn:
                    pass
                    return False
            except Exception:
                # 没有找到登录按钮，可能是已登录
                pass

            # 方法2: 检查是否有用户头像/用户名等已登录标识
            try:
                # 已登录用户通常有用户中心入口
                user_elements = page.query_selector_all('.user-name, .username, .user-info, .header-user')
                if user_elements:
                    for el in user_elements:
                        if el.is_visible():
                            pass
                            return True
            except Exception:
                pass

            # 方法3: 检查 cookies
            try:
                cookies = context.cookies() if context else page.context.cookies()
                has_session = any(
                    c.get("name") in ("PHPSESSID", "user_id", "userid", "username", "uc_uid")
                    and c.get("value", "")
                    for c in cookies
                    if "book118.com" in c.get("domain", "")
                )
                if has_session:
                    pass
                    return True
            except Exception:
                pass

            # 方法4: 检查上传按钮是否可用 (已登录才能看到上传功能)
            try:
                upload_btn = page.query_selector('#btn_upload')
                if upload_btn and upload_btn.is_visible():
                    pass
                    return True
            except Exception:
                pass

            if attempt < 2:
                pass
                _time.sleep(2)
                continue

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
    """自动登录流程 - 导航到登录页面，用户手动完成登录"""
    print("导航到登录页面，请在浏览器中完成登录...")
    try:
        page.goto("https://max.book118.com/", wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)

        # 尝试点击登录按钮
        login_btn_xpath = 'xpath=//*[@id="main"]/div/div[2]/div[1]/dl[1]/dd[2]/span[2]/a[1]'
        try:
            login_btn = page.wait_for_selector(login_btn_xpath, timeout=5000)
            if login_btn:
                login_btn.click()
                print("已点击登录按钮，请在弹出的登录页面完成登录")
        except Exception:
            print("未找到登录按钮，可能已登录或页面结构变化")

    except Exception as e:
        print(f"导航到登录页面失败: {e}")

    # 等待用户完成登录 (最多5分钟)
    try:
        page.wait_for_url("**/user_center**", timeout=300000)
        print("登录成功!")
    except Exception:
        print("登录超时或未检测到跳转，请确认登录状态")


def distribute(page, context, title, content, file_path=None):
    """
    上传文件到原创力文档平台

    page: Playwright Page 对象
    context: Playwright BrowserContext 对象
    title: 文档标题 (book118 不单独设置标题，使用文件名)
    content: HTML内容 (book118 不使用此参数)
    file_path: 原始 .docx 文件路径 (必须)
    """
    print(f"========== 开始上传到原创力 ==========")
    pass
    pass

    if not file_path:
        raise Exception("原创力平台需要 file_path 参数 (原始文件路径)")

    if not os.path.exists(file_path):
        raise Exception(f"文件不存在: {file_path}")

    file_name = os.path.basename(file_path)
    pass

    # ========== 1. 确保在上传页面 ==========
    print("[1/5] 确认上传页面...")
    current_url = page.url or ""
    if "book118.com" not in current_url or "upload" not in current_url.lower():
        pass
        page.goto("https://max.book118.com/user_center_v1/doc/Index/index.html#upload")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        time.sleep(2)

    pass

    # ========== 2. 点击上传按钮 ==========
    print("[2/5] 点击上传按钮...")
    upload_btn_xpath = 'xpath=//*[@id="btn_upload"]/span'
    try:
        upload_btn = page.wait_for_selector(upload_btn_xpath, timeout=10000)
        upload_btn.click()
        pass
        time.sleep(3)
    except Exception as e:
        pass
        # 尝试备用选择器
        try:
            upload_btn = page.locator('#btn_upload')
            upload_btn.click()
            pass
            time.sleep(3)
        except Exception as e2:
            raise Exception(f"无法找到上传按钮: {e} / {e2}")

    # ========== 3. 获取上传 iframe 并上传文件 ==========
    print("[3/5] 上传文件...")
    frame = _get_upload_frame(page)
    if not frame:
        raise Exception("无法获取上传iframe")

    # 勾选用户协议
    _check_and_click_checkbox(frame)
    time.sleep(1)

    upload_triggered = False

    # 方案1: 通过文件选择器上传
    try:
        with page.expect_file_chooser(timeout=15000) as fc_info:
            frame.locator(".webuploader-pick").first.click(timeout=10000)
        fc = fc_info.value
        fc.set_files(file_path)
        upload_triggered = True
        pass
    except Exception as e:
        pass

    # 方案2: 直接给 input 赋值
    if not upload_triggered:
        try:
            file_input = frame.wait_for_selector('#upload_picker input[type="file"]', timeout=8000)
            file_input.set_input_files(file_path)
            upload_triggered = True
            pass
        except Exception as e:
            pass

    if not upload_triggered:
        raise Exception("两种上传方式均无法传入文件")

    # ========== 4. 等待上传完成 ==========
    print("[4/5] 等待上传完成...")
    upload_ok = _wait_for_upload_complete(frame, page, max_wait=120)
    if upload_ok:
        print("  ✓ 文件上传完成")
    else:
        print("  ⚠ 上传等待超时，尝试继续...")

    # 寻找确认上传按钮
    try:
        submit_selectors = ['text="确认上传"', 'text="提交"', '.btn-submit']
        for sel in submit_selectors:
            try:
                btn = frame.wait_for_selector(sel, timeout=3000)
                if btn and btn.is_visible():
                    btn.click()
                    pass
                    time.sleep(3)
                    _wait_for_upload_complete(frame, page, 60)
                    break
            except Exception:
                continue
    except Exception:
        pass

    time.sleep(2)

    # ========== 5. 移动文件到已发布目录 ==========
    print("[5/5] 移动文件到已发布目录...")
    moved = _move_to_published(file_path)
    if moved:
        print(f"  ✓ 文件已移动到已发布目录: {PUBLISHED_DIR}")
    else:
        print(f"  ⚠ 文件移动失败，文件保留在: {file_path}")

    print(f"========== 上传完成: {file_name} ==========")
    return "上传成功"


# ===================== 辅助函数 =====================

def _get_upload_frame(page):
    """获取上传iframe"""
    for _ in range(20):
        frame = next((f for f in page.frames if f.name == "doc_index_iframe"), None)
        if frame:
            return frame
        page.wait_for_timeout(500)
    pass
    return None


def _check_and_click_checkbox(frame):
    """勾选用户协议"""
    checkbox_selectors = ['input[name="agreement"]', 'input[type="checkbox"]']
    checkbox = None
    for sel in checkbox_selectors:
        try:
            checkbox = frame.wait_for_selector(sel, timeout=5000)
            if checkbox:
                break
        except Exception:
            continue
    if not checkbox:
        pass
        return True
    try:
        if checkbox.is_checked():
            pass
            return True
    except Exception:
        pass
    pass
    try:
        frame.evaluate("""()=>{
            let cb=document.querySelector('input[name="agreement"]');
            if(cb){cb.checked=true;cb.dispatchEvent(new Event('change',{bubbles:true}));}
        }""")
        frame.wait_for_timeout(1000)
    except Exception as e:
        pass
    return True


def _wait_for_upload_complete(frame, page, max_wait):
    """等待上传处理完成"""
    pass
    for _ in range(max_wait):
        page.wait_for_timeout(1000)
        try:
            stats = frame.evaluate(r"""()=>{
                let res={};
                let tabs=document.querySelectorAll('.tab-item,.nav-tabs li');
                for(let t of tabs){
                    let txt=t.innerText.trim();
                    if(txt.includes('待上传')||txt.includes('上传成功')) res[txt]=1;
                }
                let pros=document.querySelectorAll('[style*="width"]');
                let per=[];
                for(let p of pros){
                    let m=p.style.width.match(/(\d+)%/);
                    if(m) per.push(parseInt(m[1]))
                }
                res._per=per;
                return res;
            }""")
            per_list = stats.get("_per", [])
            if per_list and all(x >= 100 for x in per_list):
                pass
                return True
        except Exception:
            continue
    pass
    return False


def _move_to_published(file_path):
    """上传成功后移动文件至已发布目录，重名自动加时间戳"""
    file_name = os.path.basename(file_path)
    dest_path = os.path.join(PUBLISHED_DIR, file_name)
    if os.path.exists(dest_path):
        name, ext = os.path.splitext(file_name)
        ts = time.strftime("%Y%m%d_%H%M%S")
        dest_path = os.path.join(PUBLISHED_DIR, f"{name}_{ts}{ext}")
    try:
        shutil.move(file_path, dest_path)
        return True
    except Exception as e:
        pass
        return False


def on_close(page, context):
    """浏览器关闭时调用"""
    print("原创力浏览器关闭")
