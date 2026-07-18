"""
智能分块引擎 — 将章节列表按剧情逻辑切分为 AI 可处理的文本块

设计原则：
- 先按卷/篇章分大单元，再在大单元内按 3-5 章切小块
- 块与块之间保留 200 字重叠，防止剧情/人物在接缝处遗漏
- 每块带章节锚点（起止章节号），所有后续提取都可溯源
- 同时抽取全局骨架（目录+首末章），供骨架层分析用
"""

from dataclasses import dataclass, field
from typing import List, Optional

from src.parser import Chapter


# ── 卷/篇章检测正则 ──────────────────────────────────────────

_VOLUME_PATTERNS = [
    # 第X卷 / 第X部 / 第X篇 / 第X集
    "第[一二三四五六七八九十百千\\d]+[卷部篇集]",
    "Volume\\s+\\d+",
    # 上卷/中卷/下卷
    "[上中下][卷部篇集]",
    # 序卷/终卷
    "[序终][卷部篇集]",
]


@dataclass
class SmartBlock:
    """一个处理块"""
    id: int                          # 块序号 (0-based)
    title: str                       # 块标题（如"第1-5章"或"第一卷·第1-5章"）
    content: str                     # 完整文本内容
    char_count: int                  # 字数
    chapter_start: int               # 起始章节 index
    chapter_end: int                 # 结束章节 index
    volume: str = ""                 # 所属卷名
    is_overlap_from_prev: bool = False  # 是否包含与前一块的重叠内容


@dataclass
class SkeletonContext:
    """全局骨架上下文 — 用于骨架层分析"""
    toc: str                         # 完整目录
    first_chapters: str              # 前 3 章全文
    last_chapters: str               # 末 3 章全文
    volume_beginnings: str           # 每卷首章合集
    volume_endings: str              # 每卷末章合集
    chapter_count: int
    total_chars: int


class SmartChunker:
    """智能分块器"""

    def __init__(
        self,
        chapters_per_block: int = 35,         # 每块章数
        max_chars_per_block: int = 50000,      # 每块字数上限
        overlap_chars: int = 200,              # 块间重叠字数
        detect_volumes: bool = True,           # 是否检测卷结构
    ):
        self.chapters_per_block = chapters_per_block
        self.max_chars_per_block = max_chars_per_block
        self.overlap_chars = overlap_chars
        self.detect_volumes = detect_volumes

    def chunk(self, chapters: List[Chapter]) -> List[SmartBlock]:
        """主入口：将章节列表切分为处理块列表"""
        if not chapters:
            return []

        volumes = self._detect_volume_boundaries(chapters) if self.detect_volumes else []
        blocks: List[SmartBlock] = []
        block_id = 0

        # 确定分块边界：每个 volume 内部再切
        boundaries = self._build_boundaries(chapters, volumes)

        i = 0
        while i < len(boundaries) - 1:
            seg_start = boundaries[i]
            seg_end = boundaries[i + 1]
            seg_chapters = chapters[seg_start:seg_end]

            # 在这个 segment 内部按章数+字数切
            seg_blocks = self._chunk_segment(seg_chapters, seg_start, block_id)
            blocks.extend(seg_blocks)
            block_id += len(seg_blocks)
            i += 1

        # 添加重叠内容
        blocks = self._add_overlaps(blocks, chapters)

        return blocks

    def build_skeleton(self, chapters: List[Chapter]) -> SkeletonContext:
        """构建全局骨架上下文"""
        total = len(chapters)
        if total == 0:
            return SkeletonContext("", "", "", "", "", 0, 0)

        # 目录
        toc_lines = []
        for ch in chapters:
            toc_lines.append(f"第{ch.index + 1}章 {ch.title}")
        toc = "\n".join(toc_lines)

        # 前 3 章
        first = chapters[:min(3, total)]
        first_chapters = self._concat_chapters(first, "开头章节")

        # 末 3 章
        last = chapters[max(0, total - 3):]
        last_chapters = self._concat_chapters(last, "结尾章节")

        # 每卷首末章
        vol_beginnings = []
        vol_endings = []
        volumes = self._detect_volume_boundaries(chapters) if self.detect_volumes else [0]
        if volumes:
            for vi, v_start in enumerate(volumes):
                v_end = volumes[vi + 1] if vi + 1 < len(volumes) else total
                vol_chs = chapters[v_start:v_end]
                if vol_chs:
                    vol_beginnings.append(self._concat_chapters(vol_chs[:1], f"卷{vi + 1}首章"))
                    vol_endings.append(self._concat_chapters(vol_chs[-1:], f"卷{vi + 1}末章"))

        return SkeletonContext(
            toc=toc,
            first_chapters=first_chapters,
            last_chapters=last_chapters,
            volume_beginnings="\n\n".join(vol_beginnings),
            volume_endings="\n\n".join(vol_endings),
            chapter_count=total,
            total_chars=sum(ch.char_count for ch in chapters),
        )

    # ── 内部方法 ──────────────────────────────────────────────

    def _detect_volume_boundaries(self, chapters: List[Chapter]) -> List[int]:
        """检测卷/篇章边界，返回每个卷的起始章节 index"""
        boundaries = [0]
        import re
        for i, ch in enumerate(chapters):
            if i == 0:
                continue
            for pat in _VOLUME_PATTERNS:
                if re.search(pat, ch.title):
                    boundaries.append(i)
                    break
        return sorted(set(boundaries))

    def _build_boundaries(self, chapters: List[Chapter], volumes: List[int]) -> List[int]:
        """构建所有分块边界（卷边界 + 自然断点）"""
        total = len(chapters)
        if not volumes or volumes == [0]:
            return [0, total]

        boundaries = sorted(set(volumes))
        if boundaries[0] != 0:
            boundaries.insert(0, 0)
        if boundaries[-1] != total:
            boundaries.append(total)
        return boundaries

    def _chunk_segment(
        self, chapters: List[Chapter], global_offset: int, start_id: int
    ) -> List[SmartBlock]:
        """在一个 segment 内部切块"""
        blocks: List[SmartBlock] = []
        i = 0
        bid = start_id

        while i < len(chapters):
            # 取 chapters_per_block 章，但不超过字数上限
            end_i = min(i + self.chapters_per_block, len(chapters))
            chunk_chs = chapters[i:end_i]
            content = self._concat_chapters(chunk_chs, "")

            # 字数超限时回退
            total_chars = sum(c.char_count for c in chunk_chs)
            while total_chars > self.max_chars_per_block and end_i > i + 1:
                end_i -= 1
                chunk_chs = chapters[i:end_i]
                total_chars = sum(c.char_count for c in chunk_chs)

            title = self._block_title(chunk_chs, global_offset + i, global_offset + end_i - 1)

            blocks.append(SmartBlock(
                id=bid,
                title=title,
                content=content,
                char_count=total_chars,
                chapter_start=global_offset + i,
                chapter_end=global_offset + end_i - 1,
            ))

            bid += 1
            i = end_i

        return blocks

    def _add_overlaps(self, blocks: List[SmartBlock], chapters: List[Chapter]) -> List[SmartBlock]:
        """为相邻块之间添加重叠内容"""
        if not self.overlap_chars or len(blocks) < 2:
            return blocks

        for i in range(1, len(blocks)):
            prev_end = blocks[i - 1].chapter_end
            curr_start = blocks[i].chapter_start
            if prev_end < curr_start:
                # 不连续，无需重叠
                continue

            # 从前一块末尾取重叠文字
            prev_ch = chapters[blocks[i - 1].chapter_end]
            overlap_text = prev_ch.content[-self.overlap_chars:] if prev_ch.content else ""
            if overlap_text:
                blocks[i].content = (
                    f"[与前块重叠 · 章节{prev_ch.index + 1} {prev_ch.title}]\n\n"
                    f"{overlap_text}\n\n"
                    f"---\n\n"
                    f"{blocks[i].content}"
                )
                blocks[i].is_overlap_from_prev = True

        return blocks

    def _concat_chapters(self, chapters: List[Chapter], label: str = "") -> str:
        """拼接多个章节为一段文本"""
        parts = []
        if label:
            parts.append(f"【{label}】\n")
        for ch in chapters:
            parts.append(f"\n{'=' * 40}\n第{ch.index + 1}章 {ch.title}\n{'=' * 40}\n\n{ch.content}")
        return "".join(parts)

    def _block_title(self, chapters: List[Chapter], start_idx: int, end_idx: int) -> str:
        """生成块标题"""
        if not chapters:
            return f"第{start_idx + 1}-{end_idx + 1}章"
        start_title = chapters[0].title
        end_title = chapters[-1].title
        return f"第{start_idx + 1}-{end_idx + 1}章 ({start_title} → {end_title})"

    @staticmethod
    def blocks_to_chapter_map(blocks: List[SmartBlock]) -> dict:
        """生成块→章节的索引映射，方便后续按章节号溯源"""
        mapping: dict = {}
        for blk in blocks:
            for ci in range(blk.chapter_start, blk.chapter_end + 1):
                mapping.setdefault(ci, []).append(blk.id)
        return mapping
