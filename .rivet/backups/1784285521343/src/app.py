"""
小说分析工具 — Flask Web 应用
上传 txt/epub/docx → 解析文本 → AI 分析 → 展示结果
"""

import uuid
from pathlib import Path

from flask import Flask, render_template, request, jsonify, session

from src.config import UPLOAD_DIR, OUTPUT_DIR
from src.parser import parse
from src.analyzer import NovelAnalyzer

app = Flask(__name__, template_folder="templates", static_folder="static")
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
    except Exception as e:
        return jsonify({"error": f"解析失败: {str(e)}"}), 400

    analyzer = NovelAnalyzer()
    try:
        results = analyzer.analyze(chapters, dimensions=dimensions)
        # 生成摘要文本
        summary = analyzer.format_summary(results)
    except Exception as e:
        return jsonify({"error": f"分析失败: {str(e)}"}), 500

    return jsonify({
        "success": True,
        "results": results,
        "summary": summary,
    })


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
