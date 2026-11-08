$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Test-HttpOk {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [int]$TimeoutSec = 5
    )

    try {
        $response = Invoke-WebRequest -Uri $Uri -Method GET -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($response.StatusCode -eq 200)
    } catch {
        return $false
    }
}

Write-Host "======================================" -ForegroundColor Green
Write-Host "Starting Academic Agent services" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green

$configCandidates = @("apiconfig.env", ".env")
$configPath = $configCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $configPath) {
    Write-Host "" 
    Write-Host "No config file found." -ForegroundColor Red
    Write-Host "Provide one of:" -ForegroundColor Yellow
    Write-Host "  - apiconfig.env" -ForegroundColor Cyan
    Write-Host "  - .env" -ForegroundColor Cyan
    exit 1
}

Write-Host ""
Write-Host "Loading environment variables from $configPath" -ForegroundColor Blue
Get-Content $configPath | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -match '^\s*$') { return }

    $parts = $_ -split '=', 2
    if ($parts.Count -ne 2) { return }

    $key = $parts[0].Trim()
    $value = $parts[1].Trim()
    [Environment]::SetEnvironmentVariable($key, $value)
}

if ($env:LOCAL_LLAMA_BASE) {
    $dockerLlamaBase = $env:LOCAL_LLAMA_BASE `
        -replace '://127\.0\.0\.1', '://host.docker.internal' `
        -replace '://localhost', '://host.docker.internal'

    [Environment]::SetEnvironmentVariable("LOCAL_LLAMA_BASE_DOCKER", $dockerLlamaBase)
    Write-Host "LiteLLM container local model URL: $dockerLlamaBase" -ForegroundColor Cyan
}

if (-not $env:FIELD_NOTES_CHAT_MODEL) {
    Write-Host "Warning: FIELD_NOTES_CHAT_MODEL is not set. The app may fall back to LOCAL_LLAMA_MODEL." -ForegroundColor Yellow
}

if ($env:FIELD_NOTES_CHAT_MODEL -match 'embed') {
    Write-Host "Warning: FIELD_NOTES_CHAT_MODEL looks like an embedding model name. Make sure the 8080 service is running a chat model." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Checking Docker..." -ForegroundColor Blue
try {
    docker ps | Out-Null
    Write-Host "OK Docker is running" -ForegroundColor Green
} catch {
    Write-Host "Error: Docker is not running. Start Docker Desktop first." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Checking Qdrant container..." -ForegroundColor Blue
$qdrantRunning = docker ps -q --filter "name=qdrant" 2>$null
$qdrantExists = docker ps -a -q --filter "name=qdrant" 2>$null

if ($qdrantRunning) {
    Write-Host "OK Qdrant is already running" -ForegroundColor Green
} elseif ($qdrantExists) {
    Write-Host "Restarting Qdrant..." -ForegroundColor Yellow
    docker start qdrant | Out-Null
    Start-Sleep -Seconds 2
    Write-Host "OK Qdrant started" -ForegroundColor Green
} else {
    Write-Host "Creating and starting Qdrant..." -ForegroundColor Yellow
    docker run -d `
        --name qdrant `
        --restart unless-stopped `
        -p 6333:6333 `
        qdrant/qdrant:latest | Out-Null
    Start-Sleep -Seconds 3
    Write-Host "OK Qdrant started" -ForegroundColor Green
}

Write-Host ""
Write-Host "Applying LiteLLM config..." -ForegroundColor Blue
docker compose up -d --force-recreate litellm | Out-Null
Start-Sleep -Seconds 5
Write-Host "OK LiteLLM recreated with latest config" -ForegroundColor Green

Write-Host ""
Write-Host "Checking service health..." -ForegroundColor Blue

$qdrantHealth = Test-HttpOk -Uri "http://127.0.0.1:6333/health" -TimeoutSec 5
if ($qdrantHealth) {
    Write-Host "OK Qdrant reachable at http://127.0.0.1:6333" -ForegroundColor Green
} else {
    Write-Host "Error: Qdrant is not reachable at http://127.0.0.1:6333" -ForegroundColor Red
}

$litellmHealth = Test-HttpOk -Uri "http://127.0.0.1:4000/health" -TimeoutSec 5
if ($litellmHealth) {
    Write-Host "OK LiteLLM reachable at http://127.0.0.1:4000" -ForegroundColor Green
} else {
    Write-Host "Warning: LiteLLM is not responding yet. Check: docker logs litellm" -ForegroundColor Yellow
}

$venvPython = Join-Path $PSScriptRoot ".venv312\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Error: .venv312 Python not found at $venvPython" -ForegroundColor Red
    Write-Host "Create and install the .venv312 environment first." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Checking FastAPI..." -ForegroundColor Blue
$fastapiHealth = Test-HttpOk -Uri "http://127.0.0.1:8000/" -TimeoutSec 3

if ($fastapiHealth) {
    Write-Host "OK FastAPI is already running at http://127.0.0.1:8000" -ForegroundColor Green
} else {
    Write-Host "Starting FastAPI in background..." -ForegroundColor Yellow
    $fastapiCommand = "Set-Location '$PSScriptRoot'; & '$venvPython' -m uvicorn src.main:app --host 127.0.0.1 --port 8000"
    Start-Process powershell -ArgumentList @(
        "-NoProfile",
        "-WindowStyle", "Minimized",
        "-Command", $fastapiCommand
    ) | Out-Null

    Start-Sleep -Seconds 4

    $fastapiHealth = Test-HttpOk -Uri "http://127.0.0.1:8000/" -TimeoutSec 5
    if ($fastapiHealth) {
        Write-Host "OK FastAPI started at http://127.0.0.1:8000" -ForegroundColor Green
    } else {
        Write-Host "Error: FastAPI failed to start at http://127.0.0.1:8000" -ForegroundColor Red
        Write-Host "Manual command: & '.\.venv312\Scripts\python.exe' -m uvicorn src.main:app --host 127.0.0.1 --port 8000" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Green
Write-Host "All services are ready" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Activate venv if needed: .venv312\Scripts\Activate.ps1" -ForegroundColor Cyan
Write-Host "2. FastAPI is now auto-checked and auto-started by this script" -ForegroundColor Cyan
Write-Host "3. Trigger Zotero sync: Invoke-WebRequest -Uri http://127.0.0.1:8000/ingest/zotero -Method POST -ContentType 'application/json' -Body '{\"full_sync\": false}' -UseBasicParsing" -ForegroundColor Cyan
Write-Host "4. Trigger field-notes sync: Invoke-WebRequest -Uri http://127.0.0.1:8000/ingest/field-notes -Method POST -ContentType 'application/json' -Body '{\"full_sync\": false}' -UseBasicParsing" -ForegroundColor Cyan
Write-Host ""
Write-Host "Service URLs:" -ForegroundColor Cyan
Write-Host "  - FastAPI: http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "  - LiteLLM: http://127.0.0.1:4000" -ForegroundColor Cyan
Write-Host "  - Qdrant: http://127.0.0.1:6333" -ForegroundColor Cyan