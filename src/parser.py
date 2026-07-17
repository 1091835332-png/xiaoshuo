"""
文件解析器 — 将 txt / epub / docx 文件解析为章节列表。

纯标准库实现：epub 和 docx 本质是 ZIP + XML，用 zipfile + xml.etree 即可解析，
避免 lxml 在 Python 3.15 beta 上的编译问题。
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from bs4 import BeautifulSoup


@dataclass
class Chapter:
    """章节数据结构"""
    index: int
    title: str
    content: str
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.content)


# ── 篇章切分正则 ──────────────────────────────────────────────

_CHAPTER_PATTERNS = [
    # 中文：第X章 / 第X节 / 第X卷 / 第X回 / 第X篇
    re.compile(
        r'^[\s　]*(第[一二三四五六七八九十百千\d]+[章节卷回篇集部])[　\s]*(.*?)$',
        re.MULTILINE,
    ),
    # 英文：Chapter X / CHAPTER X
    re.compile(
        r'^[\s]*(Chapter\s+\d+)[\s:]*(.*?)$',
        re.MULTILINE | re.IGNORECASE,
    ),
    # 序章/楔子/尾声/后记/番外
    re.compile(
        r'^[\s　]*(序章|楔子|尾声|后记|番外[　\s]*(?:[一二三四五六七八九十\d]+)?)[　\s]*(.*?)$',
        re.MULTILINE,
    ),
]

_FALLBACK_CHUNK_CHARS = 5000  # 无章节标记时，按此字数切分


def _clean_html(raw: str) -> str:
    """从 HTML 中提取纯文本"""
    return BeautifulSoup(raw, "html.parser").get_text()


def _xml_namespace(element: ET.Element) -> str:
    """提取 XML 元素的命名空间"""
    tag = element.tag
    if "}" in tag:
        return tag.split("}")[0].lstrip("{")
    return ""


def _strip_ns(tag: str) -> str:
    """去除命名空间前缀，返回纯标签名"""
    return tag.split("}")[-1] if "}" in tag else tag


# ── TXT 解析 ──────────────────────────────────────────────────

def _parse_txt(text: str) -> List[Chapter]:
    """TXT 文件按章节标题切分"""
    # 尝试每种模式，找到第一个匹配的位置
    best_matches: List[re.Match] = []
    best_pattern = None

    for pat in _CHAPTER_PATTERNS:
        matches = list(pat.finditer(text))
        if len(matches) >= 2:
            # 至少有 2 个章节标记才算有效
            if len(matches) > len(best_matches):
                best_matches = matches
                best_pattern = pat

    if not best_matches:
        # 无章节标记，按固定长度切分
        return _chunk_by_size(text, _FALLBACK_CHUNK_CHARS)

    # 按匹配位置切分
    chapters: List[Chapter] = []
    for i, m in enumerate(best_matches):
        start = m.start()
        end = best_matches[i + 1].start() if i + 1 < len(best_matches) else len(text)
        raw = text[start:end].strip()

        title = m.group(1).strip()
        if m.lastindex and m.lastindex >= 2:
            subtitle = m.group(2).strip()
            if subtitle:
                title = f"{title} {subtitle}"

        body = raw[len(m.group(0)):].strip()
        chapters.append(Chapter(index=i, title=title, content=body))

    # 处理章节标记之前的前言
    if best_matches and best_matches[0].start() > 0:
        preface = text[: best_matches[0].start()].strip()
        if preface:
            chapters.insert(0, Chapter(index=-1, title="前言/简介", content=preface))

    # 修复 index
    for i, ch in enumerate(chapters):
        ch.index = i

    return chapters


def _chunk_by_size(text: str, size: int) -> List[Chapter]:
    """按固定字数切分"""
    chapters: List[Chapter] = []
    pos = 0
    idx = 0
    while pos < len(text):
        chunk = text[pos : pos + size]
        chapters.append(Chapter(index=idx, title=f"第{idx + 1}段", content=chunk))
        pos += size
        idx += 1
    return chapters


# ── EPUB 解析 ─────────────────────────────────────────────────

def _parse_epub_content(epub_path: Path) -> str:
    """
    用 zipfile + xml.etree 解析 EPUB。
    EPUB 结构: META-INF/container.xml → 定位 .opf → 列出 spine 顺序 → 提取各 HTML 文本
    """

    with zipfile.ZipFile(epub_path) as zf:
        # 1. 解析 container.xml
        container = ET.parse(zf.open("META-INF/container.xml"))
        root = container.getroot()
        # 找到 rootfile full-path
        ns = _xml_namespace(root)
        rootfile = root.find(f".//{{{ns}}}rootfile") if ns else root.find(".//rootfile")
        if rootfile is None:
            raise ValueError("无效的 EPUB：container.xml 中未找到 rootfile")
        opf_path = rootfile.attrib.get("full-path", "")

        opf_dir = Path(opf_path).parent.as_posix() if "/" in opf_path else ""

        # 2. 解析 .opf
        opf = ET.parse(zf.open(opf_path))
        opf_root = opf.getroot()
        opf_ns = _xml_namespace(opf_root)

        manifest: dict[str, str] = {}  # id → href
        spine_ids: List[str] = []

        for item in opf_root.iter():
            tag = _strip_ns(item.tag)
            if tag == "item":
                mid = item.attrib.get("id", "")
                href = item.attrib.get("href", "")
                if mid and href:
                    manifest[mid] = href
            elif tag == "itemref":
                idref = item.attrib.get("idref", "")
                if idref:
                    spine_ids.append(idref)

        # 3. 按 spine 顺序读取各章节 HTML
        full_text_parts: List[str] = []
        for sid in spine_ids:
            href = manifest.get(sid, "")
            if not href:
                continue
            # 构造资源在 ZIP 中的路径
            resource_path = (
                f"{opf_dir}/{href}"
                if opf_dir
                else href
            )
            try:
                html_bytes = zf.read(resource_path)
                full_text_parts.append(_clean_html(html_bytes.decode("utf-8", errors="replace")))
            except (KeyError, UnicodeDecodeError):
                continue

    return "\n\n".join(full_text_parts)


def _parse_epub(epub_path: Path) -> List[Chapter]:
    """EPUB 解析入口：提取文本后按章节标记切分"""
    full_text = _parse_epub_content(epub_path)
    return _parse_txt(full_text)


# ── DOCX 解析 ─────────────────────────────────────────────────

def _parse_docx_content(docx_path: Path) -> str:
    """
    用 zipfile + xml.etree 解析 DOCX。
    DOCX 结构: word/document.xml 包含正文段落。
    """
    with zipfile.ZipFile(docx_path) as zf:
        doc_xml = ET.parse(zf.open("word/document.xml"))
        root = doc_xml.getroot()
        # 命名空间通常是 http://schemas.openxmlformats.org/wordprocessingml/2006/main
        ns = _xml_namespace(root)

        paragraphs: List[str] = []
        for p in root.iter():
            if _strip_ns(p.tag) != "p":
                continue
            texts: List[str] = []
            for t in p.iter():
                if _strip_ns(t.tag) == "t":
                    texts.append(t.text or "")
            line = "".join(texts)
            if line.strip():
                paragraphs.append(line.strip())

    return "\n\n".join(paragraphs)


def _parse_docx(docx_path: Path) -> List[Chapter]:
    """DOCX 解析入口：提取文本后按章节标记切分"""
    full_text = _parse_docx_content(docx_path)
    return _parse_txt(full_text)


# ── 公共入口 ──────────────────────────────────────────────────

def parse(file_path: str) -> List[Chapter]:
    """
    解析文件并返回章节列表。

    Args:
        file_path: 文件路径（.txt / .epub / .docx）

    Returns:
        Chapter 列表，每个 Chapter 包含 index, title, content, char_count
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace")
        return _parse_txt(text)
    elif suffix == ".epub":
        return _parse_epub(path)
    elif suffix == ".docx":
        return _parse_docx(path)
    else:
        raise ValueError(f"不支持的文件格式: {suffix}，支持 txt / epub / docx")
