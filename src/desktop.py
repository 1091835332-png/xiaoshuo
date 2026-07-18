"""
NovelScope 桌面应用入口 — pywebview 原生窗口
Python 3.12/3.13 原生支持，3.15 自动降级
"""
import sys
import threading
import time

from src.app import app


def run_flask():
    app.run(debug=False, port=5000, use_reloader=False)


def main():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    time.sleep(0.8)

    try:
        import webview
        webview.create_window(
            title="NovelScope · AI 小说深度分析",
            url="http://127.0.0.1:5000",
            width=1200, height=820,
            min_size=(900, 600),
            text_select=True,
        )
        webview.start(gui="edgechromium")
        return
    except Exception as e:
        print(f"[!] 原生窗口不可用 ({e})，降级到 --app 模式...")

    # 降级：Chrome --app 模式
    import subprocess, webbrowser, shutil
    url = "http://127.0.0.1:5000"
    browser = shutil.which("chrome") or shutil.which("msedge") or shutil.which("edge")
    if browser:
        subprocess.Popen([browser, f"--app={url}", "--window-size=1200,820"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"已启动 {browser} --app 模式")
    else:
        webbrowser.open(url)
        print("使用默认浏览器")

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
