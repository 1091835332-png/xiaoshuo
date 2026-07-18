"""
小说分析工具 — Flask Web 应用
上传 txt/epub/docx → 解析文本 → AI 分析 → 展示结果
"""

import json as _json
import sys
import uuid
from pathlib import Path
from typing import Generator

from flask import Flask, render_template, request, jsonify, session, Response

from src.config import UPLOAD_DIR, OUTPUT_DIR, DEEPSEEK_BASE_URL
from src.parser import parse
from src.analyzer import NovelAnalyzer
from src.engine import ExtractionPipeline, GRANULARITY_LABELS

# PyInstaller 打包后资源路径：_MEIPASS 是解压临时目录
if getattr(sys, "frozen", False):
    _ROOT = Path(sys._MEIPASS)
else:
    _ROOT = Path(__file__).resolve().parent.parent

app = Flask(
    __name__,
    template_folder=str(_ROOT / "src" / "templates"),
    static_folder=str(_ROOT / "src" / "static"),
)
app.secret_key = "novel-extractor-secret-key-change-in-production"

UPLOAD_DIR_PATH = Path(UPLOAD_DIR)
UPLOAD_DIR_PATH.mkdir(parents=True, exist_ok=True)
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".txt", ".epub", ".docx"}


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """处理文件上传，解析并返回章节信息"""
    if "file" not in request.files:
        return jsonify({"error": "未选择文件"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "文件名为空"}), 400

    if not allowed_file(file.filename):
        return jsonify(
            {"error": f"不支持的文件格式，仅支持 {', '.join(ALLOWED_EXTENSIONS)}"}
        ), 400

    # 保存到 uploads 目录
    ext = Path(file.filename).suffix
    saved_name = f"{uuid.uuid4().hex}{ext}"
    saved_path = UPLOAD_DIR_PATH / saved_name
    file.save(str(saved_path))

    try:
        chapters = parse(str(saved_path))
    except Exception as e:
        saved_path.unlink(missing_ok=True)
        return jsonify({"error": f"解析失败: {str(e)}"}), 400

    # 存 session
    session["saved_file"] = saved_name
    session["total_chars"] = sum(ch.char_count for ch in chapters)
    session["chapter_count"] = len(chapters)

    return jsonify({
        "success": True,
        "filename": file.filename,
        "chapter_count": len(chapters),
        "total_chars": session["total_chars"],
        "chapters": [
            {"index": ch.index, "title": ch.title, "char_count": ch.char_count}
            for ch in chapters
        ],
    })


_ENV_PATH = _ROOT / ".env"

def _read_env_key() -> str:
    """从 .env 文件读取 API Key"""
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

def _read_env_base_url() -> str:
    """从 .env 文件读取 Base URL"""
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_BASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "https://api.deepseek.com"

def _write_env_config(api_key: str, base_url: str):
    """写入 API Key 和 Base URL 到 .env 文件"""
    lines = []
    found_key = False
    found_url = False
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("DEEPSEEK_API_KEY="):
                lines.append(f'DEEPSEEK_API_KEY={api_key}')
                found_key = True
            elif s.startswith("DEEPSEEK_BASE_URL="):
                lines.append(f'DEEPSEEK_BASE_URL={base_url}')
                found_url = True
            elif s:
                lines.append(line)
    if not found_key and api_key:
        lines.append(f'DEEPSEEK_API_KEY={api_key}')
    if not found_url:
        lines.append(f'DEEPSEEK_BASE_URL={base_url}')
    _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.route("/api/set-key", methods=["POST"])
def set_key():
    """设置 API Key + Base URL — 持久化到 .env 文件"""
    data = request.get_json(silent=True) or {}
    api_key = (data.get("api_key") or "").strip()
    base_url = (data.get("base_url") or "https://api.deepseek.com").strip()
    if api_key:
        _write_env_config(api_key, base_url)
        session["ds_api_key"] = api_key
        session["ds_base_url"] = base_url
        return jsonify({"success": True, "has_key": True, "base_url": base_url})
    else:
        session.pop("ds_api_key", None)
        session.pop("ds_base_url", None)
        return jsonify({"success": True, "has_key": False})


@app.route("/api/has-key")
def has_key():
    """检查设置 — 优先 .env，其次 session"""
    env_key = _read_env_key()
    env_url = _read_env_base_url()
    if env_key:
        session["ds_api_key"] = env_key
        session["ds_base_url"] = env_url
        return jsonify({"has_key": True, "base_url": env_url})
    sk = session.get("ds_api_key")
    su = session.get("ds_base_url", "https://api.deepseek.com")
    return jsonify({"has_key": bool(sk), "base_url": su})


@app.route("/analyze", methods=["POST"])
def analyze():
    """对已上传的文件执行 AI 分析"""
    saved_name = session.get("saved_file")
    if not saved_name:
        return jsonify({"error": "请先上传文件"}), 400

    saved_path = UPLOAD_DIR_PATH / saved_name
    if not saved_path.exists():
        return jsonify({"error": "文件已过期，请重新上传"}), 400

    data = request.get_json(silent=True) or {}
    dimensions = data.get("dimensions", ["worldview", "characters", "plot", "themes"])

    try:
        chapters = parse(str(saved_path))
        api_key = session.get("ds_api_key") or _read_env_key()
        if not api_key:
            return jsonify({"error": "请先设置 DeepSeek API Key（点击页面右上角齿轮图标）"}), 400
        api_url = session.get("ds_base_url") or _read_env_base_url()
        analyzer = NovelAnalyzer(api_key=api_key, base_url=api_url)
        results = analyzer.analyze(chapters, dimensions=dimensions)
        summary = analyzer.format_summary(results)
    except Exception as e:
        return jsonify({"error": f"分析失败: {str(e)}"}), 500

    return jsonify({
        "success": True,
        "results": results,
        "summary": summary,
    })


@app.route("/analyze-stream", methods=["POST"])
def analyze_stream():
    """SSE 流式分析：逐维度推送结果，前端实时展示进度"""
    saved_name = session.get("saved_file")
    if not saved_name:
        return jsonify({"error": "请先上传文件"}), 400

    saved_path = UPLOAD_DIR_PATH / saved_name
    if not saved_path.exists():
        return jsonify({"error": "文件已过期，请重新上传"}), 400

    api_key = session.get("ds_api_key") or _read_env_key()
    if not api_key:
        return jsonify({"error": "请先设置 DeepSeek API Key"}), 400

    data = request.get_json(silent=True) or {}
    dimensions = data.get("dimensions", ["worldview", "characters", "plot", "themes"])

    chapters = parse(str(saved_path))
    api_url = session.get("ds_base_url") or _read_env_base_url()
    analyzer = NovelAnalyzer(api_key=api_key, base_url=api_url)

    def generate() -> Generator[str, None, None]:
        for dim, label, content, done, total in analyzer.analyze_stream(chapters, dimensions):
            event = _json.dumps({
                "dim": dim,
                "label": label,
                "content": content,
                "done": done,
                "total": total,
            }, ensure_ascii=False)
            yield f"data: {event}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/granularities")
def granularities():
    return jsonify(GRANULARITY_LABELS)


@app.route("/analyze-stream-v2", methods=["POST"])
def analyze_stream_v2():
    """SSE 流式分析 v2：三层递进提取管线"""
    saved_name = session.get("saved_file")
    if not saved_name:
        return jsonify({"error": "请先上传文件"}), 400

    saved_path = UPLOAD_DIR_PATH / saved_name
    if not saved_path.exists():
        return jsonify({"error": "文件已过期，请重新上传"}), 400

    api_key = session.get("ds_api_key") or _read_env_key()
    if not api_key:
        return jsonify({"error": "请先设置 DeepSeek API Key"}), 400

    data = request.get_json(silent=True) or {}
    granularity = data.get("granularity", "detailed")

    chapters = parse(str(saved_path))
    api_url = session.get("ds_base_url") or _read_env_base_url()
    pipeline = ExtractionPipeline(api_key=api_key, base_url=api_url)

    def generate() -> Generator[str, None, None]:
        for ev in pipeline.run(chapters, granularity=granularity):
            yield f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
