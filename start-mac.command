#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "重力储能智能调度展示平台启动中..."
echo "项目目录：$(pwd)"

if [ ! -d "node_modules" ]; then
  echo "未检测到 node_modules，正在安装前端依赖..."
  npm install
fi

if [ ! -d ".venv" ]; then
  echo "未检测到 Python 虚拟环境，正在创建并安装后端依赖..."
  python3 -m venv .venv
  ./.venv/bin/python -m pip install -r requirements.txt
fi

echo "启动后端：http://127.0.0.1:8001"
./.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8001 &
BACKEND_PID=$!

echo "启动前端：http://127.0.0.1:5174"
./node_modules/.bin/vite --host 127.0.0.1 --port 5174 &
FRONTEND_PID=$!

sleep 3
open -a Safari http://127.0.0.1:5174/ || open http://127.0.0.1:5174/

echo ""
echo "系统已启动。"
echo "登录账号：siat-admin"
echo "登录密码：demo123456"
echo ""
echo "关闭本窗口会停止前端和后端服务。"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true" EXIT
wait
