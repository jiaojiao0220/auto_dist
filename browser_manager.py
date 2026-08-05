"""浏览器管理器 - Playwright 持久化上下文, 自动保存登录态"""
import threading
import queue
import time
import inspect
import traceback
import logging
import io
import sys
import json
from collections import deque
from pathlib import Path
from typing import Dict, Callable, Optional, Any, List

logger = logging.getLogger(__name__)


class LogCollector:
    """收集插件执行时的 print 输出, 供前端实时查看"""

    def __init__(self, max_lines: int = 500):
        self._logs: deque = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self._capturing = False
        self._old_stdout = None

    def add(self, msg: str, level: str = "info") -> None:
        """手动添加一条日志"""
        ts = time.strftime("%H:%M:%S")
        with self._lock:
            self._logs.append({"time": ts, "level": level, "msg": msg})

    def start_capture(self) -> None:
        """开始捕获 stdout (print 输出), 实时逐行收集"""
        if self._capturing:
            return
        self._capturing = True
        self._old_stdout = sys.stdout
        sys.stdout = _TeeStream(self._old_stdout, self)

    def stop_capture(self) -> None:
        """停止捕获, flush 残留内容"""
        if not self._capturing:
            return
        stream = sys.stdout
        sys.stdout = self._old_stdout
        self._capturing = False
        # flush 残留的不完整行
        if hasattr(stream, "flush"):
            try:
                stream.flush()
            except Exception:
                pass

    def get_logs(self, after: int = 0) -> List[dict]:
        """获取日志, after 指定从第几条开始 (增量切片: after=0 返回全部, after>=len 返回空)"""
        with self._lock:
            all_logs = list(self._logs)
        # 始终按 after 切片，避免 offset 追上 len 时反而返回全部，导致前端重复渲染同批日志
        if after < 0:
            after = 0
        return all_logs[after:]

    def clear(self) -> None:
        with self._lock:
            self._logs.clear()


class _TeeStream(io.TextIOBase):
    """同时写入原始 stdout 并实时逐行收集日志 (不攒批)"""

    def __init__(self, original_stdout, log_collector):
        self._original = original_stdout
        self._collector = log_collector
        self._line_buf = ""

    def write(self, s):
        # 原始 stdout 照常输出
        try:
            self._original.write(s)
        except Exception:
            pass
        # 逐行收集 — 遇到换行就立即写入日志
        self._line_buf += s
        while "\n" in self._line_buf:
            line, self._line_buf = self._line_buf.split("\n", 1)
            if line.strip():
                self._collector.add(line.rstrip("\r"), "info")
        return len(s)

    def flush(self):
        try:
            self._original.flush()
        except Exception:
            pass
        # flush 时把残留的不完整行也输出
        if self._line_buf.strip():
            self._collector.add(self._line_buf.rstrip("\r"), "info")
            self._line_buf = ""


def call_plugin_func(func: Callable, page=None, context=None, **extra) -> Any:
    """
    根据函数签名智能传参.
    不同插件函数可能接受不同参数: (page), (page, context), (page, content), (page, context, content)
    此函数只传递函数实际声明的参数.
    """
    sig = inspect.signature(func)
    params = sig.parameters

    kwargs = {}
    if "page" in params:
        kwargs["page"] = page
    if "context" in params:
        kwargs["context"] = context
    for key, value in extra.items():
        if key in params:
            kwargs[key] = value

    for param in params.values():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            for key, value in extra.items():
                if key not in kwargs:
                    kwargs[key] = value
            break

    return func(**kwargs)


class BrowserInstance:
    """单个平台的浏览器实例, 运行在独立线程中"""

    def __init__(
        self,
        platform_id: str,
        user_data_dir: Path,
        url: str,
        plugin_functions: Dict[str, Callable],
        headless: bool = False,
    ):
        self.platform_id = platform_id
        self.user_data_dir = str(user_data_dir)
        self.url = url
        self.plugin = plugin_functions
        self.headless = headless
        self.command_queue: queue.Queue = queue.Queue()
        self.result_queue: queue.Queue = queue.Queue()
        self.thread: Optional[threading.Thread] = None
        self.running = False
        self.error: Optional[str] = None
        self.auth_status: Optional[bool] = None
        self.auth_expiry: Optional[float] = None  # 授权过期时间 (Unix 秒), 取最早过期的持久 cookie
        self.logs = LogCollector()
        self._ready = threading.Event()  # 初始 on_open + is_logged_in 完成后置位

    def start(self) -> None:
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"browser-{self.platform_id}")
        self.thread.start()

    def _run(self) -> None:
        """浏览器线程主循环"""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    self.user_data_dir,
                    headless=self.headless,
                    viewport={"width": 1280, "height": 800},
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                )

                # 授予剪贴板权限
                try:
                    context.grant_permissions(["clipboard-read", "clipboard-write"])
                except Exception:
                    pass

                page = context.pages[0] if context.pages else context.new_page()

                # 监听新标签页打开
                def on_new_page(new_page):
                    self.logs.add(f"检测到新标签页打开: {new_page.url}", "info")

                context.on("page", on_new_page)

                # 执行 on_open
                if self.plugin.get("on_open"):
                    self.logs.add("执行 on_open...", "info")
                    self.logs.start_capture()
                    try:
                        call_plugin_func(self.plugin["on_open"], page, context)
                    except Exception:
                        self.error = f"on_open 执行出错:\n{traceback.format_exc()}"
                        self.logs.add(f"on_open 出错: {self.error}", "error")
                        try:
                            page.goto(self.url)
                        except Exception:
                            pass
                    finally:
                        self.logs.stop_capture()
                else:
                    try:
                        page.goto(self.url)
                    except Exception:
                        pass

                # 检查登录状态
                if self.plugin.get("is_logged_in"):
                    self.logs.add("检查登录状态...", "info")
                    self.logs.start_capture()
                    try:
                        self.auth_status = bool(call_plugin_func(self.plugin["is_logged_in"], page, context))
                        self.logs.stop_capture()
                        self.logs.add(f"登录状态: {self.auth_status}", "info")
                    except Exception:
                        self.logs.stop_capture()
                        self.auth_status = None
                        self.logs.add("登录状态检查失败", "warning")

                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                if self.plugin.get("is_logged_in"):
                    try:
                        self.auth_status = bool(call_plugin_func(self.plugin["is_logged_in"], page, context))
                    except Exception:
                        pass

                # 读取授权 cookie 过期时间
                # 策略: 取持久 cookie 中最晚过期的时间作为授权失效点
                # (最早过期的往往是短期临时 cookie, 不代表登录态失效; 最晚的才是登录态有效期)
                try:
                    cookies = context.cookies()
                    expires_list = [
                        float(c.get("expires", -1))
                        for c in cookies
                        if c.get("expires", -1) and float(c.get("expires", -1)) > 0
                    ]
                    if expires_list:
                        self.auth_expiry = max(expires_list)
                    else:
                        self.auth_expiry = None
                except Exception:
                    self.auth_expiry = None

                # 初始 on_open + is_logged_in 完成，标记就绪
                self._ready.set()

                # 命令处理循环
                while self.running:
                    try:
                        cmd = self.command_queue.get(timeout=0.5)
                    except queue.Empty:
                        if context.pages == []:
                            self.logs.add("浏览器被手动关闭", "warning")
                            break
                        continue

                    if cmd["action"] == "close":
                        self.logs.add("收到关闭命令", "info")
                        break
                    elif cmd["action"] == "run":
                        func_name = cmd["func_name"]
                        args = cmd.get("args", {})
                        func = self.plugin.get(func_name)
                        if func:
                            self.logs.add(f"▶ 执行函数: {func_name}({', '.join(f'{k}=...' for k in args) if args else ''})", "info")
                            # 捕获 print 输出
                            self.logs.start_capture()
                            try:
                                result = call_plugin_func(func, page, context, **args)
                                self.logs.stop_capture()
                                self.result_queue.put({"status": "ok", "result": result})
                                if func_name == "is_logged_in":
                                    self.auth_status = bool(result) if result is not None else None
                                    self.logs.add(f"is_logged_in 返回: {result}", "info")
                                else:
                                    self.logs.add(f"✓ {func_name} 执行完成", "success")
                            except Exception as e:
                                self.logs.stop_capture()
                                err_msg = str(e)
                                tb = traceback.format_exc()
                                self.logs.add(f"✗ {func_name} 执行失败: {err_msg}", "error")
                                self.result_queue.put({
                                    "status": "error",
                                    "error": err_msg,
                                    "traceback": tb,
                                })
                        else:
                            self.logs.add(f"插件未定义函数: {func_name}", "error")
                            self.result_queue.put({
                                "status": "error",
                                "error": f"插件未定义函数: {func_name}",
                            })
                    elif cmd["action"] == "reload":
                        new_plugin = cmd.get("plugin", {})
                        self.plugin = new_plugin
                        self.logs.add("插件已热重载", "success")
                        self.result_queue.put({"status": "ok", "result": "reloaded"})
                        if new_plugin.get("is_logged_in"):
                            try:
                                self.auth_status = bool(call_plugin_func(new_plugin["is_logged_in"], page, context))
                            except Exception:
                                pass

                # 执行 on_close
                if self.plugin.get("on_close"):
                    self.logs.add("执行 on_close...", "info")
                    self.logs.start_capture()
                    try:
                        call_plugin_func(self.plugin["on_close"], page, context)
                    except Exception:
                        pass
                    finally:
                        self.logs.stop_capture()

                try:
                    context.close()
                except Exception:
                    pass

        except Exception as e:
            self.error = f"浏览器启动失败: {e}\n{traceback.format_exc()}"
            self.logs.add(self.error, "error")
            logger.error(self.error)
        finally:
            self.running = False

    def run_action(self, func_name: str, **args) -> Dict[str, Any]:
        """发送命令执行插件函数, 等待返回结果"""
        if not self.running:
            return {"status": "error", "error": "浏览器未运行"}

        self.command_queue.put({"action": "run", "func_name": func_name, "args": args})
        try:
            return self.result_queue.get(timeout=300)
        except queue.Empty:
            self.logs.add(f"执行超时 (300s): {func_name}", "error")
            return {"status": "error", "error": "执行超时 (300s)"}

    def reload_plugin(self, plugin_functions: Dict[str, Callable]) -> Dict[str, Any]:
        """热重载插件"""
        if not self.running:
            return {"status": "error", "error": "浏览器未运行"}
        self.command_queue.put({"action": "reload", "plugin": plugin_functions})
        try:
            return self.result_queue.get(timeout=10)
        except queue.Empty:
            return {"status": "error", "error": "重载超时"}

    def close(self) -> None:
        """关闭浏览器"""
        self.running = False
        self.command_queue.put({"action": "close"})
        if self.thread:
            self.thread.join(timeout=15)


class BrowserManager:
    """管理所有平台的浏览器实例"""

    def __init__(self, browser_data_dir: Path):
        self.browser_data_dir = Path(browser_data_dir)
        self.browser_data_dir.mkdir(parents=True, exist_ok=True)
        self.instances: Dict[str, BrowserInstance] = {}

    def open_browser(
        self,
        platform_id: str,
        url: str,
        plugin_functions: Dict[str, Callable],
        headless: bool = False,
    ) -> Dict[str, Any]:
        """打开浏览器"""
        existing = self.instances.get(platform_id)
        if existing and existing.running:
            return {"status": "ok", "message": "浏览器已打开"}

        if existing and not existing.running:
            del self.instances[platform_id]

        user_data_dir = self.browser_data_dir / platform_id
        user_data_dir.mkdir(parents=True, exist_ok=True)

        instance = BrowserInstance(platform_id, user_data_dir, url, plugin_functions, headless=headless)
        instance.start()

        for _ in range(40):
            time.sleep(0.2)
            if instance.error:
                return {"status": "error", "error": instance.error}
            if not instance.running:
                return {"status": "error", "error": instance.error or "浏览器启动后立即关闭"}

        self.instances[platform_id] = instance

        # 等待初始 on_open + is_logged_in 完成（最多 30 秒）
        instance._ready.wait(timeout=30)

        return {
            "status": "ok",
            "auth_status": instance.auth_status,
            "message": "浏览器已打开",
        }

    def close_browser(self, platform_id: str) -> Dict[str, Any]:
        instance = self.instances.get(platform_id)
        if not instance:
            return {"status": "error", "error": "浏览器未打开"}
        instance.close()
        del self.instances[platform_id]
        return {"status": "ok", "message": "浏览器已关闭"}

    def is_open(self, platform_id: str) -> bool:
        instance = self.instances.get(platform_id)
        return instance is not None and instance.running

    def get_auth_status(self, platform_id: str) -> Optional[bool]:
        instance = self.instances.get(platform_id)
        if instance:
            return instance.auth_status
        return None

    # ========== 授权过期时间 ==========
    AUTH_EXPIRY_CACHE_FILE = "auth_expiry.json"

    def _auth_expiry_cache_path(self) -> Path:
        return self.browser_data_dir / self.AUTH_EXPIRY_CACHE_FILE

    def get_auth_expiry(self, platform_id: str) -> Optional[float]:
        """获取平台授权过期时间 (Unix 秒); 浏览器打开时读实时值, 否则读缓存"""
        instance = self.instances.get(platform_id)
        if instance and instance.auth_expiry is not None:
            self._save_auth_expiry_cache(platform_id, instance.auth_expiry)
            return instance.auth_expiry
        # 浏览器未打开, 读缓存
        return self._load_auth_expiry_cache().get(platform_id)

    def _save_auth_expiry_cache(self, platform_id: str, expiry: float) -> None:
        try:
            cache = self._load_auth_expiry_cache()
            cache[platform_id] = expiry
            self._auth_expiry_cache_path().write_text(
                json.dumps(cache, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    def _load_auth_expiry_cache(self) -> dict:
        try:
            path = self._auth_expiry_cache_path()
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def run_action(self, platform_id: str, func_name: str, **args) -> Dict[str, Any]:
        instance = self.instances.get(platform_id)
        if not instance or not instance.running:
            return {"status": "error", "error": "浏览器未打开, 请先打开浏览器"}
        return instance.run_action(func_name, **args)

    def get_logs(self, platform_id: str, after: int = 0) -> List[dict]:
        """获取平台日志"""
        instance = self.instances.get(platform_id)
        if not instance:
            return []
        return instance.logs.get_logs(after)

    def clear_logs(self, platform_id: str) -> None:
        """清空平台日志缓存 (新一轮分发前调用, 避免历史日志堆叠)"""
        instance = self.instances.get(platform_id)
        if instance:
            instance.logs.clear()

    def reload_plugin(self, platform_id: str, plugin_functions: Dict[str, Callable]) -> Dict[str, Any]:
        instance = self.instances.get(platform_id)
        if not instance or not instance.running:
            return {"status": "error", "error": "浏览器未打开"}
        return instance.reload_plugin(plugin_functions)

    def get_status(self, platform_id: str) -> Dict[str, Any]:
        instance = self.instances.get(platform_id)
        if not instance:
            return {"browser_open": False, "auth_status": None, "error": None}
        return {
            "browser_open": instance.running,
            "auth_status": instance.auth_status,
            "error": instance.error,
        }

    def close_all(self) -> None:
        for platform_id in list(self.instances.keys()):
            self.close_browser(platform_id)
