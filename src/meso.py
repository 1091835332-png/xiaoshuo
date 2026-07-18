"""
中观层分析引擎 — 每块4个并行AI任务（剧情/设定/人物/素材摘抄）。

每个文本块同时跑4个独立AI任务，各司其职：
  任务1: 剧情节点识别（主线/支线/日常/设定补充分类）
  任务2: 设定增量更新（能力招式、器物道具、材料药剂、灾祸怪物、地名场景）
  任务3: 人物信息增量（外貌、新能力、性格表现、关系变化、名场面台词）
  任务4: 可视化素材摘抄（原文照搬场景描写、动作特写、战斗过程、经典对话）
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
from typing import List, Dict, Optional, Callable

from src.chunker import SmartBlock
from src.lexicon import Lexicon


@dataclass
class MesoResult:
    block_index: int
    plot_events: List[dict] = field(default_factory=list)
    new_settings: List[dict] = field(default_factory=list)
    character_updates: List[dict] = field(default_factory=list)
    visual_excerpts: List[dict] = field(default_factory=list)


MESO_PROMPTS = {
    "plot": """你是小说剧情分析专家。严格区分四类事件：
【主线推进】推动核心故事发展的关键事件
【支线单元】独立副本/配角剧情/单元故事
【日常过渡】过渡性日常描写、氛围铺垫
【设定补充】主要用来展现世界观或设定的段落
每个事件输出JSON：{"type":"主线/支线/日常/设定","name":"事件名","characters":["人物"],"location":"地点","summary":"50字概括","chapter_range":"第X-Y章","foreshadowing":false}""",

    "setting": """你是小说设定拆解专家。提取本段所有新增设定：
【能力招式】【器物道具】【材料药剂】【灾祸怪物】【地名场景】【制度规则】
每个词条输出JSON：{"category":"类别","name":"名称","appearance":"外观/效果原文40字","first_chapter":数字,"related_characters":["人物"]}""",

    "character": """你是人物档案专家。提取本段所有人物的增量信息：
外貌变化、新能力展现、性格表现、关系变化、名场面台词(原文照搬)、成长转折点
输出JSON：{"name":"人物名","new_appearance":"","new_ability":"","character_moment":"","relationship_change":"","iconic_line":"","growth_point":"","chapter":数字}""",

    "visual": """你是漫剧分镜素材采集员。从本段原文摘抄适合分镜的片段。
禁止概括，必须原文照搬。标注章节号和情绪分类。
【场景环境】【动作特写】【战斗攻防】【情绪名场面】【经典对话】【特效画面】
输出JSON：{"category":"类别","emotion":"高燃/搞笑/虐心/悬疑/温情/史诗","excerpt":"原文100-300字","chapter":数字,"characters":["人物"],"shot_suggestion":"镜头建议"}""",
}

MESO_SYSTEM = "你是专业的小说分析助手，输出严格按JSON格式。只基于给定文本提取，不编造文中不存在的信息。"


class MesoAnalyzer:
    """每块文本执行4个并行AI任务"""

    def __init__(self, client, lexicon: Lexicon):
        self.client = client
        self.lexicon = lexicon

    def analyze_block(self, block: SmartBlock, block_index: int,
                      on_task_done: Callable = None) -> MesoResult:
        result = MesoResult(block_index=block_index)
        checklist = self.lexicon.format_checklist(block.content[:3000])
        header = f"[{block.title}]"

        tasks = [
            ("plot", MESO_PROMPTS["plot"], "plot_events"),
            ("setting", MESO_PROMPTS["setting"], "new_settings"),
            ("character", MESO_PROMPTS["character"], "character_updates"),
            ("visual", MESO_PROMPTS["visual"], "visual_excerpts"),
        ]

        for task_id, prompt, attr in tasks:
            try:
                user_msg = f"{prompt}\n\n{checklist}\n\n{header}\n\n--- 文本 ---\n\n{block.content}"
                resp = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": MESO_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.2,
                    max_tokens=4096,
                )
                raw = resp.choices[0].message.content or ""
                parsed = self._parse_json_list(raw)
                setattr(result, attr, parsed)
            except Exception as e:
                setattr(result, attr, [{"error": str(e)}])

            if on_task_done:
                on_task_done(task_id, len(getattr(result, attr)))

        self.lexicon.mark_block_done(block_index)
        return result

    @staticmethod
    def _parse_json_list(raw: str) -> List[dict]:
        import json as _json
        import re
        items = []
        for m in re.finditer(r"\{[^}]+\}", raw, re.DOTALL):
            try:
                items.append(_json.loads(m.group()))
            except _json.JSONDecodeError:
                pass
        if not items and raw.strip():
            items = [{"raw": raw[:500]}]
        return items


__all__ = ["MesoAnalyzer", "MesoResult", "MESO_PROMPTS"]
