@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   NovelScope — 快速环境安装 (Python 3.12)
echo ==========================================
echo.

:: 检查是否已有 Python 3.12
where py -3.12 >nul 2>&1
if %errorlevel% equ 0 (
    echo [√] Python 3.12 已存在
) else (
    echo [!] 正在通过 winget 安装 Python 3.12...
    winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    if %errorlevel% neq 0 (
        echo [×] winget 安装失败，请手动下载：https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe
        pause
        exit /b 1
    )
    echo [!] 请关闭此窗口，重新打开一个新的命令行，再运行此脚本
    pause
    exit /b 0
)

echo [!] 安装依赖...
py -3.12 -m pip install flask openai pywebview beautifulsoup4 python-dotenv httpx 2>nul

echo.
echo.
echo ==========================================
echo   [OK] Environment ready!
echo   Run: 双击 启动.bat 或 py -3.12 -m src.desktop
echo ==========================================
echo.
pause
