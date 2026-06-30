@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

echo.
echo ================================================
echo   重力储能智能调度展示平台 - Windows 启动脚本
echo ================================================
echo 当前目录：%cd%
echo.

where node >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 Node.js。
  echo 请先安装 Node.js LTS 版本：https://nodejs.org/
  echo 安装完成后重新双击本文件。
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 npm，请确认 Node.js 已正确安装。
  pause
  exit /b 1
)

where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [错误] 未检测到 Python。
    echo 请先安装 Python 3.10 或更高版本：https://www.python.org/downloads/
    echo 安装时请勾选 Add Python to PATH。
    pause
    exit /b 1
  )
  set PYTHON_CMD=python
) else (
  set PYTHON_CMD=py -3
)

if not exist node_modules (
  echo.
  echo [1/4] 正在安装前端依赖 npm install ...
  call npm install
  if errorlevel 1 (
    echo [错误] 前端依赖安装失败。
    pause
    exit /b 1
  )
) else (
  echo [1/4] 已检测到 node_modules，跳过前端依赖安装。
)

if not exist .venv (
  echo.
  echo [2/4] 正在创建 Python 虚拟环境 ...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 (
    echo [错误] Python 虚拟环境创建失败。
    pause
    exit /b 1
  )

  echo.
  echo [3/4] 正在安装后端依赖 ...
  call .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [错误] 后端依赖安装失败。
    pause
    exit /b 1
  )
) else (
  echo [2/4] 已检测到 .venv，跳过后端依赖安装。
  echo [3/4] 后端环境已存在。
)

echo.
echo [4/4] 正在启动系统 ...
echo 后端地址：http://127.0.0.1:8001
echo 前端地址：http://127.0.0.1:5174
echo.

start "Gravity Storage Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8001"
timeout /t 2 /nobreak >nul
start "Gravity Storage Frontend" cmd /k "node_modules\.bin\vite.cmd --host 127.0.0.1 --port 5174"
timeout /t 3 /nobreak >nul
start http://127.0.0.1:5174/

echo.
echo 系统已启动。
echo 登录账号：siat-admin
echo 登录密码：demo123456
echo.
echo 如果要关闭系统，请关闭刚弹出的 Backend 和 Frontend 两个命令窗口。
echo.
pause

