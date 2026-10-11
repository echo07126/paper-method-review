<#
  一键启动（Windows / Docker Desktop）
  用法：powershell -ExecutionPolicy Bypass -File .\start.ps1
  自动完成：校验 backend/.env → 创建 ./data → 按需构建或直接使用已 load 的镜像 → 启动容器 → 打印访问地址。
#>
[CmdletBinding()]
param([string]$Version = '1.0')

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "未检测到 docker：请先安装并启动 Docker Desktop（或 docker engine）。"
}

if (-not (Test-Path 'backend/.env')) {
  if (Test-Path 'backend/.env.example') { Copy-Item 'backend/.env.example' 'backend/.env' }
  Write-Warning "未找到 backend/.env，已从 .env.example 复制；若未填写 DEEPSEEK_API_KEY，将仅使用规则引擎（模型增强不可用）。"
}

New-Item -ItemType Directory -Force -Path 'data' | Out-Null

$env:IMAGE_TAG = $Version
$backendImage = "paper-method-review-backend:$Version"

docker image inspect $backendImage *> $null
if ($LASTEXITCODE -eq 0) {
  Write-Host "检测到本地镜像 $backendImage，直接启动（不重新构建）。"
  docker compose up -d
} else {
  Write-Host "未检测到本地镜像，执行 docker compose up -d --build ..."
  docker compose up -d --build
}

docker compose ps
Write-Host ""
Write-Host "前端界面：http://127.0.0.1:8080"
Write-Host "后端健康：http://127.0.0.1:8000/api/v1/health"
Write-Host "停止服务：docker compose down"