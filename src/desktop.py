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

    # 降级：Chrome/Edge --app 模式（无地址栏、无标签、独立窗口）
    import subprocess, webbrowser, os
    url = "http://127.0.0.1:5000"
    browser = None
    for p in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]:
        if os.path.exists(p):
            browser = p
            break

    if browser:
        print(f"启动独立窗口: {browser}")
        subprocess.Popen([browser, f"--app={url}", "--window-size=1200,820"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print("未找到 Chrome/Edge，用默认浏览器...")
        webbrowser.open(url)

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
