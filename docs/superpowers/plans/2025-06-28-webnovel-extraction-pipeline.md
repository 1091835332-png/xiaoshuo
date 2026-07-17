# 网文信息提取流水线 — 实施计划

> **面向 AI 代理：** 使用 `executing-plans` 逐任务实现。
> 步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 构建一个 Web 应用，上传网文 TXT 文件 → 选择提取维度（角色/世界观/场景/剧情/道具）→ DeepSeek 驱动提取 → 输出结构化 Markdown 档案。

**架构：** Flask Web 后端 + ChromaDB 向量索引 + DeepSeek API（OpenAI 兼容协议）。每个提取维度封装为独立 Skill，通过注册表按需加载。分块采用章节边界感知策略，每条提取结果标注章节范围和原文证据。

**技术栈：** Python 3.15, Flask, ChromaDB, OpenAI SDK (DeepSeek), tiktoken, Jinja2 + HTMX

---

## 项目结构

```
E:\新建文件夹 (2)\
├── pyproject.toml
├── .env.example
├── src/
│   ├── __init__.py
│   ├── app.py                    # Flask 入口
│   ├── config.py                 # 配置（读 .env）
│   ├── pipeline.py               # 流水线编排
│   ├── preprocess/
│   │   ├── __init__.py
│   │   ├── chapter_splitter.py   # 章节识别+分割
│   │   └── chunker.py            # 章节边界感知分块
│   ├── index/
│   │   ├── __init__.py
│   │   ├── embedder.py           # DeepSeek 向量嵌入
│   │   └── store.py              # ChromaDB 封装
│   ├── extract/
│   │   ├── __init__.py
│   │   ├── base.py               # 基类：LLM 调用 + 引用校验
│   │   ├── character.py          # 角色提取 skill
│   │   ├── worldbuilding.py      # 世界观提取 skill
│   │   ├── scene.py              # 场景提取 skill
│   │   ├── plot.py               # 剧情提取 skill
│   │   └── item.py               # 道具提取 skill
│   ├── merge/
│   │   ├── __init__.py
│   │   └── dedup.py              # 合并去重 + 矛盾标记
│   ├── output/
│   │   ├── __init__.py
│   │   └── writer.py             # Markdown 结构化输出
│   └── web/
│       ├── __init__.py
│       └── routes.py             # Flask 路由
├── templates/
│   ├── base.html                 # 布局骨架
│   ├── index.html                # 主页面（上传+选skill）
│   └── results.html              # 结果查看
├── static/
│   └── style.css
├── output/                       # 提取结果输出目录（gitignore）
└── tests/
    ├── __init__.py
    ├── test_chapter_splitter.py
    ├── test_chunker.py
    ├── test_dedup.py
    └── fixtures/
        └── sample_novel.txt      # 测试用短文本
```

---

## 任务

### 任务 1：项目骨架 — 依赖、配置、目录

- [ ] 创建 `pyproject.toml`（uv 项目，声明依赖）
- [ ] 创建 `.env.example`（DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL）
- [ ] 创建 `src/config.py`
- [ ] 创建所有 `__init__.py` 空文件
- [ ] 创建 `tests/fixtures/sample_novel.txt`（200 行测试用的网文片段）
- [ ] `uv sync` 安装依赖

**目标：** 项目可 import，配置可加载，依赖就绪。

**实现：**

`pyproject.toml`:
```toml
[project]
name = "novel-extractor"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "flask>=3.1",
    "chromadb>=0.5",
    "openai>=1.0",
    "tiktoken>=0.8",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8"]
```

`src/config.py`:
```python
import os
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
CHUNK_SIZE = 2000  # tokens
CHUNK_OVERLAP = 0  # 章节边界感知，不重叠
CHROMA_PERSIST_DIR = "./chroma_data"
OUTPUT_DIR = "./output"
```

**验证：**
```bash
uv run python -c "from src.config import DEEPSEEK_API_KEY; print('config ok')"
```

**提交：**
```bash
git add -A
git commit -m "chore: 项目骨架 — pyproject、配置、目录结构"
```

---

### 任务 2：预处理 — 章节分割 + 智能分块

- [ ] TDD → 创建 `tests/test_chapter_splitter.py`（RED）
- [ ] 创建 `src/preprocess/chapter_splitter.py`
- [ ] TDD → 创建 `tests/test_chunker.py`（RED）
- [ ] 创建 `src/preprocess/chunker.py`
- [ ] 运行测试 → GREEN

**目标：** 输入 TXT 文本 → 输出 `List[Chapter]`（每章含章节号、标题、正文）；再 → 输出 `List[Chunk]`（每块含文本、章节号、块序号、token 数）。

**调研背书：**
- 网文章节格式多样：`第X章`、`Chapter X`、`X.`、纯数字标题等。正则需覆盖 3 种以上常见格式。
- 分块规则：章节 token ≤ CHUNK_SIZE（2000）→ 保持整章；章节 token > CHUNK_SIZE → 按段落边界切分，每块接近但不超过 2000 tokens。

**实现：**

`src/preprocess/chapter_splitter.py` — `split_chapters(text: str) -> list[dict]`
- 正则匹配章节标题：`r'(?:第\s*[0-9零一二三四五六七八九十百千万]+\s*章|Chapter\s*\d+|^\d+[\.\、])'`
- 返回 `[{chapter_id, title, content}]`

`src/preprocess/chunker.py` — `chunk_chapter(chapter: dict) -> list[dict]`
- 用 `tiktoken.get_encoding("cl100k_base")` 做 token 计数
- 返回 `[{chunk_id, chapter_id, chapter_title, chunk_index, total_chunks, text, token_count}]`

**验证：**
```bash
uv run python -m pytest tests/test_chapter_splitter.py tests/test_chunker.py -v
```

**提交：**
```bash
git add src/preprocess/ tests/test_chapter_splitter.py tests/test_chunker.py tests/fixtures/
git commit -m "feat(preprocess): 章节分割 + 章节边界感知分块"
```

---

### 任务 3：索引 — 向量嵌入 + ChromaDB 存储

- [ ] 创建 `src/index/embedder.py`
- [ ] 创建 `src/index/store.py`
- [ ] 测试嵌入和检索 → 验证召回精度

**目标：** 输入 `List[Chunk]` → 批量嵌入 → 存入 ChromaDB → 支持语义检索 `query(text, top_k=10)`。

**实现：**

`src/index/embedder.py` — `Embedder` 类：
- 调用 DeepSeek Embedding API（`deepseek-chat` 的 embedding 端点）
- `embed(texts: list[str]) -> list[list[float]]`
- `embed_query(text: str) -> list[float]`

`src/index/store.py` — `VectorStore` 类：
- 封装 ChromaDB PersistentClient
- `add_chunks(chunks: list[dict], embeddings: list[list[float]])`
- `search(query_embedding: list[float], top_k: int) -> list[dict]`
- metadata：`{chapter_id, chapter_title, chunk_index}`

**验证：**
```bash
uv run python -c "
from src.preprocess.chapter_splitter import split_chapters
from src.preprocess.chunker import chunk_chapter
from src.index.embedder import Embedder
from src.index.store import VectorStore
# 用 sample_novel.txt 跑通整条索引链路
"
```

**提交：**
```bash
git add src/index/
git commit -m "feat(index): DeepSeek 向量嵌入 + ChromaDB 存储"
```

---

### 任务 4：提取引擎 — 基类 + Skill 注册表

- [ ] 创建 `src/extract/base.py`（LLM 调用基类 + 引用校验）
- [ ] 创建 `src/extract/__init__.py`（Skill 注册表）
- [ ] 创建 `src/pipeline.py`（流水线编排：分块→索引→提取→合并→输出）

**目标：** 定义 Skill 接口，实现统一的 LLM 调用和结果校验。每个 skill 是 `{name, description, prompt_template, run(novel_path)}` 的注册项。

**实现：**

`src/extract/base.py`:
```python
from openai import OpenAI
from src.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

class ExtractionSkill:
    name: str
    description: str
    
    def build_prompt(self, chunks: list[dict]) -> str:
        """子类覆盖，构造提取 prompt"""
        ...
    
    def validate(self, result: dict) -> list[str]:
        """校验：每条提取必须有原文引用或标注为推断"""
        ...

    def run(self, store, chaps) -> dict:
        """模板方法：检索 → 构造prompt → LLM调用 → 校验"""
        ...
```

Skill 注册表（`src/extract/__init__.py`）：
```python
from src.extract.character import CharacterSkill
from src.extract.worldbuilding import WorldbuildingSkill
from src.extract.scene import SceneSkill
from src.extract.plot import PlotSkill
from src.extract.item import ItemSkill

SKILLS = {
    "character": CharacterSkill(),
    "worldbuilding": WorldbuildingSkill(),
    "scene": SceneSkill(),
    "plot": PlotSkill(),
    "item": ItemSkill(),
}
```

**验证：**
```bash
uv run python -c "from src.extract import SKILLS; [print(s.name, s.description) for s in SKILLS.values()]"
```

**提交：**
```bash
git add src/extract/base.py src/extract/__init__.py src/pipeline.py
git commit -m "feat(extract): 提取引擎基类 + Skill 注册表"
```

---

### 任务 5：五个提取 Skill 实现

- [ ] 创建 `src/extract/character.py` — 角色提取
- [ ] 创建 `src/extract/worldbuilding.py` — 世界观提取
- [ ] 创建 `src/extract/scene.py` — 场景提取
- [ ] 创建 `src/extract/plot.py` — 剧情提取
- [ ] 创建 `src/extract/item.py` — 道具提取

**目标：** 每个 skill 继承 `ExtractionSkill`，实现 `build_prompt` 和 `validate`。Prompt 模板内置章节戳要求 + 视觉信息三级标注（显式/推断/待定⬜）。

**设计要点：**
- 每个 skill 的 prompt 结尾统一加校验指令："每条提取项必须标注章节范围。如果描述来自原文，加 `[原文]`；如果来自推断，加 `[推断·依据:xxx]`；如果原文完全没有此信息，标注 `[待定⬜]`。"
- 角色 skill 额外要求：属性按章节排序，外貌变化标注时间节点
- 世界观 skill 额外要求：力量体系标注揭示程度（仅知名称 / 能力展开 / 充分展开）

**验证：**
```bash
uv run python -c "
from src.extract import SKILLS
# 验证每个 skill 的 build_prompt 返回有效 prompt 字符串
for name, skill in SKILLS.items():
    prompt = skill.build_prompt([{'text': '测试文本', 'chapter_id': 1}])
    assert len(prompt) > 100, f'{name} prompt too short'
print('all prompts ok')
"
```

**提交：**
```bash
git add src/extract/character.py src/extract/worldbuilding.py src/extract/scene.py src/extract/plot.py src/extract/item.py
git commit -m "feat(extract): 五个提取 Skill — 角色/世界观/场景/剧情/道具"
```

---

### 任务 6：合并去重 + Markdown 输出

- [ ] TDD → 创建 `tests/test_dedup.py`（RED）
- [ ] 创建 `src/merge/dedup.py`
- [ ] 创建 `src/output/writer.py`
- [ ] 运行测试 → GREEN

**目标：** 多次提取结果合并：同名实体合并、矛盾标记 ⚠️ CONFLICT、属性按章节排序。输出 Markdown 文件到 `output/<书名>/`。

**实现：**

`src/merge/dedup.py` — `merge_characters(extracts: list[dict]) -> list[dict]`:
- 基于"姓名 + 别称"做模糊匹配合并
- 同一属性有多个值时，按章节排序，保留最详细版本
- 矛盾检测：同一属性、不同值 → 标注 `⚠️ CONFLICT: Ch5说"蓝眼睛" vs Ch80说"黑眼睛"`

`src/output/writer.py` — `Writer` 类:
- `write(book_name: str, skill_name: str, data: list[dict]) -> path`
- 输出到 `output/<book_name>/<skill_name>/*.md`
- 遵循 spec 文档第 5 节的目录结构

**验证：**
```bash
uv run python -m pytest tests/test_dedup.py -v
```

**提交：**
```bash
git add src/merge/ src/output/ tests/test_dedup.py
git commit -m "feat(merge+output): 合并去重 + 矛盾标记 + Markdown 产出"
```

---

### 任务 7：Web 界面 — 科技感多主题 UI

- [ ] 创建 `src/web/__init__.py`
- [ ] 创建 `src/web/routes.py`（Flask 路由）
- [ ] 创建 `src/app.py`（Flask 入口 + 主题配置注入）
- [ ] 创建 `templates/base.html`（布局骨架 + 导航栏 + 主题选择器）
- [ ] 创建 `templates/index.html`（上传区 + skill 卡片）
- [ ] 创建 `templates/results.html`（目录树 + Markdown 预览）
- [ ] 创建 `static/themes.css`（4 套 CSS 变量主题）
- [ ] 创建 `static/style.css`（全局样式 + 布局 + 组件）
- [ ] 创建 `static/app.js`（主题切换 + 拖拽上传 + HTMX 交互）
- [ ] 端到端验证：启动服务 → 切换主题 → 上传 → 提取 → 查看结果

**目标：** 极简科技感单页应用——暗色底、多主题切换、Lucide 图标、零 emoji、三段式布局（侧栏 + 主内容）。

**UI 约束（硬性）：**
- 所有标识/装饰使用 Lucide SVG 图标，CDN 引入（`lucide.dev`），线型 stroke-width:1.5
- 页面内不出现任何 Unicode emoji；Markdown 渲染结果中的 emoji 做过滤替换
- 颜色不超过 4 种（主题色、底色、文字色、边框色），无彩虹渐变无 neon 发光
- 主题选择器：右上角 4 个色块圆点，hover 显示主题名，点击切换，偏好存 localStorage

**路由设计：**
- `GET /` → 主页面
- `POST /upload` → 接收 TXT → 预处理（章节分割+分块+索引）
- `POST /extract` → 选中 skills → 异步流水线 → 返回结果
- `GET /results/<book_name>` → 结果目录 + Markdown 预览

**实现：**

`static/themes.css` — 4 套主题，CSS 变量驱动：
```css
:root, [data-theme="midnight"] {
  --bg-primary: #1a1b23;
  --bg-secondary: #23242f;
  --bg-tertiary: #2d2e3a;
  --accent: #8B9DC3;
  --accent-dim: rgba(139, 157, 195, 0.12);
  --text-primary: #e4e6ef;
  --text-secondary: #9498a8;
  --border: rgba(255, 255, 255, 0.06);
  --radius: 10px;
  --font-mono: "JetBrains Mono", "Cascadia Code", monospace;
}
[data-theme="aurora"] {
  --bg-primary: #0d1117; --bg-secondary: #161b22; --bg-tertiary: #1c2333;
  --accent: #00d4aa; --accent-dim: rgba(0, 212, 170, 0.10);
  --text-primary: #e6edf3; --text-secondary: #8b949e;
}
[data-theme="ember"] {
  --bg-primary: #1c1917; --bg-secondary: #25211e; --bg-tertiary: #302b27;
  --accent: #f0883e; --accent-dim: rgba(240, 136, 62, 0.10);
  --text-primary: #ede4dc; --text-secondary: #9e8e80;
}
[data-theme="void"] {
  --bg-primary: #0a0a0f; --bg-secondary: #111118; --bg-tertiary: #1a1a24;
  --accent: #a78bfa; --accent-dim: rgba(167, 139, 250, 0.10);
  --text-primary: #e8e4f0; --text-secondary: #8a82a0;
}
```

`static/style.css` 关键结构：
- 深色底 + 低对比度边框，无大面积纯白
- 卡片/面板：`background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius);` + 微弱的 `backdrop-filter: blur(12px)`
- 上传区：虚线边框 `border: 2px dashed var(--border)`，拖动悬停时 `border-color: var(--accent)` + `background: var(--accent-dim)`
- 按钮：`background: var(--accent); color: #fff;` 圆角，hover 微调亮度，无阴影扩散
- 进度条：细线（4px），`background: var(--accent)`，带 `transition: width 0.3s ease`
- 目录树：缩进线条 + 圆点指示器，纯 CSS 无图标字体
- 字体：正文系统默认，等宽部分用 `--font-mono`

`templates/base.html` 布局：
```
+-------------------+------------------------------------+
| 侧栏 (240px)       | 主内容区                            |
|                   |                                    |
| [Logo] NovelExt   |  (Jinja2 block content)            |
| ───────────────── |                                    |
| [+ 上传新小说]     |                                    |
| ───────────────── |                                    |
| 技能列表           |                                    |
| ○ 角色提取         |                                    |
| ○ 世界观           |                                    |
| ○ 场景             |                                    |
| ○ 剧情             |                                    |
| ○ 道具             |                                    |
| ───────────────── |                                    |
| 历史记录           |                                    |
+-------------------+------------------------------------+
|                    主题选择器 ●●●● (右上角固定)          |
+------------------------------------------------------+
```

`static/app.js` — 主题切换逻辑：
```javascript
function setTheme(name) {
  document.documentElement.setAttribute('data-theme', name);
  localStorage.setItem('theme', name);
}
document.addEventListener('DOMContentLoaded', () => {
  setTheme(localStorage.getItem('theme') || 'midnight');
});
```

**验证：**
```bash
uv run python src/app.py &
# 浏览器验证：
# 1. 切换 4 个主题 → 颜色即时变化
# 2. 拖拽 TXT 上传 → 侧栏显示新书名
# 3. 勾选技能 → 点击运行 → 进度条 → 结果页
# 4. 结果页：左侧目录树 + 右侧 Markdown 渲染
# 5. 确认页面内无 emoji（grep 扫描模板）
```

**提交：**
```bash
git add src/app.py src/web/ templates/ static/
git commit -m "feat(web): 科技感多主题 UI — Lucide 图标 + 4 主题 + 零 emoji"
```

---

## 验证汇总

```bash
# 类型检查（如果有 mypy）
uv run mypy src/ --ignore-missing-imports

# 单元测试
uv run python -m pytest tests/ -v

# 端到端
uv run python src/app.py
# → 浏览器 http://localhost:5000 → 上传 sample_novel.txt → 测试角色提取
```

---

## 设计决策回顾

| 决策 | 实现方式 |
|------|---------|
| LLM 供应商 | DeepSeek，通过 OpenAI SDK（设置 `base_url`） |
| 交互界面 | Flask + Jinja2 + HTMX，三段式布局（侧栏+主内容） |
| UI 风格 | 极简科技感，4 套 CSS 变量主题，Lucide SVG 图标，零 emoji |
| 分块策略 | 章节边界感知，tiktoken 计数 |
| 提取模式 | Skill 注册表，分批按需运行 |
| 视觉标注 | 三级标注（显式/推断/待定）嵌入 Prompt |
| 矛盾处理 | CONFLICT 标记，不自动选择 |
| 输出格式 | Markdown 文件，按 `output/<书名>/<维度>/` 组织 |
