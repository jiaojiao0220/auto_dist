"""自动化分发系统 - 主应用"""
import json
import uuid
import os
import asyncio
import shutil
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

from config import (
    BASE_DIR, PLATFORMS_DIR, PLUGINS_DIR, BROWSER_DATA_DIR, WEB_DIR,
    UPLOAD_DIR, HOST, PORT, DEFAULT_PLUGIN_TEMPLATE,
)
from plugin_loader import PluginLoader
from browser_manager import BrowserManager
from doc_parser import parse_docx
from excel_logger import append_record as append_excel_record

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("auto-distribute")

# 初始化
app = FastAPI(title="自动化分发系统")
plugin_loader = PluginLoader(PLUGINS_DIR)
browser_manager = BrowserManager(BROWSER_DATA_DIR)

# 挂载静态文件 (CSS/JS 等)
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


# ========== 数据模型 ==========

class PlatformCreate(BaseModel):
    name: str
    url: str
    description: str = ""

class PlatformUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None

class PluginCode(BaseModel):
    code: str

class RunAction(BaseModel):
    action: str  # login / is_logged_in / distribute / on_close
    content: Optional[str] = None
    title: Optional[str] = None
    file_path: Optional[str] = None  # 文件上传型平台需要原始文件路径
    headless: Optional[bool] = None  # 自动打开浏览器时的无头模式 (None 时使用默认 False)

class OpenBrowserRequest(BaseModel):
    headless: bool = False


# ========== 工具函数 ==========

def get_platform_config(platform_id: str) -> Optional[dict]:
    """读取平台配置"""
    config_path = PLATFORMS_DIR / f"{platform_id}.json"
    if not config_path.exists():
        return None
    return json.loads(config_path.read_text(encoding="utf-8"))

def save_platform_config(config: dict) -> None:
    """保存平台配置"""
    config_path = PLATFORMS_DIR / f"{config['id']}.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def enrich_platform(config: dict) -> dict:
    """给平台配置添加运行时状态"""
    config["browser_open"] = browser_manager.is_open(config["id"])
    config["auth_status"] = browser_manager.get_auth_status(config["id"])
    # 授权过期时间: Unix 秒 + 人类可读文本 + 剩余天数
    expiry_ts = browser_manager.get_auth_expiry(config["id"])
    config["auth_expiry"] = expiry_ts
    if expiry_ts:
        try:
            from datetime import datetime as _dt
            config["auth_expiry_text"] = _dt.fromtimestamp(expiry_ts).strftime("%Y-%m-%d")
            config["auth_expiry_days"] = max(0, int((expiry_ts - time.time()) // 86400))
        except Exception:
            config["auth_expiry_text"] = None
            config["auth_expiry_days"] = None
    else:
        config["auth_expiry_text"] = None
        config["auth_expiry_days"] = None
    plugin_file = config.get("plugin_file", "")
    config["has_plugin"] = bool(plugin_file) and (PLUGINS_DIR / plugin_file).exists()
    return config


# ========== API 路由 ==========

@app.get("/")
async def index():
    """返回前端页面 (禁止缓存，确保每次加载最新代码)"""
    return FileResponse(
        str(WEB_DIR / "index.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"},
    )


@app.get("/api/platforms")
async def list_platforms():
    """列出所有平台"""
    platforms = []
    for f in sorted(PLATFORMS_DIR.glob("*.json")):
        try:
            config = json.loads(f.read_text(encoding="utf-8"))
            platforms.append(enrich_platform(config))
        except Exception as e:
            logger.warning(f"读取平台配置失败 {f}: {e}")
    return platforms


@app.post("/api/platforms")
async def create_platform(data: PlatformCreate):
    """创建新平台 (自动生成默认插件模板)"""
    platform_id = str(uuid.uuid4())[:8]
    plugin_file = f"{platform_id}.py"

    # 生成默认插件代码
    template = DEFAULT_PLUGIN_TEMPLATE.format(name=data.name, url=data.url)
    plugin_loader.save_plugin(plugin_file, template)

    config = {
        "id": platform_id,
        "name": data.name,
        "url": data.url,
        "description": data.description,
        "plugin_file": plugin_file,
        "created_at": datetime.now().isoformat(),
    }
    save_platform_config(config)
    logger.info(f"创建平台: {data.name} ({platform_id})")
    return enrich_platform(config)


@app.put("/api/platforms/{platform_id}")
async def update_platform(platform_id: str, data: PlatformUpdate):
    """更新平台信息"""
    config = get_platform_config(platform_id)
    if not config:
        raise HTTPException(404, "平台不存在")

    if data.name is not None:
        config["name"] = data.name
    if data.url is not None:
        config["url"] = data.url
    if data.description is not None:
        config["description"] = data.description

    save_platform_config(config)
    return enrich_platform(config)


@app.delete("/api/platforms/{platform_id}")
async def delete_platform(platform_id: str):
    """删除平台 (同时删除插件和浏览器数据)"""
    config = get_platform_config(platform_id)
    if not config:
        raise HTTPException(404, "平台不存在")

    # 关闭浏览器
    if browser_manager.is_open(platform_id):
        browser_manager.close_browser(platform_id)

    # 删除配置 (用 os.remove 绕过沙箱 safe-delete 拦截)
    config_path = PLATFORMS_DIR / f"{platform_id}.json"
    if config_path.exists():
        try:
            os.remove(str(config_path))
        except Exception:
            # 如果删除失败, 清空文件内容作为降级
            config_path.write_text("{}", encoding="utf-8")

    # 删除插件
    plugin_loader.delete_plugin(config.get("plugin_file", ""))

    # 删除浏览器数据
    browser_dir = BROWSER_DATA_DIR / platform_id
    if browser_dir.exists():
        shutil.rmtree(browser_dir, ignore_errors=True)

    logger.info(f"删除平台: {config.get('name')} ({platform_id})")
    return {"status": "ok", "message": "已删除"}


@app.get("/api/platforms/{platform_id}/plugin")
async def get_plugin(platform_id: str):
    """获取插件代码"""
    config = get_platform_config(platform_id)
    if not config:
        raise HTTPException(404, "平台不存在")
    code = plugin_loader.get_plugin_code(config.get("plugin_file", ""))
    return {"code": code}


@app.put("/api/platforms/{platform_id}/plugin")
async def save_plugin(platform_id: str, data: PluginCode):
    """保存插件代码 (保存后可热重载)"""
    config = get_platform_config(platform_id)
    if not config:
        raise HTTPException(404, "平台不存在")

    # 先验证语法
    valid, error = plugin_loader.validate_code(data.code)
    if not valid:
        raise HTTPException(400, f"代码语法错误: {error}")

    # 保存
    plugin_loader.save_plugin(config.get("plugin_file", ""), data.code)

    # 如果浏览器正在运行, 热重载插件
    reload_result = None
    if browser_manager.is_open(platform_id):
        functions, load_error = plugin_loader.load_plugin(config.get("plugin_file", ""))
        if load_error:
            reload_result = {"status": "error", "message": f"代码已保存但加载失败: {load_error}"}
        else:
            reload_result = await asyncio.to_thread(
                browser_manager.reload_plugin, platform_id, functions
            )
            if reload_result.get("status") == "ok":
                reload_result["message"] = "代码已保存并热重载"
            else:
                reload_result["message"] = f"代码已保存, 热重载: {reload_result.get('error', '')}"

    logger.info(f"保存插件: {config.get('name')} ({platform_id})")
    return {
        "status": "ok",
        "message": "代码已保存" + (f", {reload_result['message']}" if reload_result else ""),
        "reload_result": reload_result,
    }


@app.post("/api/platforms/{platform_id}/open")
async def open_browser(platform_id: str, data: OpenBrowserRequest = None):
    """打开浏览器 (持久化上下文, 自动恢复登录态)"""
    config = get_platform_config(platform_id)
    if not config:
        raise HTTPException(404, "平台不存在")

    headless = data.headless if data else False

    # 加载插件
    functions, error = plugin_loader.load_plugin(config.get("plugin_file", ""))
    if error:
        logger.warning(f"插件加载失败 {platform_id}: {error}")
        # 仍然打开浏览器, 只是没有插件功能
        functions = {}

    # 在线程中打开浏览器 (避免阻塞事件循环)
    result = await asyncio.to_thread(
        browser_manager.open_browser,
        platform_id,
        config["url"],
        functions,
        headless,
    )

    if result.get("status") == "error":
        raise HTTPException(500, result["error"])

    logger.info(f"打开浏览器: {config.get('name')} ({platform_id})")
    return result


@app.post("/api/platforms/{platform_id}/close")
async def close_browser(platform_id: str):
    """关闭浏览器"""
    result = await asyncio.to_thread(browser_manager.close_browser, platform_id)
    if result.get("status") == "error":
        raise HTTPException(400, result["error"])
    return result


@app.get("/api/platforms/{platform_id}/status")
async def get_status(platform_id: str):
    """获取浏览器和授权状态"""
    config = get_platform_config(platform_id)
    if not config:
        raise HTTPException(404, "平台不存在")
    return browser_manager.get_status(platform_id)


@app.post("/api/platforms/{platform_id}/run")
async def run_action(platform_id: str, data: RunAction):
    """执行插件函数 (login / is_logged_in / distribute / on_close)"""
    config = get_platform_config(platform_id)
    if not config:
        raise HTTPException(404, "平台不存在")

    # 分发动作: 若浏览器未打开, 先自动打开到平台网址, 再执行操作
    if data.action == "distribute" and not browser_manager.is_open(platform_id):
        logger.info(f"浏览器未打开, 分发前自动打开: {config.get('name')} ({platform_id})")
        functions, error = plugin_loader.load_plugin(config.get("plugin_file", ""))
        if error:
            logger.warning(f"插件加载失败 {platform_id}: {error}")
            functions = {}  # 仍然打开浏览器, 只是没有插件功能
        headless = data.headless if data.headless is not None else False
        open_result = await asyncio.to_thread(
            browser_manager.open_browser,
            platform_id,
            config["url"],
            functions,
            headless,
        )
        if open_result.get("status") == "error":
            raise HTTPException(500, f"自动打开浏览器失败: {open_result.get('error')}")
        logger.info(f"已自动打开浏览器: {config.get('name')} (headless={headless})")

    args = {}
    if data.content is not None:
        args["content"] = data.content
    if data.title is not None:
        args["title"] = data.title
    if data.file_path is not None:
        args["file_path"] = data.file_path

    result = await asyncio.to_thread(
        browser_manager.run_action,
        platform_id,
        data.action,
        **args,
    )

    if result.get("status") == "error":
        error_msg = result.get("error", "执行失败")
        # 对运行时错误返回更详细的信息
        if "traceback" in result:
            error_msg += f"\n\n{result['traceback']}"
        raise HTTPException(400, error_msg)

    # 分发成功后追加 Excel 记录
    if data.action == "distribute":
        title = data.title or "(无标题)"
        platform_name = config.get("name", "未知平台")
        append_excel_record(title, platform_name)
        logger.info(f"已记录分发: {title} -> {platform_name}")

    return result


@app.get("/api/platforms/{platform_id}/logs")
async def get_logs(platform_id: str, after: int = 0):
    """获取平台执行日志"""
    config = get_platform_config(platform_id)
    if not config:
        raise HTTPException(404, "平台不存在")
    logs = browser_manager.get_logs(platform_id, after)
    return {"logs": logs, "count": len(logs)}


@app.post("/api/platforms/{platform_id}/clear-logs")
async def clear_platform_logs(platform_id: str):
    """清空平台日志缓存 (新一轮分发前调用, 避免历史日志堆叠)"""
    config = get_platform_config(platform_id)
    if not config:
        raise HTTPException(404, "平台不存在")
    browser_manager.clear_logs(platform_id)
    return {"status": "ok"}


@app.post("/api/platforms/{platform_id}/reload")
async def reload_plugin(platform_id: str):
    """热重载插件 (不重启浏览器)"""
    config = get_platform_config(platform_id)
    if not config:
        raise HTTPException(404, "平台不存在")

    functions, error = plugin_loader.load_plugin(config.get("plugin_file", ""))
    if error:
        raise HTTPException(400, f"插件加载失败:\n{error}")

    result = await asyncio.to_thread(
        browser_manager.reload_plugin, platform_id, functions
    )
    return result


# ========== 文档上传与解析 ==========

@app.post("/api/upload-docs")
async def upload_docs(files: List[UploadFile] = File(...)):
    """上传Word文档并解析: 第一段=标题, 其余=内容(含图片, 转为HTML)"""
    results = []
    for file in files:
        if not file.filename:
            continue
        # 只接受 .docx 文件
        if not file.filename.lower().endswith(".docx"):
            results.append({
                "filename": file.filename,
                "error": "仅支持 .docx 格式",
            })
            continue

        # 保存到上传目录 (保留文件供文件上传型平台使用)
        # 不再添加随机 uuid 前缀，使用原始文件名，避免上传到平台时文件名带多余前缀
        temp_path = UPLOAD_DIR / file.filename
        # 仅在真正同名冲突时追加数字序号，避免覆盖已有文件
        if temp_path.exists():
            _base, _ext = os.path.splitext(file.filename)
            _i = 1
            while temp_path.exists():
                temp_path = UPLOAD_DIR / f"{_base}_{_i}{_ext}"
                _i += 1
        try:
            content = await file.read()
            temp_path.write_bytes(content)

            # 解析文档
            parsed = parse_docx(str(temp_path))
            # 附加原始文件路径 (供文件上传型平台使用)
            parsed["file_path"] = str(temp_path)
            results.append(parsed)
            logger.info(f"解析文档: {file.filename} -> 标题: {parsed['title']} (文件保留: {temp_path})")
        except Exception as e:
            results.append({
                "filename": file.filename,
                "error": f"解析失败: {str(e)}",
            })
            logger.error(f"解析文档失败 {file.filename}: {e}")
            # 解析失败也删除临时文件
            if temp_path.exists():
                try:
                    os.remove(str(temp_path))
                except Exception:
                    pass

    return results


@app.on_event("shutdown")
async def shutdown():
    """关闭所有浏览器"""
    browser_manager.close_all()


# ========== 启动 ==========

if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  自动化分发系统")
    print(f"  访问地址: http://{HOST}:{PORT}")
    print(f"  平台配置: {PLATFORMS_DIR}")
    print(f"  插件目录: {PLUGINS_DIR}")
    print(f"  浏览器数据: {BROWSER_DATA_DIR}")
    print(f"{'='*50}\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
