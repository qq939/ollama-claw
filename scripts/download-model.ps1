#!/usr/bin/env pwsh
param(
    [Parameter(Mandatory=$true)]
    [string]$Model
)

$ErrorActionPreference = "Continue"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Ollama 模型下载工具" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "正在下载模型: $Model" -ForegroundColor Yellow
Write-Host ""

$process = Start-Process -FilePath "docker" -ArgumentList "exec ollama ollama pull $Model" -NoNewWindow -PassThru

$exitCode = $null
while (-not $process.HasExited) {
    Start-Sleep -Seconds 1
}

$exitCode = $process.ExitCode

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  下载成功！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  下载失败 (Exit code: $exitCode)" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
}

Write-Host ""
Write-Host "当前已安装的模型:" -ForegroundColor Cyan
docker exec ollama ollama list