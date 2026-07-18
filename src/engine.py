"""
三层递进提取管线 — 串联 chunker → skeleton → lexicon → meso → aggregator

粒度档位：
  skeleton  — 仅骨架层（~2次 AI 调用，快）
  standard  — 骨架 + 中观层逐块（~4 × N块 AI 调用）
  detailed  — 全量：骨架 + 中观 + 汇总加工 + 校验

用法：
  from src.engine import ExtractionPipeline
  pipeline = ExtractionPipeline(api_key="sk-...")
  for event in pipeline.run(chapters, granularity="detailed"):
      # SSE yield: {"stage": "...", "progress": 0.5, "label": "...", "data": ...}
"""

from dataclasses import dataclass
from typing import List, Dict, Generator, Callable, Optional

try:
    from openai import OpenAI
    _OPENAI_OK = True
except ImportError:
    OpenAI = None
    _OPENAI_OK = False

from src.config import DEEPSEEK_BASE_URL
from src.parser import Chapter
from src.chunker import SmartChunker, SmartBlock
from src.skeleton import SkeletonAnalyzer, SkeletonResult
from src.lexicon import Lexicon
from src.meso import MesoAnalyzer, MesoResult
from src.aggregator import Aggregator, AggregatedResult


GRANULARITY_LABELS = {
    "skeleton": "精简版 — 仅全局框架",
    "standard": "标准版 — 框架 + 主线 + 核心设定",
    "detailed": "精细化版 — 全量拆解，支线/配角/素材库全覆盖",
}


class ExtractionPipeline:
    """小说三层递进提取管线"""

    def __init__(self, api_key: str, base_url: str = None):
        if not _OPENAI_OK:
            raise RuntimeError("openai 未安装，请运行: pip install openai==1.55.0")
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url or DEEPSEEK_BASE_URL,
        )
        self._lexicon: Optional[Lexicon] = None

    def run(
        self,
        chapters: List[Chapter],
        granularity: str = "detailed",
        on_progress: Callable = None,
    ) -> Generator[dict, None, None]:
        """
        执行提取管线，逐阶段 yield 进度事件。

        Yields:
            {"stage": str, "label": str, "progress_pct": float, "data": ...}
        """

        # ── 阶段 1: 分块 ──
        yield {"stage": "chunking", "label": "智能分块中...", "progress_pct": 0.02}
        chunker = SmartChunker()
        blocks = chunker.chunk(chapters)
        yield {"stage": "chunking", "label": f"完成 → {len(blocks)} 个文本块",
               "progress_pct": 0.05, "data": {"block_count": len(blocks)}}

        if granularity == "skeleton":
            yield from self._run_skeleton(chapters, 0.05, 0.9)
            return

        # ── 阶段 2: 骨架层 ──
        yield from self._run_skeleton(chapters, 0.05, 0.15)

        self._lexicon = Lexicon()

        # ── 阶段 3: 中观层逐块 ──
        meso = MesoAnalyzer(self.client, self._lexicon)
        meso_results: List[MesoResult] = []
        block_count = len(blocks)

        for i, block in enumerate(blocks):
            base_pct = 0.15 + (i / block_count) * 0.55
            label = f"分析第{block.start_idx}-{block.end_idx}章... ({i+1}/{block_count})"
            yield {"stage": "meso", "label": label, "progress_pct": base_pct,
                   "data": {"block_index": i, "chapters": f"{block.start_idx}-{block.end_idx}"}}

            def task_callback(task_id: str, count: int):
                yield {"stage": "meso_task", "label": f"  {task_id}: {count}条",
                       "progress_pct": base_pct, "data": {"task": task_id, "extracted": count}}

            try:
                mr = meso.analyze_block(block, i, on_task_done=task_callback)
                meso_results.append(mr)
            except Exception as e:
                yield {"stage": "meso_error", "label": str(e), "progress_pct": base_pct}

        yield {"stage": "meso_done", "label": f"中观层完成 → {len(meso_results)} 块已处理",
               "progress_pct": 0.70, "data": {"lexicon_stats": self._lexicon.stats()}}

        if granularity == "standard":
            yield {"stage": "done", "label": "标准版完成",
                   "progress_pct": 1.0, "data": self._build_standard_output(meso_results)}
            return

        # ── 阶段 4: 汇总层 ──
        yield {"stage": "aggregation", "label": "汇总去重 + 伏笔关联 + 战力梯队...", "progress_pct": 0.72}
        aggr = Aggregator(self._lexicon)
        agg_result = aggr.aggregate(meso_results)

        yield {"stage": "aggregation_done", "label": "汇总完成",
               "progress_pct": 0.85,
               "data": {
                   "foreshadow_count": len(agg_result.foreshadow_links),
                   "tier_entries": len(agg_result.tier_list),
                   "material_categories": list(agg_result.material_library.keys()),
                   "validation_gaps": agg_result.validation_gaps,
               }}

        # ── 阶段 5: 输出 ──
        yield {"stage": "done", "label": "精细化版完成",
               "progress_pct": 1.0, "data": self._package_output(agg_result)}

    # ── 子阶段 ──

    def _run_skeleton(self, chapters, start_pct, end_pct):
        yield {"stage": "skeleton", "label": "提取全局骨架...", "progress_pct": start_pct}
        sk = SkeletonAnalyzer(self.client)
        sk_result = sk.analyze(chapters)
        mid = (start_pct + end_pct) / 2
        yield {"stage": "skeleton_done", "label": "骨架层完成",
               "progress_pct": mid,
               "data": {
                   "worldview": sk_result.worldview[:300],
                   "timeline": sk_result.timeline[:300],
                   "character_count": len(sk_result.characters),
               }}
        yield {"stage": "skeleton", "label": "骨架提取完成", "progress_pct": end_pct}

    def _build_standard_output(self, meso_results: List[MesoResult]) -> dict:
        timeline = []
        characters: Dict[str, dict] = {}
        for mr in meso_results:
            for ev in mr.plot_events:
                if ev.get("type") in ("主线", "主线推进"):
                    timeline.append(ev)
            for cu in mr.character_updates:
                name = cu.get("name", "")
                if name and name not in characters:
                    characters[name] = cu
        return {"timeline": timeline, "characters": list(characters.values()),
                "lexicon": self._lexicon.stats() if self._lexicon else {}}

    def _package_output(self, agg: AggregatedResult) -> dict:
        return {
            "foreshadow_links": [
                {"content": fl.content, "planted": fl.planted_chapter,
                 "resolved": fl.resolved_chapter, "status": fl.status}
                for fl in agg.foreshadow_links
            ],
            "tier_list": [
                {"name": t.name, "tier": t.tier, "category": t.category,
                 "evidence_count": len(t.evidence)}
                for t in agg.tier_list[:30]
            ],
            "character_count": len(agg.character_archives),
            "setting_categories": list(agg.settings_encyclopedia.keys()),
            "material_categories": list(agg.material_library.keys()),
            "validation_gaps": agg.validation_gaps[:10],
        }


__all__ = ["ExtractionPipeline", "GRANULARITY_LABELS"]
