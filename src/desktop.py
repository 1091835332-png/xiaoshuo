"""
NovelScope 桌面应用入口
用 Chrome/Edge 的 --app 模式创建无边框原生窗口，无需 pywebview。
"""
import subprocess
import sys
import threading
import time
import webbrowser
import shutil

from src.app import app


def run_flask():
    app.run(debug=False, port=5000, use_reloader=False)


def find_browser():
    """查找 Chrome 或 Edge 路径"""
    for name in ["chrome", "google-chrome", "msedge", "edge"]:
        path = shutil.which(name)
        if path:
            return path
    return None


def main():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    time.sleep(0.8)

    url = "http://127.0.0.1:5000"
    browser = find_browser()

    if browser:
        print(f"打开 {browser} --app 模式...")
        subprocess.Popen(
            [browser, f"--app={url}", "--window-size=1200,820"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        print("未找到 Chrome/Edge，使用默认浏览器...")
        webbrowser.open(url)

    print("应用已启动。关闭此窗口退出。")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
