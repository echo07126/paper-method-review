<#
  交付打包脚本（双轨）
    轨道 A · 源码包：仅含运行必需文件（排除 docs/、materials/、samples/、backend/tests、backend/scripts 等），并携带 backend/.env
    轨道 B · 离线镜像包：docker compose build 后 docker save 出两个镜像 tar（免构建、免联网）

  用法（在仓库根目录执行）：
    powershell -ExecutionPolicy Bypass -File .\build_release.ps1               # 两轨都打
    powershell -ExecutionPolicy Bypass -File .\build_release.ps1 -Mode source  # 只打源码包
    powershell -ExecutionPolicy Bypass -File .\build_release.ps1 -Mode image   # 只打镜像包
    powershell -ExecutionPolicy Bypass -File .\build_release.ps1 -Version 1.0 -OutDir release
#>
[CmdletBinding()]
param(
  [ValidateSet('source', 'image', 'both')] [string]$Mode = 'both',
  [string]$Version = '1.0',
  [string]$OutDir = 'release'
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root

$outPath = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $outPath | Out-Null

$backendImage = "paper-method-review-backend:$Version"
$frontendImage = "paper-method-review-frontend:$Version"

function New-SourcePackage {
  Write-Host "[源码包] 组装运行必需文件 ..."
  $stageRoot = Join-Path $outPath '.stage'
  $stage = Join-Path $stageRoot 'paper-method-review'
  Remove-Item $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $stage | Out-Null

  # 顶层文件
  foreach ($f in 'docker-compose.yml', 'README.md', '交付说明.md', 'THIRD_PARTY_NOTICES.md', 'requirements.txt', '.gitignore', 'start.ps1', 'start.sh') {
    if (Test-Path $f) { Copy-Item $f $stage -Force }
  }

  # 审查清单
  Copy-Item 'checklists' $stage -Recurse -Force

  # 后端：仅 app/ 与构建所需文件
  New-Item -ItemType Directory -Force -Path (Join-Path $stage 'backend') | Out-Null
  Copy-Item 'backend/app' $stage/backend -Recurse -Force
  foreach ($f in 'Dockerfile', 'requirements.txt', '.env', '.env.example', '.dockerignore') {
    if (Test-Path "backend/$f") { Copy-Item "backend/$f" "$stage/backend" -Force }
  }

  # 前端：仅 src/ 与构建所需文件
  New-Item -ItemType Directory -Force -Path (Join-Path $stage 'frontend') | Out-Null
  Copy-Item 'frontend/src' $stage/frontend -Recurse -Force
  if (Test-Path 'frontend/mockup') { Copy-Item 'frontend/mockup' $stage/frontend -Recurse -Force }
  foreach ($f in 'Dockerfile', 'nginx.conf', 'index.html', 'package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.mjs', '.dockerignore', '.env.example') {
    if (Test-Path "frontend/$f") { Copy-Item "frontend/$f" "$stage/frontend" -Force }
  }

  # 运行数据占位目录（容器以 uid 10001 写入）
  New-Item -ItemType Directory -Force -Path (Join-Path $stage 'data/tmp') | Out-Null
  Set-Content -Path (Join-Path $stage 'data/.gitkeep') -Value '' -NoNewline

  # 清理编译产物
  Get-ChildItem -Path $stage -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  Get-ChildItem -Path $stage -Recurse -Filter '*.pyc' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

  $tarName = "paper-method-review-src-$Version.tar.gz"
  $tarPath = Join-Path $outPath $tarName
  Remove-Item $tarPath -Force -ErrorAction SilentlyContinue
  tar -czf $tarPath -C $stageRoot 'paper-method-review'
  if ($LASTEXITCODE -ne 0) { throw "tar 打包失败（请确认系统自带 tar 可用：Windows 10 1803+ 自带 tar.exe）。" }

  Remove-Item $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
  Write-Host "[源码包] 完成：$tarPath"

  if (Test-Path 'backend/.env') {
    Copy-Item 'backend/.env' (Join-Path $outPath 'backend.env') -Force
    Write-Host "[源码包] 已随包附带 backend.env（走镜像包时请将其放为 backend/.env）。"
  } else {
    Write-Warning "[源码包] 未找到 backend/.env —— 交付前请复制 backend/.env.example 并填写 DEEPSEEK_API_KEY。"
  }
}

function New-ImagePackage {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "未检测到 docker，无法打镜像包。" }

  Write-Host "[镜像包] docker compose build ..."
  $env:IMAGE_TAG = $Version
  docker compose build
  if ($LASTEXITCODE -ne 0) { throw "docker compose build 失败。" }

  $tarName = "paper-method-review-images-$Version.tar"
  $tarPath = Join-Path $outPath $tarName
  Write-Host "[镜像包] docker save -> $tarName ..."
  docker save -o $tarPath $backendImage $frontendImage
  if ($LASTEXITCODE -ne 0) { throw "docker save 失败。" }

  if (Test-Path 'backend/.env') { Copy-Item 'backend/.env' (Join-Path $outPath 'backend.env') -Force }
  Write-Host "[镜像包] 完成：$tarPath"
}

Write-Host "交付打包：Mode=$Mode  Version=$Version  OutDir=$OutDir"
if ($Mode -eq 'source' -or $Mode -eq 'both') { New-SourcePackage }
if ($Mode -eq 'image' -or $Mode -eq 'both') { New-ImagePackage }

Write-Host ""
Write-Host "产物："
Get-ChildItem $outPath -File | ForEach-Object { Write-Host ("  - " + $_.Name) }
Write-Host "离线镜像包（裸 tar）仅含镜像；如需「解压即用」的单文件离线部署包，请再运行 无关代码/tools/build_image_bundle.ps1 生成 …-离线镜像包.zip。"