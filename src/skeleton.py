"""
骨架层分析器 — 只用目录+首末章输出全书顶层框架
轻量、快速，作为后续中观/微观提取的索引
"""

from dataclasses import dataclass, field
from typing import List

try:
    from openai import OpenAI
    _OPENAI_OK = True
except ImportError:
    OpenAI = None
    _OPENAI_OK = False

from src.parser import Chapter

# ── 骨架层四个维度的 Prompt ──────────────────────────────────

SKELETON_WORLDVIEW_PROMPT = """你是一位资深小说设定分析师。请基于提供的小说目录和前几章文本，
提取全书的世界观核心规则框架。注意：你只看到极少文本，目标是搭建框架索引，不是填充全貌。

输出严格按以下结构：

## 世界背景
- 时代/文明级别（古代/现代/未来/星际/末日等）
- 社会形态（王国/联邦/城邦/宗门/学院等）

## 核心力量体系
- 力量类型（魔法/斗气/科技/异能/修仙等）
- 等级划分（如有明确的等级命名，列出）
- 修炼/进阶方式

## 势力总览
- 主要势力/组织及其定位（一句话概括）
- 势力间关系（敌对/联盟/中立）

## 核心法则
- 这个世界独有的重要规则（如"只有男性才能使用魔力""死亡后三天内可复活"等）

请用中文回答。框架性输出，每项1-2句话即可。"""

SKELETON_PLOT_PROMPT = """你是一位资深小说剧情分析师。请基于提供的小说目录和前几章文本，
梳理全书的主线剧情时间轴。注意：你只看到极少文本，目标是搭建框架。

输出严格按以下结构：

## 主线概括
- 一句话概括整个故事的核心冲突/目标

## 关键转折点预测
- 基于目录推测的5-8个关键剧情转折，每个标注：
  - 预估所在卷/章节范围
  - 转折性质（启程/升级/转折/低谷/高潮/结局）
  - 一句话描述该阶段的核心事件

## 叙事结构
- 故事类型（升级流/悬疑/恋爱/群像/无限流等）
- 叙事视角（第一人称/第三人称/多视角）
- 时间线特点（线性/倒叙/插叙/双线并行）

请用中文回答。框架性输出。"""

SKELETON_CHARACTERS_PROMPT = """你是一位资深小说人物分析师。请基于提供的小说目录和前几章文本，
建立核心人物名录。注意：你只看到极少文本，目标是建立索引框架。

输出严格按以下结构：

## 主角团
- 主角：姓名、身份定位、性格基调、成长方向预判
- 核心伙伴（2-4人）：各一句话定位

## 主要反派/对手
- 列出已出现或目录暗示的关键对手，各一句话定位

## 重要配角
- 导师/前辈/家人/关键NPC等，各一句话定位

## 人物关系网预判
- 基于目录推测的人物关系结构（师徒/队友/三角/阵营对峙等）

请用中文回答。框架性输出。未确认的信息标注"[推测]"。"""

SKELETON_MYSTERIES_PROMPT = """你是一位资深小说悬念分析师。请基于提供的小说目录和前几章文本，
识别全书的悬念和伏笔框架。

输出严格按以下结构：

## 核心悬念
- 故事最核心的未解之谜（如"主角身世真相""世界为什么崩坏"等），列出3-5个
- 每个标注：悬念内容、关联人物、预估揭晓阶段

## 长线伏笔
- 基于前几章和目录暗示的可能伏笔，列出3-5个
- 每个标注：伏笔内容、埋设位置、预估回收时机

## 未解疑问
- 当前文本中明确提出的、尚未解答的问题清单

请用中文回答。框架性输出。未确认的信息标注"[推测]"。
"""

SKELETON_DIMS = {
    "worldview":  {"label": "世界观核心规则总纲", "prompt": SKELETON_WORLDVIEW_PROMPT},
    "plot":       {"label": "全书主线剧情时间轴", "prompt": SKELETON_PLOT_PROMPT},
    "characters": {"label": "核心人物名录",       "prompt": SKELETON_CHARACTERS_PROMPT},
    "mysteries":  {"label": "核心悬念与伏笔清单", "prompt": SKELETON_MYSTERIES_PROMPT},
}


def build_skeleton_context(chapters: List[Chapter], max_chars: int = 6000) -> str:
    """
    构建骨架分析上下文：目录 + 前2章 + 最后1章 + 每卷首章采样。
    控制在 6000 字以内，确保 AI 快速输出框架。
    """
    if not chapters:
        return ""

    parts: List[str] = []

    # 目录
    parts.append("## 全书目录\n")
    for ch in chapters:
        parts.append(f"- [{ch.index}] {ch.title} ({ch.char_count}字)")
    parts.append("")

    # 前 2 章全文（各取前 1200 字）
    for ch in chapters[:2]:
        parts.append(f"## {ch.title}\n{ch.content[:1200]}\n")

    # 最后 1 章（取前 600 字）
    if len(chapters) > 2:
        last = chapters[-1]
        parts.append(f"## {last.title}\n{last.content[:600]}\n")

    # 每卷首章采样（取标题含"卷"或每 50 章取一章的前 400 字）
    for i, ch in enumerate(chapters):
        if "卷" in ch.title and "第" in ch.title:
            parts.append(f"## {ch.title}\n{ch.content[:400]}\n")
        elif i > 2 and i < len(chapters) - 1 and i % 50 == 0:
            parts.append(f"## {ch.title}\n{ch.content[:400]}\n")

    context = "\n".join(parts)
    if len(context) > max_chars:
        context = context[:max_chars] + "\n\n[... 文本已截断 ...]"
    return context


class SkeletonAnalyzer:
    """骨架层分析器：轻量全局框架提取"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        if not _OPENAI_OK:
            raise RuntimeError("openai 未安装，请运行: pip install openai==1.55.0")
        from src.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
        self.client = OpenAI(
            api_key=api_key or DEEPSEEK_API_KEY,
            base_url=base_url or DEEPSEEK_BASE_URL,
        )

    def analyze(self, chapters: List[Chapter], dims: List[str] | None = None) -> dict:
        """
        骨架层分析，返回 {dim_key: content} 字典。
        因上下文极小（<6000字），速度快、token 消耗低。
        """
        if dims is None:
            dims = list(SKELETON_DIMS.keys())

        context = build_skeleton_context(chapters)
        results: dict = {}

        for dim in dims:
            cfg = SKELETON_DIMS.get(dim)
            if not cfg:
                continue
            try:
                resp = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": "你是一位专业的网络小说分析专家，擅长从极少文本中提取框架结构。请基于已有信息输出，未确认处标注[推测]。请严格按要求的Markdown结构输出。"},
                        {"role": "user", "content": f"{cfg['prompt']}\n\n--- 小说骨架信息 ---\n\n{context}"},
                    ],
                    temperature=0.3,
                    max_tokens=4096,
                )
                results[dim] = resp.choices[0].message.content or ""
            except Exception as e:
                results[dim] = f"[骨架分析失败: {str(e)}]"

        return results

    def analyze_stream(self, chapters: List[Chapter], dims: List[str] | None = None):
        """流式版本，每完成一个维度 yield"""
        if dims is None:
            dims = list(SKELETON_DIMS.keys())

        context = build_skeleton_context(chapters)
        valid = [d for d in dims if d in SKELETON_DIMS]
        done = 0

        for dim in dims:
            cfg = SKELETON_DIMS.get(dim)
            if not cfg:
                continue
            try:
                resp = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": "你是一位专业的网络小说分析专家，擅长从极少文本中提取框架结构。请基于已有信息输出，未确认处标注[推测]。"},
                        {"role": "user", "content": f"{cfg['prompt']}\n\n--- 小说骨架信息 ---\n\n{context}"},
                    ],
                    temperature=0.3,
                    max_tokens=4096,
                )
                content = resp.choices[0].message.content or ""
            except Exception as e:
                content = f"[骨架分析失败: {str(e)}]"

            done += 1
            yield dim, cfg["label"], content, done, len(valid)
