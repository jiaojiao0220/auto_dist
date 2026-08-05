"""Word文档解析器 - 提取标题和内容(含图片)，转为HTML用于粘贴"""
import base64
import re
from pathlib import Path
from typing import Dict, List
from docx import Document
from docx.oxml.ns import qn


def parse_docx(file_path: str) -> Dict:
    """
    解析Word文档:
    - 第一段 = 标题
    - 其余段落 = 内容(含图片)，转为HTML
    """
    doc = Document(file_path)
    paragraphs = doc.paragraphs

    if not paragraphs:
        return {
            "title": Path(file_path).stem,
            "html_content": "",
            "filename": Path(file_path).name,
        }

    # 第一段是标题
    title = paragraphs[0].text.strip()
    if not title:
        title = Path(file_path).stem

    # 解析剩余内容为HTML
    html_parts: List[str] = []
    for para in paragraphs[1:]:
        html = _paragraph_to_html(para, doc)
        if html:
            html_parts.append(html)

    return {
        "title": title,
        "html_content": "\n".join(html_parts),
        "filename": Path(file_path).name,
    }


def _paragraph_to_html(para, doc) -> str:
    """将一个段落转为HTML，处理文本和内嵌图片"""
    parts: List[str] = []

    for run in para.runs:
        # 处理文本
        if run.text:
            text = _escape_html(run.text)
            # 加粗
            if run.bold:
                text = f"<strong>{text}</strong>"
            # 斜体
            if run.italic:
                text = f"<em>{text}</em>"
            parts.append(text)

        # 处理图片 (w:drawing 元素)
        drawings = run._element.findall(qn("w:drawing"))
        for drawing in drawings:
            img_html = _extract_image_from_drawing(drawing, doc)
            if img_html:
                parts.append(img_html)

        # 处理旧格式图片 (w:pict 元素)
        picts = run._element.findall(qn("w:pict"))
        for pict in picts:
            img_html = _extract_image_from_pict(pict, doc)
            if img_html:
                parts.append(img_html)

    # 也检查段落级别直接包含的图片 (不在 runs 中的情况)
    processed_runs = set(id(run._element) for run in para.runs)
    for child in para._element:
        if child.tag == qn("w:r") and id(child) not in processed_runs:
            for drawing in child.findall(qn("w:drawing")):
                img_html = _extract_image_from_drawing(drawing, doc)
                if img_html:
                    parts.append(img_html)

    text = "".join(parts)
    text_stripped = re.sub(r"<[^>]+>", "", text).strip()

    if text_stripped or "<img" in text:
        # 处理空段落在图片前后
        if not text_stripped and "<img" in text:
            return f"<p>{text}</p>"
        return f"<p>{text}</p>"
    return ""


def _extract_image_from_drawing(drawing_elem, doc) -> str:
    """从 w:drawing 元素提取图片，返回 <img> HTML"""
    # 查找 a:blip 元素 (内嵌图片)
    blips = drawing_elem.findall(".//" + qn("a:blip"))
    for blip in blips:
        embed = blip.get(qn("r:embed"))
        if embed and embed in doc.part.related_parts:
            image_part = doc.part.related_parts[embed]
            b64 = base64.b64encode(image_part.blob).decode()
            content_type = getattr(image_part, "content_type", "image/png")
            return f'<img src="data:{content_type};base64,{b64}" alt=""/>'
    return ""


def _extract_image_from_pict(pict_elem, doc) -> str:
    """从 w:pict 元素提取图片 (旧格式)"""
    # VML 格式 imagedata
    imagedata = pict_elem.findall(".//" + qn("v:imagedata"))
    for img_data in imagedata:
        embed = img_data.get(qn("r:id"))
        if embed and embed in doc.part.related_parts:
            image_part = doc.part.related_parts[embed]
            b64 = base64.b64encode(image_part.blob).decode()
            content_type = getattr(image_part, "content_type", "image/png")
            return f'<img src="data:{content_type};base64,{b64}" alt=""/>'
    return ""


def _escape_html(text: str) -> str:
    """转义HTML特殊字符"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
