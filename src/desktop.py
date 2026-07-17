"""
桌面应用入口 — 用 pywebview 包装成独立窗口
双击 启动.bat 即打开原生窗口，无需浏览器
"""
import threading
import webview

from src.app import app


def run_flask():
    """在后台线程启动 Flask"""
    app.run(debug=False, port=5000, use_reloader=False)


if __name__ == "__main__":
    # 启动 Flask 后台线程
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    # 创建原生窗口
    webview.create_window(
        title="📚 小说分析工具",
        url="http://127.0.0.1:5000",
        width=1100,
        height=800,
        min_size=(800, 600),
        text_select=True,
    )
    webview.start()
