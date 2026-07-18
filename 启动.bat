@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: 优先用打包好的 exe
if exist "dist\NovelScope\NovelScope.exe" (
    start "" "dist\NovelScope\NovelScope.exe"
    exit
)

:: Python 3.12 原生窗口模式（推荐）
py -3.12 -m src.desktop 2>nul
if %errorlevel% equ 0 exit

:: 当前 Python --app 模式（降级）
python -m src.desktop 2>nul
if %errorlevel% equ 0 exit

echo 运行失败。请先运行 install-py312.bat 安装环境
pause
