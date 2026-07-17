"""
NovelScope 桌面应用入口
用 pywebview 包装为独立原生窗口，PyInstaller 打包后即为 .exe
"""
import sys
import threading
import webview

from src.app import app


def run_flask():
    app.run(debug=False, port=5000, use_reloader=False)


def main():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    webview.create_window(
        title="NovelScope · AI 小说深度分析",
        url="http://127.0.0.1:5000",
        width=1200,
        height=820,
        min_size=(900, 600),
        text_select=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
