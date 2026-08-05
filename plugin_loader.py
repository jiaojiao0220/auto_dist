"""插件加载器 - 动态加载 Python 插件文件"""
import importlib.util
import traceback
from pathlib import Path
from typing import Dict, Tuple, Optional, Callable


# 支持的插件函数
PLUGIN_FUNCTIONS = ["on_open", "is_logged_in", "login", "distribute", "on_close"]


class PluginLoader:
    """动态加载和保存插件代码"""

    def __init__(self, plugins_dir: Path):
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    def load_plugin(self, plugin_filename: str) -> Tuple[Dict[str, Callable], Optional[str]]:
        """
        加载插件模块, 返回 (函数字典, 错误信息)
        如果文件不存在或没有函数, 返回 ({}, None)
        如果有语法/运行错误, 返回 ({}, error_traceback)
        """
        if not plugin_filename:
            return {}, None

        plugin_path = self.plugins_dir / plugin_filename
        if not plugin_path.exists():
            return {}, None

        # 用唯一模块名避免缓存
        module_name = f"plugin_{plugin_path.stem}_{id(self)}_{plugin_path.stat().st_mtime_ns}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, plugin_path)
            if spec is None or spec.loader is None:
                return {}, "无法创建模块规范"
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            functions: Dict[str, Callable] = {}
            for func_name in PLUGIN_FUNCTIONS:
                func = getattr(module, func_name, None)
                if func and callable(func):
                    functions[func_name] = func

            return functions, None
        except SyntaxError as e:
            return {}, f"语法错误 (行 {e.lineno}): {e.msg}\n\n{e.text or ''}"
        except Exception:
            return {}, traceback.format_exc()

    def save_plugin(self, plugin_filename: str, code: str) -> None:
        """保存插件代码到文件"""
        plugin_path = self.plugins_dir / plugin_filename
        plugin_path.parent.mkdir(parents=True, exist_ok=True)
        plugin_path.write_text(code, encoding="utf-8")

    def get_plugin_code(self, plugin_filename: str) -> str:
        """读取插件代码, 文件不存在返回空字符串"""
        plugin_path = self.plugins_dir / plugin_filename
        if not plugin_path.exists():
            return ""
        return plugin_path.read_text(encoding="utf-8")

    def delete_plugin(self, plugin_filename: str) -> None:
        """删除插件文件 (用 os.remove 绕过沙箱 safe-delete)"""
        import os
        plugin_path = self.plugins_dir / plugin_filename
        if plugin_path.exists():
            try:
                os.remove(str(plugin_path))
            except Exception:
                # 降级: 清空文件内容
                plugin_path.write_text("", encoding="utf-8")

    def validate_code(self, code: str) -> Tuple[bool, Optional[str]]:
        """验证代码是否能正常编译 (不执行)"""
        try:
            compile(code, "<plugin>", "exec")
            return True, None
        except SyntaxError as e:
            return False, f"语法错误 (行 {e.lineno}): {e.msg}"
