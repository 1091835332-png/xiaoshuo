@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==========================================
echo   NovelScope — 打包为单个 .exe
echo ==========================================
echo.

:: 检查 pyinstaller
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [1/3] 安装 PyInstaller...
    pip install pyinstaller
)

:: 安装运行依赖（如果缺失）
echo [2/3] 检查依赖...
pip install flask openai python-dotenv beautifulsoup4 pywebview >nul 2>&1

:: 构建
echo [3/3] 开始打包...
pyinstaller ^
  --onedir ^
  --name NovelScope ^
  --add-data "src\templates;src\templates" ^
  --add-data "src\static;src\static" ^
  --hidden-import webview.platforms.winforms ^
  --hidden-import flask ^
  --noconsole ^
  --clean ^
  --distpath .\dist ^
  --workpath .\build-tmp ^
  src\desktop.py

echo.
if %errorlevel% equ 0 (
    echo ==========================================
    echo   ✅ 打包成功！
    echo   📁 dist\NovelScope\NovelScope.exe
    echo ==========================================
) else (
    echo ❌ 打包失败，请检查上方错误信息
)

pause
