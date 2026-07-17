# 小说分析提取器 实现计划

> **面向 AI 代理：** 使用 `executing-plans` 逐任务实现。
> 步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 构建一个本地 Web 工具，用户选择小说文件（txt/epub/docx），自动提取并分析世界观设定、人物性格转变等信息。

**架构：** 两阶段分析 — Phase1 按章节分块后逐章调用 DeepSeek 提取人物/设定/情节摘要；Phase2 将所有章节摘要汇总后调用 DeepSeek 做跨章节人物弧光和世界观全景分析。Flask 后端 + 原生 HTML/CSS/JS 前端。

**技术栈：** Flask、openai SDK（DeepSeek 兼容）、ChromaDB、EbookLib、python-docx、BeautifulSoup4

---

## 任务

### 任务 1：补充依赖

- [ ] 修改 `pyproject.toml`：dependencies 追加 ebooklib、python-docx、beautifulsoup4
- [ ] 运行 `pip install -e ".[dev]"` 安装所有依赖

**目标：** 安装文件解析所需的三个新库。

**实现：** 在 `pyproject.toml` 的 `dependencies` 列表中追加三行：
```toml
    "ebooklib>=0.18",
    "python-docx>=1.1",
    "beautifulsoup4>=4.12",
```

**验证：**
```bash
python -c "import ebooklib; import docx; import bs4; print('OK')"
```

---

### 任务 2：文件解析器

- [ ] 创建 `src/parser.py`：实现 `parse(file_path: str, file_type: str) -> list[dict]`

**目标：** 将 txt/epub/docx 三种格式统一解析为章节列表，每章为 `{index, title, content}`。

**实现：**

```python
"""文件解析器：txt / epub / docx -> 章节列表"""
import re
from pathlib import Path
from bs4 import BeautifulSoup

def parse(file_path: str, file_type: str) -> list[dict]:
    file_type = file_type.lower().lstrip(".")
    if file_type == "txt":
        return _parse_txt(file_path)
    elif file_type == "epub":
        return _parse_epub(file_path)
    elif file_type == "docx":
        return _parse_docx(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {file_type}")

# ---- 章节切分 ----

_CHAPTER_PATTERN = re.compile(
    r"^\s*(第[零一二三四五六七八九十百千\d]+[章回节卷部篇]|Chapter\s+\d+|CHAPTER\s+\d+|"
    r"[第序终]章|楔子|尾声|番外|后记|附录|引子|序章)",
    re.IGNORECASE
)

def _split_by_chapters(text: str) -> list[dict]:
    """按章节标题正则切分文本，无标记时按 5000 字固定切分。"""
    lines = text.split("\n")
    chapters = []
    current_title = "序言"
    current_lines = []
    idx = 0

    for line in lines:
        stripped = line.strip()
        if _CHAPTER_PATTERN.match(stripped):
            if current_lines:
                chapters.append({
                    "index": idx,
                    "title": current_title,
                    "content": "\n".join(current_lines).strip()
                })
                idx += 1
            current_title = stripped
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        chapters.append({
            "index": idx,
            "title": current_title,
            "content": "\n".join(current_lines).strip()
        })

    if not chapters:
        chapters.append({"index": 0, "title": "全文", "content": text})

    # 如果单章超过 15000 字，进一步切分
    result = []
    for ch in chapters:
        if len(ch["content"]) > 15000:
            sub = _fixed_split(ch)
            result.extend(sub)
        else:
            result.append(ch)

    # 重新编号
    for i, ch in enumerate(result):
        ch["index"] = i

    return result


def _fixed_split(chapter: dict, chunk_size: int = 5000) -> list[dict]:
    """固定长度切分，在换行符处断开。"""
    text = chapter["content"]
    if len(text) <= chunk_size:
        return [chapter]

    chunks = []
    pos = 0
    idx = 0
    while pos < len(text):
        end = pos + chunk_size
        if end >= len(text):
            chunks.append({"index": idx, "title": f"{chapter['title']}({idx+1})", "content": text[pos:]})
            break
        # 在换行处断开
        nl = text.rfind("\n", pos, end)
        if nl > pos + chunk_size // 2:
            end = nl + 1
        chunks.append({"index": idx, "title": f"{chapter['title']}({idx+1})", "content": text[pos:end]})
        pos = end
        idx += 1
    return chunks


# ---- 各格式解析 ----

def _parse_txt(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    return _split_by_chapters(text)


def _parse_epub(path: str) -> list[dict]:
    import ebooklib
    from ebooklib import epub

    book = epub.read_epub(path)
    chapters = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        # 提取章节标题
        title_tag = soup.find(["h1", "h2", "h3", "h4"])
        title = title_tag.get_text(strip=True) if title_tag else f"章节{len(chapters)+1}"
        # 提取正文
        text = soup.get_text(separator="\n", strip=True)
        chapters.append({
            "index": len(chapters),
            "title": title,
            "content": text
        })

    if not chapters:
        raise ValueError("epub 文件中未找到可读取的文本内容")
    return chapters


def _parse_docx(path: str) -> list[dict]:
    from docx import Document

    doc = Document(path)
    chapters = []
    current_title = "序言"
    current_paras = []

    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        # 判断是否为章节标题：加粗 且 较短（< 50 字）
        is_bold = any(run.bold for run in p.runs if run.bold)
        if is_bold and len(text) < 50:
            if current_paras:
                chapters.append({
                    "index": len(chapters),
                    "title": current_title,
                    "content": "\n".join(current_paras)
                })
            current_title = text
            current_paras = []
        else:
            current_paras.append(text)

    if current_paras:
        chapters.append({
            "index": len(chapters),
            "title": current_title,
            "content": "\n".join(current_paras)
        })

    if not chapters:
        full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return _split_by_chapters(full_text)

    return chapters
```

**验证：**
```bash
python -c "from src.parser import parse; print(parse.__name__)"
```

---

### 任务 3：提示词模板

- [ ] 创建 `src/prompts.py`：Phase1 逐章提取 + Phase2 跨章汇总的提示词模板

**目标：** 集中管理 DeepSeek 提示词，确保输出 JSON 格式可解析。

**实现：**

```python
"""DeepSeek 提示词模板"""

PHASE1_SYSTEM = """你是一位专业的小说分析助手。你的任务是针对给定的小说章节，提取以下结构化信息。

请严格按 JSON 格式输出，不要添加任何解释、评论或 markdown 代码块标记。

输出 JSON 结构：
{
  "characters": [
    {
      "name": "人物名称",
      "aliases": ["别名1", "别名2"],
      "traits": ["性格特征1", "性格特征2"],
      "actions": ["关键行为1"],
      "dialog_style": "对话风格描述",
      "relationships": [{"target": "其他人物", "type": "关系类型"}]
    }
  ],
  "world_elements": [
    {
      "category": "地理/势力/规则/历史/物品/其他",
      "name": "设定名称",
      "description": "设定描述",
      "evidence": "原文依据（简短引用）"
    }
  ],
  "plot_points": [
    {
      "type": "冲突/转折/揭示/推进",
      "summary": "情节摘要",
      "involved_characters": ["涉及人物"]
    }
  ]
}"""

PHASE1_USER = "请分析以下小说章节（第{chapter_index}章：{chapter_title}）：\n\n{chapter_content}"


PHASE2_SYSTEM = """你是一位专业的小说分析助手。你的任务是基于各章节的分析摘要，生成整部小说的全局分析。

请严格按 JSON 格式输出，不要添加任何解释、评论或 markdown 代码块标记。

输出 JSON 结构：
{
  "characters": [
    {
      "name": "人物名称",
      "arc": {
        "initial_state": "初始性格/状态",
        "key_events": [{"event": "关键事件", "chapter": "章节", "change": "引发的转变"}],
        "final_state": "最终性格/状态"
      },
      "core_traits": ["核心性格特征"],
      "role": "主角/反派/配角/导师/..."
    }
  ],
  "world": {
    "geography": [{"name": "地点", "description": "描述"}],
    "factions": [{"name": "势力/组织", "members": ["成员"], "goal": "目标"}],
    "rules": [{"name": "规则/设定", "description": "描述"}],
    "history": [{"event": "历史事件", "era": "时期"}]
  },
  "narrative": {
    "main_themes": ["主题1", "主题2"],
    "timeline": [{"chapter_range": "章节范围", "summary": "主线摘要"}],
    "style": "写作风格描述"
  }
}"""

PHASE2_USER = "以下是小说所有章节的分析摘要。请基于这些摘要生成整部小说的全局分析：\n\n{all_summaries}"
```

**验证：**
```bash
python -c "from src.prompts import PHASE1_SYSTEM, PHASE2_SYSTEM; print('OK')"
```

---

### 任务 4：AI 分析器

- [ ] 创建 `src/analyzer.py`：实现 Phase1 逐章分析 + Phase2 跨章汇总

**目标：** 核心分析逻辑。Phase1 逐章调用 DeepSeek，Phase2 汇总后调用 DeepSeek。

**实现：**

```python
"""AI 分析器：两阶段 DeepSeek 调用"""
import json
import time
from openai import OpenAI
from src.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
from src.prompts import (
    PHASE1_SYSTEM, PHASE1_USER,
    PHASE2_SYSTEM, PHASE2_USER,
)


def _create_client() -> OpenAI:
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def analyze(chapters: list[dict], progress_callback=None) -> dict:
    """
    两阶段分析入口。
    chapters: [{"index": int, "title": str, "content": str}, ...]
    progress_callback: (phase: str, current: int, total: int) -> None
    返回完整分析结果 dict。
    """
    client = _create_client()
    total = len(chapters)

    # Phase 1：逐章分析
    phase1_results = []
    for i, ch in enumerate(chapters):
        if progress_callback:
            progress_callback("phase1", i + 1, total)
        result = _call_phase1(client, ch)
        phase1_results.append(result)
        time.sleep(0.5)  # 温和限速

    # Phase 2：跨章汇总
    if progress_callback:
        progress_callback("phase2", 1, 1)
    all_summaries = _compile_summaries(phase1_results, chapters)
    phase2_result = _call_phase2(client, all_summaries)

    # 合并结果
    return {
        "characters": phase2_result.get("characters", []),
        "world": phase2_result.get("world", {}),
        "narrative": phase2_result.get("narrative", {}),
        "chapter_analyses": phase1_results,
        "chapter_count": len(chapters),
    }


def _call_phase1(client: OpenAI, chapter: dict, max_retries=3) -> dict:
    user_msg = PHASE1_USER.format(
        chapter_index=chapter["index"],
        chapter_title=chapter["title"],
        chapter_content=chapter["content"]
    )
    return _chat_json(client, PHASE1_SYSTEM, user_msg, max_retries)


def _call_phase2(client: OpenAI, summaries: str, max_retries=3) -> dict:
    user_msg = PHASE2_USER.format(all_summaries=summaries)
    return _chat_json(client, PHASE2_SYSTEM, user_msg, max_retries)


def _chat_json(client: OpenAI, system: str, user: str, max_retries: int) -> dict:
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
                max_tokens=4096,
            )
            raw = resp.choices[0].message.content
            return _extract_json(raw)
        except Exception as e:
            if attempt == max_retries - 1:
                return {"error": str(e), "raw": raw if 'raw' in dir() else ""}
            time.sleep(1)
    return {"error": "max_retries_exceeded"}


def _extract_json(raw: str) -> dict:
    """从 AI 回复中提取 JSON，处理可能的 markdown 代码块包裹。"""
    raw = raw.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    return json.loads(raw.strip())


def _compile_summaries(phase1_results: list[dict], chapters: list[dict]) -> str:
    """将 Phase1 结果编译为 Phase2 的输入摘要文本。"""
    parts = []
    for i, (result, chapter) in enumerate(zip(phase1_results, chapters)):
        parts.append(f"--- 第{chapter['index']}章：{chapter['title']} ---")
        if "error" in result:
            parts.append(f"[分析失败: {result['error']}]")
            continue
        parts.append(json.dumps(result, ensure_ascii=False, indent=2))
    return "\n".join(parts)
```

**验证：**
```bash
python -c "from src.analyzer import analyze; print('OK')"
```

---

### 任务 5：存储层

- [ ] 创建 `src/store.py`：ChromaDB 封装，存储章节分析结果

**目标：** 将每章分析结果持久化到 ChromaDB，支持按人物/设定关键词检索。

**实现：**

```python
"""ChromaDB 存储层"""
import json
import chromadb
from chromadb.config import Settings
from src.config import CHROMA_PERSIST_DIR


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def store_analysis(result: dict, source_filename: str) -> str:
    """
    存储分析结果到 ChromaDB。
    返回 collection name。
    """
    client = _get_client()
    safe_name = source_filename.rsplit(".", 1)[0].replace(" ", "_")
    collection_name = f"novel_{safe_name}"

    # 删除同名旧 collection
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(collection_name)

    # 存储每章分析结果
    chapter_analyses = result.get("chapter_analyses", [])
    for i, ch in enumerate(chapter_analyses):
        doc = json.dumps(ch, ensure_ascii=False)
        metadata = {"chapter_index": i, "source": source_filename}
        collection.add(
            ids=[f"ch_{i}"],
            documents=[doc],
            metadatas=[metadata],
        )

    # 存储全局分析结果
    global_summary = {
        "characters": result.get("characters", []),
        "world": result.get("world", {}),
        "narrative": result.get("narrative", {}),
    }
    collection.add(
        ids=["_global_"],
        documents=[json.dumps(global_summary, ensure_ascii=False)],
        metadatas=[{"chapter_index": -1, "source": source_filename}],
    )

    return collection_name


def get_stored_analyses() -> list[dict]:
    """列出所有已存储的分析。"""
    client = _get_client()
    collections = client.list_collections()
    results = []
    for col in collections:
        try:
            data = col.get(ids=["_global_"])
            if data and data["documents"]:
                results.append({
                    "name": col.name,
                    "summary": json.loads(data["documents"][0]),
                })
        except Exception:
            continue
    return results


def get_analysis(collection_name: str) -> dict | None:
    """获取指定 collection 的完整分析结果。"""
    client = _get_client()
    try:
        col = client.get_collection(collection_name)
        all_data = col.get()
        if not all_data or not all_data["ids"]:
            return None
        chapters = []
        global_summary = {}
        for id_, doc in zip(all_data["ids"], all_data["documents"]):
            if id_ == "_global_":
                global_summary = json.loads(doc)
            else:
                chapters.append(json.loads(doc))
        return {
            "chapters": sorted(chapters, key=lambda x: x.get("index", 0) if isinstance(x, dict) else 0),
            **global_summary,
        }
    except Exception:
        return None
```

**验证：**
```bash
python -c "from src.store import get_stored_analyses; print('OK')"
```

---

### 任务 6：Flask 应用入口

- [ ] 创建 `src/app.py`：Flask 应用，路由 + API

**目标：** 提供文件上传、分析触发、进度轮询、结果获取的 API。

**路由设计：**

| 路由 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 前端主页 |
| `/api/upload` | POST | 上传文件，返回文件 ID |
| `/api/analyze` | POST | 触发分析，返回任务 ID |
| `/api/progress/<task_id>` | GET | 轮询分析进度 |
| `/api/result/<task_id>` | GET | 获取分析结果 |
| `/api/history` | GET | 获取历史分析列表 |

**实现：**

```python
"""Flask 应用入口"""
import os
import uuid
import threading
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from src.config import UPLOAD_DIR, OUTPUT_DIR
from src.parser import parse
from src.analyzer import analyze
from src.store import store_analysis, get_stored_analyses, get_analysis

app = Flask(__name__, template_folder="templates", static_folder="static")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 任务状态存储（内存）
_tasks: dict[str, dict] = {}


@app.route("/")
def index():
    from flask import render_template
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "未选择文件"}), 400
    filename = secure_filename(f.filename)
    filepath = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}_{filename}")
    f.save(filepath)
    file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return jsonify({
        "file_id": os.path.basename(filepath),
        "filename": filename,
        "file_type": file_type,
    })


@app.route("/api/analyze", methods=["POST"])
def start_analysis():
    data = request.get_json()
    file_id = data.get("file_id")
    file_type = data.get("file_type", "txt")
    filename = data.get("filename", "unknown")

    if not file_id:
        return jsonify({"error": "缺少 file_id"}), 400

    filepath = os.path.join(UPLOAD_DIR, file_id)
    if not os.path.exists(filepath):
        return jsonify({"error": "文件不存在"}), 404

    task_id = uuid.uuid4().hex[:12]
    _tasks[task_id] = {
        "status": "parsing",
        "phase": "",
        "current": 0,
        "total": 0,
        "result": None,
        "error": None,
    }

    def _run():
        try:
            _tasks[task_id]["status"] = "parsing"
            chapters = parse(filepath, file_type)
            total = len(chapters)

            def progress(phase, cur, tot):
                _tasks[task_id]["phase"] = phase
                _tasks[task_id]["current"] = cur
                _tasks[task_id]["total"] = tot
                if phase == "phase1":
                    _tasks[task_id]["status"] = "analyzing"

            _tasks[task_id]["total"] = total
            result = analyze(chapters, progress_callback=progress)

            _tasks[task_id]["status"] = "storing"
            store_analysis(result, filename)

            _tasks[task_id]["status"] = "done"
            _tasks[task_id]["result"] = {
                "characters": result.get("characters", []),
                "world": result.get("world", {}),
                "narrative": result.get("narrative", {}),
                "chapter_count": result.get("chapter_count", 0),
            }
        except Exception as e:
            _tasks[task_id]["status"] = "error"
            _tasks[task_id]["error"] = str(e)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/api/progress/<task_id>")
def progress(task_id):
    task = _tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify({
        "status": task["status"],
        "phase": task["phase"],
        "current": task["current"],
        "total": task["total"],
        "error": task.get("error"),
    })


@app.route("/api/result/<task_id>")
def result(task_id):
    task = _tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    if task["status"] != "done":
        return jsonify({"error": "分析尚未完成", "status": task["status"]}), 400
    return jsonify(task["result"])


@app.route("/api/history")
def history():
    return jsonify(get_stored_analyses())


@app.route("/api/history/<name>")
def history_detail(name):
    data = get_analysis(name)
    if data is None:
        return jsonify({"error": "记录不存在"}), 404
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8889, debug=True)
```

**验证：**
```bash
python -c "from src.app import app; print('Flask app OK')"
```

---

### 任务 7：前端页面

- [ ] 创建 `src/templates/index.html` — 主页面结构
- [ ] 创建 `src/static/style.css` — 样式
- [ ] 创建 `src/static/app.js` — 交互逻辑

**目标：** 单页应用，文件选择 + 分析进度 + 结果展示三个区域。

**index.html 结构：**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>小说分析提取器</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div id="app">
    <!-- 上传区 -->
    <section class="panel upload-panel">
      <h1>📖 小说分析提取器</h1>
      <p class="desc">选择一本小说文件，AI 自动提取世界观设定与人物性格转变</p>
      <div class="upload-zone" id="uploadZone">
        <input type="file" id="fileInput" accept=".txt,.epub,.docx" hidden>
        <div class="upload-hint">点击选择文件 或 拖拽到此处<br><small>支持 .txt / .epub / .docx</small></div>
      </div>
      <div id="fileInfo" class="file-info hidden">
        <span id="fileName"></span>
        <button id="analyzeBtn">开始分析</button>
      </div>
    </section>

    <!-- 进度区 -->
    <section class="panel progress-panel hidden" id="progressPanel">
      <div id="progressText"></div>
      <div class="progress-bar"><div id="progressFill"></div></div>
    </section>

    <!-- 结果区 -->
    <section class="panel result-panel hidden" id="resultPanel">
      <div class="tabs" id="tabs">
        <button class="tab active" data-tab="characters">👤 人物弧光</button>
        <button class="tab" data-tab="world">🌍 世界观</button>
        <button class="tab" data-tab="narrative">📜 主线梳理</button>
        <button class="tab" data-tab="raw">📋 原始数据</button>
      </div>
      <div class="tab-content" id="tabContent"></div>
    </section>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>
```

**app.js 核心逻辑：**
- 文件选择（点击 + 拖拽）
- `/api/upload` 上传文件
- `/api/analyze` 触发分析，轮询 `/api/progress/<task_id>`
- `/api/result/<task_id>` 获取结果并渲染
- Tab 切换逻辑

**验证：**
```bash
python -c "import os; assert os.path.exists('src/templates/index.html'); assert os.path.exists('src/static/style.css'); assert os.path.exists('src/static/app.js')"
```

---

### 任务 8：端到端验证

- [ ] 创建测试用 txt 文件（简短小说片段）
- [ ] 使用测试文件跑通完整流程
- [ ] 确认 Flask 服务正常启动，前端页面可访问

**目标：** 确保整个链路可用。

**验证：**
```bash
# 启动服务（后台）
python -m src.app &
# 等待 3 秒后 curl 测试
sleep 3
curl -s http://localhost:8889/ | head -5
curl -s http://localhost:8889/api/history
```

---

## 自检

1. **规格覆盖**：文件解析（任务2）→ AI分析（任务4）→ 结果展示（任务7）→ 持久化（任务5），完整覆盖 spec 中的数据流
2. **占位符扫描**：无 TODO/TBD/待定
3. **类型一致性**：`Chapter = {index, title, content}` 在各模块间一致；`task_id` 统一为 12 位 hex
4. **调研背书**：Greenfield 项目，无删除/修改现有函数操作，config.py 仅扩展不破坏
5. **指标选择**：AI 分析有效性以 JSON 解析成功率为判据（非 token 数）
