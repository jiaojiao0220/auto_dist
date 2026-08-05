# auto_dist

多平台自动化分发系统 —— 基于 FastAPI + Playwright，一键将文章/文档分发到多个内容平台（CSDN、原创力文档等）。

## 功能特性

- **多平台管理**：自定义添加平台（名称、URL、描述），每个平台配套独立 Python 插件
- **插件热加载**：在线编辑插件代码，保存后自动热重载（无需重启后端）
- **登录态持久化**：Playwright 持久化浏览器上下文，自动保存 cookies/localStorage，重开浏览器登录态自动恢复
- **一键分发**：上传 Word 文档自动解析，批量分发到多个平台
- **实时日志**：前端终端风格日志面板，1s 轮询增量拉取，不同级别颜色区分
- **无头模式**：支持 headless 模式运行，适合服务器/无人值守场景

## 技术栈

- 后端：FastAPI + Playwright (sync API in threads)
- 前端：原生 HTML/JS（深色终端风格日志面板）
- 文档解析：python-docx
- 日志记录：Excel 分发记录

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

启动后访问 `http://127.0.0.1:8765`。

## 插件接口

每个平台一个插件文件，需实现以下接口：

| 函数 | 说明 |
|------|------|
| `on_open(page)` | 打开平台网页后的初始化操作 |
| `is_logged_in(page)` | 检查是否已登录，返回 True/False |
| `login(page)` | 执行登录流程 |
| `distribute(page, context, title, content)` | 分发内容到平台 |
| `on_close()` | 浏览器关闭前的收尾操作 |

## 目录结构

```
├── main.py              # FastAPI 后端入口
├── browser_manager.py   # 浏览器管理器（持久化上下文、日志收集）
├── plugin_loader.py     # 插件动态加载
├── doc_parser.py        # Word 文档解析
├── excel_logger.py      # Excel 分发记录
├── plugins/             # 各平台插件
├── web/index.html       # 前端页面
└── platforms/           # 平台配置 (JSON)
```
