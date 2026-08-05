"""Excel 分发记录日志 - 每次分发完成后追加记录到桌面 Excel 文件"""
import socket
import threading
import time
import logging
from datetime import datetime
from pathlib import Path
from openpyxl import Workbook, load_workbook

logger = logging.getLogger(__name__)

EXCEL_PATH = Path(r"C:\Users\Admin\Desktop\自动分发记录.xlsx")
HEADERS = ["分发时间", "文章标题", "发布平台", "发布链接", "分发人"]
_lock = threading.Lock()
_MAX_RETRIES = 5  # 文件被 Excel/WPS 占用时最大重试次数
_RETRY_INTERVAL = 1.0  # 每次重试间隔 (秒)


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
    else:
        # 文件存在但结构异常(如手动新建的空表)时, 补上表头
        try:
            wb = load_workbook(str(EXCEL_PATH))
            ws = wb.active
            first_row = [c.value for c in ws[1]] if ws.max_row > 0 else []
            if not first_row or first_row[0] != HEADERS[0]:
                ws.insert_rows(1)
                for col, h in enumerate(HEADERS, start=1):
                    ws.cell(row=1, column=col, value=h)
                wb.save(str(EXCEL_PATH))
                logger.info(f"已补齐 Excel 表头: {EXCEL_PATH}")
        except Exception as e:
            logger.warning(f"检查/修复 Excel 表头失败(将按新建处理): {e}")


def append_record(title: str, platform_name: str, link: str = "") -> bool:
    """
    追加一条分发记录到 Excel

    title: 文章标题
    platform_name: 发布平台名称
    link: 发布链接 (暂不填写, 留空)
    返回: True=成功, False=失败
    """
    with _lock:
        last_err = None
        for attempt in range(1, _MAX_RETRIES + 1):
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
            except PermissionError as e:
                last_err = e
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        f"Excel 文件被占用(可能正被 Excel/WPS 打开), 第 {attempt}/{_MAX_RETRIES} 次重试: {EXCEL_PATH.name}"
                    )
                    time.sleep(_RETRY_INTERVAL)
                else:
                    logger.error(
                        f"追加 Excel 记录失败: {e}。请关闭正在打开的「自动分发记录.xlsx」后重试。"
                    )
                    return False
            except Exception as e:
                last_err = e
                logger.error(f"追加 Excel 记录失败: {e}")
                return False
        return False
