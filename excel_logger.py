"""Excel 分发记录日志 - 每次分发完成后追加记录到桌面 Excel 文件"""
import socket
import threading
import logging
from datetime import datetime
from pathlib import Path
from openpyxl import Workbook, load_workbook

logger = logging.getLogger(__name__)

EXCEL_PATH = Path(r"C:\Users\Admin\Desktop\自动分发记录.xlsx")
HEADERS = ["分发时间", "文章标题", "发布平台", "发布链接", "分发人"]
_lock = threading.Lock()


def get_local_ip() -> str:
    """获取本机 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "unknown"


def _ensure_excel() -> None:
    """确保 Excel 文件存在，不存在则创建并写入表头"""
    if not EXCEL_PATH.exists():
        wb = Workbook()
        ws = wb.active
        ws.title = "分发记录"
        ws.append(HEADERS)
        # 设置列宽
        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 40
        ws.column_dimensions["C"].width = 16
        ws.column_dimensions["D"].width = 50
        ws.column_dimensions["E"].width = 16
        wb.save(str(EXCEL_PATH))
        logger.info(f"已创建 Excel 记录文件: {EXCEL_PATH}")


def append_record(title: str, platform_name: str, link: str = "") -> bool:
    """
    追加一条分发记录到 Excel

    title: 文章标题
    platform_name: 发布平台名称
    link: 发布链接 (暂不填写, 留空)
    返回: True=成功, False=失败
    """
    with _lock:
        try:
            _ensure_excel()
            wb = load_workbook(str(EXCEL_PATH))
            ws = wb.active

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ip = get_local_ip()

            ws.append([now, title, platform_name, link, ip])
            wb.save(str(EXCEL_PATH))
            logger.info(f"已追加分发记录: {title} -> {platform_name} ({now})")
            return True
        except Exception as e:
            logger.error(f"追加 Excel 记录失败: {e}")
            return False
