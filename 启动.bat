@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo =====================================
echo    📚 小说分析工具 — 启动中...
echo =====================================
echo.

start http://127.0.0.1:5000

.venv\Scripts\python -m src.app 2>nul
if %errorlevel% neq 0 (
    echo ❌ 依赖缺失，正在安装...
    uv pip install flask python-dotenv openai beautifulsoup4
    echo.
    echo 重新启动...
    start http://127.0.0.1:5000
    .venv\Scripts\python -m src.app
)

pause
