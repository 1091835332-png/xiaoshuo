@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: 优先用打包好的 exe
if exist "dist\NovelScope\NovelScope.exe" (
    start "" "dist\NovelScope\NovelScope.exe"
    exit
)

echo =====================================
echo   NovelScope - 开发模式启动
echo =====================================
echo.

python -m src.desktop 2>nul
if %errorlevel% neq 0 (
    echo 运行失败。请检查依赖：pip install flask openai pywebview python-dotenv beautifulsoup4
)

pause
