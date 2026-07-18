"""
AI 分析模块 — 调用 DeepSeek API 分析小说
分析维度：世界观、人物性格转变、关键情节、主题思想
"""

import json
from typing import List

try:
    from openai import OpenAI
    _OPENAI_OK = True
except ImportError:
    OpenAI = None
    _OPENAI_OK = False

from src.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, CHUNK_SIZE
from src.parser import Chapter

# ── 分析维度与 Prompt ─────────────────────────────────────────

ANALYSIS_DIMENSIONS = {
    "worldview": {
        "label": "世界观",
        "prompt": """你是一位文学评论家。请分析以下小说的世界观设定：

1. **时代背景**：故事发生的时代、社会环境、文化氛围
2. **空间设定**：主要场景、地理环境、空间布局的特点
3. **规则体系**：这个世界中的特殊规则（如有）——权力结构、阶级、魔法/科技体系等
4. **氛围基调**：整体的氛围是怎样的（黑暗/温暖/荒诞/史诗感等）

请用中文回答，尽量具体，引用原文细节支撑观点。""",
    },
    "characters": {
        "label": "人物性格转变",
        "prompt": """你是一位文学评论家。请分析以下小说的人物塑造：

1. **主要人物列表**：列出所有重要人物，各用一句话概括其核心特质
2. **性格转变轨迹**：对每个主要人物，分析其性格在故事进程中的变化——起点是什么状态，经历了什么关键事件，终点是什么状态
3. **人物关系网络**：人物之间的核心关系（盟友/对手/师徒/爱慕等）
4. **人物塑造手法**：作者通过什么方式展现人物性格（对话/心理描写/行动/他人视角等）

请用中文回答，尽量具体，引用原文细节支撑观点。""",
    },
    "plot": {
        "label": "关键情节",
        "prompt": """你是一位文学评论家。请分析以下小说的情节结构：

1. **主线概括**：用一段话概括核心故事线
2. **关键转折点**：列出 3-5 个最重要的情节转折，说明为什么关键
3. **悬念与伏笔**：识别明显的伏笔设置和悬念手法
4. **高潮与结局**：高潮部分的处理方式，结局的类型（闭合/开放/反转等）

请用中文回答，尽量具体，引用原文细节支撑观点。""",
    },
    "themes": {
        "label": "主题思想",
        "prompt": """你是一位文学评论家。请分析以下小说的主题：

1. **核心主题**：小说探讨的核心主题是什么（如成长、救赎、权力、自由等）
2. **象征与隐喻**：文中的重要象征和隐喻及其含义
3. **价值观表达**：作者通过故事传达了怎样的价值观或思考
4. **与现实的关联**：小说是否映射了某种现实议题

请用中文回答，尽量具体，引用原文细节支撑观点。""",
    },
}


class NovelAnalyzer:
    """小说 AI 分析器"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        if not _OPENAI_OK:
            raise RuntimeError("openai 未安装，请运行: pip install openai==1.55.0")
        self.client = OpenAI(
            api_key=api_key or DEEPSEEK_API_KEY,
            base_url=base_url or DEEPSEEK_BASE_URL,
        )

    def _build_context(self, chapters: List[Chapter], max_chars: int = 16000) -> str:
        """
        构建分析上下文：从各章节采样拼接。
        策略：取开头章节全文 + 中间章节摘要 + 结尾章节全文
        """
        if not chapters:
            return ""

        total = len(chapters)
        parts: List[str] = []

        # 开头 2 章全文
        for ch in chapters[:2]:
            parts.append(f"【{ch.title}】\n{ch.content[:2000]}")

        # 中间采样（每 5 章取一章的前 1000 字）
        if total > 4:
            step = max(1, (total - 2) // 5)
            for i in range(2, total - 2, step):
                parts.append(f"【{chapters[i].title}】\n{chapters[i].content[:1000]}")

        # 结尾 2 章全文
        for ch in chapters[-2:]:
            if ch not in chapters[:2]:  # 避免 4 章以下时重复
                parts.append(f"【{ch.title}】\n{ch.content[:2000]}")

        # 拼接并截断
        context = "\n\n---\n\n".join(parts)
        if len(context) > max_chars:
            context = context[:max_chars] + "\n\n[... 文本过长已截断 ...]"
        return context

    def analyze(
        self, chapters: List[Chapter], dimensions: List[str] | None = None
    ) -> dict:
        """
        对小说进行多维度分析（一次性返回所有结果）。

        Args:
            chapters: 章节列表
            dimensions: 要分析的维度，默认全部

        Returns:
            { "worldview": "...", "characters": "...", ... }
        """
        if dimensions is None:
            dimensions = list(ANALYSIS_DIMENSIONS.keys())

        context = self._build_context(chapters)
        results: dict = {}

        for dim in dimensions:
            if dim not in ANALYSIS_DIMENSIONS:
                continue
            cfg = ANALYSIS_DIMENSIONS[dim]
            try:
                resp = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一位专业的文学评论家，擅长分析小说的结构、人物和主题。请基于提供的文本内容进行分析，不要编造文中不存在的信息。",
                        },
                        {
                            "role": "user",
                            "content": f"{cfg['prompt']}\n\n--- 小说文本 ---\n\n{context}",
                        },
                    ],
                    temperature=0.3,
                    max_tokens=4096,
                )
                results[dim] = resp.choices[0].message.content or ""
            except Exception as e:
                results[dim] = f"[分析失败: {str(e)}]"

        return results

    def analyze_stream(
        self, chapters: List[Chapter], dimensions: List[str] | None = None
    ):
        """
        逐维度流式分析，每完成一个维度 yield (dim_key, label, content)。

        Args:
            chapters: 章节列表
            dimensions: 要分析的维度，默认全部

        Yields:
            (dim_key, label, content) 元组
        """
        if dimensions is None:
            dimensions = list(ANALYSIS_DIMENSIONS.keys())

        context = self._build_context(chapters)
        total = len([d for d in dimensions if d in ANALYSIS_DIMENSIONS])
        done = 0

        for dim in dimensions:
            if dim not in ANALYSIS_DIMENSIONS:
                continue
            cfg = ANALYSIS_DIMENSIONS[dim]
            try:
                resp = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一位专业的文学评论家，擅长分析小说的结构、人物和主题。请基于提供的文本内容进行分析，不要编造文中不存在的信息。",
                        },
                        {
                            "role": "user",
                            "content": f"{cfg['prompt']}\n\n--- 小说文本 ---\n\n{context}",
                        },
                    ],
                    temperature=0.3,
                    max_tokens=4096,
                )
                content = resp.choices[0].message.content or ""
            except Exception as e:
                content = f"[分析失败: {str(e)}]"

            done += 1
            yield dim, cfg['label'], content, done, total

    def format_summary(self, results: dict) -> str:
        """将分析结果格式化为可读的摘要文本"""
        lines: List[str] = []
        for dim, cfg in ANALYSIS_DIMENSIONS.items():
            if dim in results and results[dim]:
                lines.append(f"## {cfg['label']}\n\n{results[dim]}\n")
        return "\n\n".join(lines)
