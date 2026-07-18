"""
汇总引擎 — 收集所有中观层结果，跨块去重、关联、补全，输出结构化成品库。

功能：
1. 跨块人物/设定/剧情去重合并
2. 伏笔自动关联（埋下 ↔ 回收）
3. 战力梯队自动梳理
4. 漫剧素材库按情绪分类整理
5. 多轮校验：人物↔剧情↔设定 交叉核对
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict

from src.lexicon import Lexicon
from src.meso import MesoResult


@dataclass
class ForeshadowLink:
    content: str
    planted_chapter: int
    resolved_chapter: int = -1
    related_plot: str = ""
    status: str = "open"  # open | resolved

@dataclass
class TierEntry:
    name: str
    tier: int
    category: str  # character | monster
    evidence: List[str] = field(default_factory=list)
    upper_limit: str = ""
    battle_records: List[str] = field(default_factory=list)

@dataclass
class MaterialItem:
    category: str  # 场景/动作/战斗/名场面/对话/特效
    emotion: str   # 高燃/搞笑/虐心/悬疑/温情/史诗
    excerpt: str
    chapter: int
    characters: List[str] = field(default_factory=list)
    shot_suggestion: str = ""

@dataclass
class AggregatedResult:
    # 剧情库
    main_timeline: List[dict] = field(default_factory=list)
    subplots: List[dict] = field(default_factory=list)
    daily_fragments: List[dict] = field(default_factory=list)

    # 设定百科
    settings_encyclopedia: Dict[str, List[dict]] = field(default_factory=dict)

    # 人物档案库（去重合并后）
    character_archives: List[dict] = field(default_factory=list)

    # 伏笔关联
    foreshadow_links: List[ForeshadowLink] = field(default_factory=list)

    # 战力梯队
    tier_list: List[TierEntry] = field(default_factory=list)

    # 素材库
    material_library: Dict[str, List[MaterialItem]] = field(default_factory=dict)

    # 校验报告
    validation_gaps: List[str] = field(default_factory=list)


class Aggregator:
    """收集 MesoResult 列表 + Lexicon，产出 AggregatedResult"""

    def __init__(self, lexicon: Lexicon):
        self.lexicon = lexicon
        self._char_index: Dict[str, dict] = {}
        self._setting_index: Dict[str, dict] = {}
        self._foreshadows: List[ForeshadowLink] = []
        self._resolutions: Dict[str, List[Tuple[int, str]]] = defaultdict(list)
        self._tier_data: Dict[str, TierEntry] = {}

    # ── 主入口 ──

    def aggregate(self, meso_results: List[MesoResult]) -> AggregatedResult:
        result = AggregatedResult()

        for mr in meso_results:
            self._ingest_block(mr)

        result.plot_events = self._build_plot_events(meso_results)
        result.subplots = self._build_subplots(meso_results)
        result.daily_fragments = self._build_daily(meso_results)

        result.settings_encyclopedia = self.lexicon.export_categories()
        result.character_archives = list(self._char_index.values())

        self._link_foreshadows()
        result.foreshadow_links = self._foreshadows

        result.tier_list = self._build_tier_list()
        result.material_library = self._organize_materials(meso_results)

        result.validation_gaps = self._validate(meso_results)
        return result

    # ── 逐块摄入 ──

    def _ingest_block(self, mr: MesoResult):
        # 人物增量 → 去重合并
        for cu in mr.character_updates:
            name = cu.get("name", "")
            if not name:
                continue
            if name not in self._char_index:
                self._char_index[name] = {
                    "name": name,
                    "appearances": [],
                    "abilities": [],
                    "personality_moments": [],
                    "relationships": [],
                    "iconic_lines": [],
                    "growth": [],
                    "chapters_seen": set(),
                }
            rec = self._char_index[name]
            if cu.get("new_appearance"):
                rec["appearances"].append(cu["new_appearance"])
            if cu.get("new_ability"):
                rec["abilities"].append(cu["new_ability"])
            if cu.get("character_moment"):
                rec["personality_moments"].append(cu["character_moment"])
            if cu.get("relationship_change"):
                rec["relationships"].append(cu["relationship_change"])
            if cu.get("iconic_line"):
                rec["iconic_lines"].append(cu["iconic_line"])
            if cu.get("growth_point"):
                rec["growth"].append(cu["growth_point"])
            ch = cu.get("chapter", 0)
            if ch:
                rec["chapters_seen"].add(ch)

        # 伏笔收集
        for ev in mr.plot_events:
            if ev.get("foreshadowing") and ev.get("foreshadow_content"):
                self._foreshadows.append(ForeshadowLink(
                    content=ev["foreshadow_content"],
                    planted_chapter=self._parse_chapter(ev.get("chapter_range", "")),
                ))
            if ev.get("type") == "主线" and ev.get("name"):
                self._resolutions[ev["name"]].append(
                    (self._parse_chapter(ev.get("chapter_range", "")), ev.get("summary", ""))
                )

        # 战力数据
        for cu in mr.character_updates:
            name = cu.get("name", "")
            if not name:
                continue
            if name not in self._tier_data:
                self._tier_data[name] = TierEntry(name=name, tier=0, category="character")
            te = self._tier_data[name]
            if cu.get("new_ability"):
                te.evidence.append(cu["new_ability"])
            ch = cu.get("chapter", 0)
            if ch:
                te.battle_records.append(f"第{ch}章: {cu.get('character_moment', '')}")

    # ── 伏笔关联 ──

    def _link_foreshadows(self):
        """遍历伏笔列表，在全文中匹配回收内容"""
        for fl in self._foreshadows:
            keywords = set(fl.content[:6])
            for ev_name, occurrences in self._resolutions.items():
                if any(kw in ev_name for kw in keywords if len(kw) >= 2):
                    for chap, summary in occurrences:
                        if chap > fl.planted_chapter:
                            fl.resolved_chapter = chap
                            fl.related_plot = ev_name
                            fl.status = "resolved"
                            break
                if fl.status == "resolved":
                    break

    # ── 战力梯队 ──

    def _build_tier_list(self) -> List[TierEntry]:
        entries = sorted(
            self._tier_data.values(),
            key=lambda e: (len(e.evidence), len(e.battle_records)),
            reverse=True,
        )
        for i, e in enumerate(entries):
            if i < len(entries) * 0.1:
                e.tier = 1
            elif i < len(entries) * 0.3:
                e.tier = 2
            elif i < len(entries) * 0.6:
                e.tier = 3
            else:
                e.tier = 4
        return sorted(entries, key=lambda e: e.tier)

    # ── 素材库 ──

    def _organize_materials(self, results: List[MesoResult]) -> Dict[str, List[MaterialItem]]:
        by_emotion: Dict[str, List[MaterialItem]] = defaultdict(list)
        for mr in results:
            for ve in mr.visual_excerpts:
                item = MaterialItem(
                    category=ve.get("category", "其他"),
                    emotion=ve.get("emotion", "其他"),
                    excerpt=ve.get("excerpt", ""),
                    chapter=ve.get("chapter", 0),
                    characters=ve.get("characters", []),
                    shot_suggestion=ve.get("shot_suggestion", ""),
                )
                by_emotion[item.emotion].append(item)
                if item.emotion == "高燃":
                    by_emotion["🔥 高燃"].append(item)
        return dict(by_emotion)

    # ── 剧情分类 ──

    def _build_plot_events(self, results: List[MesoResult]) -> List[dict]:
        timeline = []
        for mr in sorted(results, key=lambda r: r.block_index):
            for ev in mr.plot_events:
                if ev.get("type") in ("主线", "主线推进"):
                    timeline.append(ev)
        return timeline

    def _build_subplots(self, results: List[MesoResult]) -> List[dict]:
        return [ev for mr in results for ev in mr.plot_events
                if ev.get("type") in ("支线", "支线单元")]

    def _build_daily(self, results: List[MesoResult]) -> List[dict]:
        return [ev for mr in results for ev in mr.plot_events
                if ev.get("type") in ("日常", "日常过渡")]

    # ── 校验 ──

    def _validate(self, results: List[MesoResult]) -> List[str]:
        gaps = []

        # 1. 剧情里出现的人物是否都在人物档案中
        plot_names: Set[str] = set()
        for mr in results:
            for ev in mr.plot_events:
                for c in ev.get("characters", []):
                    plot_names.add(c)
        for name in plot_names:
            if name not in self._char_index:
                gaps.append(f"⚠ 人物缺失：'{name}' 出现在剧情中但未建档")

        # 2. 词典逻辑
        gaps.extend(self.lexicon.find_gaps([]))

        # 3. 伏笔未回收
        unresolved = [fl for fl in self._foreshadows if fl.status == "open"]
        if unresolved:
            gaps.append(f"🔍 {len(unresolved)} 条伏笔未找到回收: " +
                        ", ".join(fl.content[:20] + "..." for fl in unresolved[:5]))

        return gaps

    @staticmethod
    def _parse_chapter(chapter_range: str) -> int:
        import re
        m = re.search(r"(\d+)", chapter_range)
        return int(m.group(1)) if m else 0


__all__ = ["Aggregator", "AggregatedResult", "ForeshadowLink", "TierEntry", "MaterialItem"]
