#!/usr/bin/env bash
# 一键启动（Linux / macOS）
# 用法：bash start.sh          （可用 export IMAGE_TAG=1.0 覆盖镜像标签）
set -euo pipefail
cd "$(dirname "$0")"

IMAGE_TAG="${IMAGE_TAG:-1.0}"
export IMAGE_TAG

if ! command -v docker >/dev/null 2>&1; then
  echo "未检测到 docker，请先安装 docker engine 与 compose 插件。" >&2
  exit 1
fi

if [ ! -f backend/.env ]; then
  if [ -f backend/.env.example ]; then cp backend/.env.example backend/.env; fi
  echo "警告：未找到 backend/.env，已从 .env.example 复制；未填写 DEEPSEEK_API_KEY 时仅规则引擎可用。" >&2
fi

mkdir -p data
if [ "$(uname -s)" = "Linux" ] && [ "$(stat -c '%u' data 2>/dev/null || echo 0)" != "10001" ]; then
  echo "提示：容器以 uid 10001 运行；若启动后报 data 目录无写权限，请执行 sudo chown -R 10001:10001 data" >&2
fi

if docker image inspect "paper-method-review-backend:${IMAGE_TAG}" >/dev/null 2>&1; then
  echo "检测到本地镜像，直接启动（不重新构建）。"
  docker compose up -d
else
  echo "未检测到本地镜像，执行 docker compose up -d --build ..."
  docker compose up -d --build
fi

docker compose ps
echo
echo "前端界面：http://127.0.0.1:8080"
echo "后端健康：http://127.0.0.1:8000/api/v1/health"
echo "停止服务：docker compose down"