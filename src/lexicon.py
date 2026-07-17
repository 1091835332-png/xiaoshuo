"""
词典管理器 — 三层递进提取的全局索引层。
维护全局设定/人物/地名词典，支持增量更新、引导校验和多轮补全。
按用户方案中的"词典引导法"实现。
"""
import json
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple
from pathlib import Path


@dataclass
class TermEntry:
    name: str
    category: str   # "character" | "setting" | "location" | "item" | "ability"
    first_chapter: int = 0
    last_chapter: int = 0
    description: str = ""
    attributes: dict = field(default_factory=dict)
    seen_in_blocks: Set[int] = field(default_factory=set)


class Lexicon:
    """全局词典：管理所有已识别的设定、人物、地名词条"""

    def __init__(self, save_path: Optional[Path] = None):
        self._entries: Dict[str, TermEntry] = {}
        self._name_index: Dict[str, str] = {}
        self._processed_blocks: Set[int] = set()
        self._save_path = save_path

    # ── CRUD ──

    def add_or_update(self, name: str, category: str, chapter: int,
                      description: str = "", attributes: dict = None,
                      block_index: int = -1) -> TermEntry:
        key = f"{category}:{name}"
        if key in self._entries:
            entry = self._entries[key]
            if description and len(description) > len(entry.description):
                entry.description = description
            if attributes:
                entry.attributes.update(attributes)
            entry.last_chapter = max(entry.last_chapter, chapter)
            if block_index >= 0:
                entry.seen_in_blocks.add(block_index)
        else:
            entry = TermEntry(
                name=name, category=category,
                first_chapter=chapter, last_chapter=chapter,
                description=description or name,
                attributes=attributes or {},
            )
            if block_index >= 0:
                entry.seen_in_blocks.add(block_index)
            self._entries[key] = entry
            self._name_index[name] = key
        return entry

    def get(self, name: str, category: str = None) -> Optional[TermEntry]:
        if category:
            return self._entries.get(f"{category}:{name}")
        for cat in ("character", "setting", "location", "item", "ability"):
            e = self._entries.get(f"{cat}:{name}")
            if e:
                return e
        return None

    def find(self, keyword: str) -> List[TermEntry]:
        results = []
        kw = keyword.lower()
        for entry in self._entries.values():
            if kw in entry.name.lower() or kw in entry.description.lower():
                results.append(entry)
        return results

    # ── 词典引导 ──

    def build_prompt_guide(self, block_text: str) -> Dict[str, List[TermEntry]]:
        """扫描文本块，找出其中出现（或可能出现）的已知词条"""
        guided: Dict[str, List[TermEntry]] = {
            "definitely_present": [],
            "possibly_present": [],
        }
        for entry in self._entries.values():
            if entry.name in block_text:
                guided["definitely_present"].append(entry)
            elif any(token in block_text for token in entry.name[:2]):
                guided["possibly_present"].append(entry)
        return guided

    def format_checklist(self, block_text: str) -> str:
        guide = self.build_prompt_guide(block_text)
        lines = ["【强制检查清单】本段文本中可能涉及以下已知词条，请逐一核实是否有新信息："]
        if guide["definitely_present"]:
            lines.append("\n✅ 已确认出现：")
            for e in guide["definitely_present"][:20]:
                lines.append(f"  [{e.category}] {e.name}：{e.description[:60]}...")
        if guide["possibly_present"]:
            lines.append("\n🔍 可能相关：")
            for e in guide["possibly_present"][:10]:
                lines.append(f"  [{e.category}] {e.name}")
        return "\n".join(lines)

    # ── 校验 ──

    def find_gaps(self, all_chapter_indices: List[int]) -> List[str]:
        gaps = []
        for entry in self._entries.values():
            if entry.category == "character" and entry.last_chapter - entry.first_chapter > 50:
                gaps.append(
                    f"[{entry.category}] {entry.name}："
                    f"首现第{entry.first_chapter}章，末现第{entry.last_chapter}章，"
                    f"中间跨度{entry.last_chapter - entry.first_chapter}章，建议核对是否有剧情遗漏"
                )
            if not entry.description or len(entry.description) < 10:
                gaps.append(f"[{entry.category}] {entry.name}：信息不足，仅'{entry.description}'")
        return gaps

    def mark_block_done(self, block_index: int):
        self._processed_blocks.add(block_index)

    # ── 导出 ──

    def to_dict(self) -> dict:
        return {
            name: {
                "category": e.category,
                "first_chapter": e.first_chapter,
                "last_chapter": e.last_chapter,
                "description": e.description,
                "attributes": e.attributes,
                "seen_in_blocks": sorted(e.seen_in_blocks),
            }
            for name, e in sorted(self._entries.items())
        }

    def export_categories(self) -> dict:
        """按类别分组导出"""
        cats: dict = {}
        for entry in self._entries.values():
            cats.setdefault(entry.category, []).append({
                "name": entry.name,
                "description": entry.description,
                "first_chapter": entry.first_chapter,
                "last_chapter": entry.last_chapter,
                "attributes": entry.attributes,
            })
        return cats

    def stats(self) -> dict:
        cats = {}
        for e in self._entries.values():
            cats[e.category] = cats.get(e.category, 0) + 1
        return {"total_terms": len(self._entries), "by_category": cats,
                "blocks_processed": len(self._processed_blocks)}

    def save(self):
        if self._save_path:
            self._save_path.write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

    @classmethod
    def load(cls, path: Path) -> "Lexicon":
        lex = cls(save_path=path)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            for key, d in data.items():
                cat, _, name = key.partition(":")
                lex.add_or_update(name, cat, d["first_chapter"],
                                  d.get("description", ""), d.get("attributes", {}))
        return lex
