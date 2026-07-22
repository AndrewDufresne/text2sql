# deploy-to-ubuntu.ps1 — one-shot deploy of text2sql-platform to remote Ubuntu host.
#
# What it does:
#   1. tar-streams the source tree (minus heavy/regenerated dirs) over ssh
#   2. ships .env.server -> remote .env (port-remapped to dodge collisions)
#   3. saves every locally-built/pulled compose image and pipes through
#      ssh -> `docker load` (skips images already present on remote)
#   4. ssh runs scripts/server-up.sh (network create + vendor + compose up)
#
# Pre-reqs already met:
#   - SSH key auth: andrew@192.168.125.18 (no password prompt)
#   - Server has docker 25 + compose v2
#
# Usage (from repo root or anywhere — script anchors to its own location):
#   pwsh scripts/deploy-to-ubuntu.ps1                 # full deploy
#   pwsh scripts/deploy-to-ubuntu.ps1 -SkipImages     # code-only refresh
#   pwsh scripts/deploy-to-ubuntu.ps1 -SkipCode       # images-only
#   pwsh scripts/deploy-to-ubuntu.ps1 -SkipUp         # transfer only, no bring-up

param(
  [string] $RemoteHost = "andrew@192.168.125.18",
  [string] $RemoteDir  = "/data_ssd/docker/text2sql-platform",
  [switch] $SkipCode,
  [switch] $SkipImages,
  [switch] $SkipUp,
  [switch] $ForceImages   # re-transfer images even if remote has them
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Run-Ssh($cmd) { ssh $RemoteHost $cmd }

# ---------------------------------------------------------------------------
# 1) Code transfer (tar | ssh tar)
# ---------------------------------------------------------------------------
if (-not $SkipCode) {
  Step "Code sync -> ${RemoteHost}:${RemoteDir}"
  Run-Ssh "mkdir -p '$RemoteDir'"

  # Windows BSD tar supports --exclude. Stream to remote tar.
  $excludes = @(
    "--exclude=./.git",
    "--exclude=./.venv",
    "--exclude=./node_modules",
    "--exclude=./src/services/*/vendor",
    "--exclude=./**/__pycache__",
    "--exclude=./**/.pytest_cache",
    "--exclude=./**/*.pyc",
    "--exclude=./eval_out*.log",
    "--exclude=./tests/eval/report.json",
    "--exclude=./.env"   # we ship .env.server -> .env separately
  )
  # Use cmd-style invocation so tar streams to stdout uninterrupted by PS pipe quirks.
  & cmd /c "tar -cf - $($excludes -join ' ') . | ssh $RemoteHost ""tar -xf - -C '$RemoteDir'"""
  if ($LASTEXITCODE -ne 0) { throw "tar pipe failed (exit $LASTEXITCODE)" }

  # Ship server env overlay -> .env on remote
  scp .env.server "${RemoteHost}:${RemoteDir}/.env"
  Run-Ssh "chmod +x '$RemoteDir/scripts/server-up.sh'"
  Write-Host "[ok] code synced + .env installed" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 2) Image transfer (docker save | ssh docker load)
# ---------------------------------------------------------------------------
if (-not $SkipImages) {
  Step "Enumerating compose images"
  $composeArgs = @(
    "--env-file", ".env",
    "-f", "compose/00-network.yml",
    "-f", "compose/10-state.yml",
    "-f", "compose/20-platform.yml",
    "-f", "compose/30-data.yml",
    "-f", "compose/31-datahub.yml",
    "-f", "compose/40-capability.yml",
    "-f", "compose/50-app.yml",
    "-f", "compose/60-hitl.yml",
    "-f", "compose/70-observability.yml",
    "-f", "compose/80-portal.yml"
  )
  $images = & docker compose @composeArgs config --images 2>$null |
    Where-Object { $_ -and $_.Trim() -ne "" } |
    Sort-Object -Unique

  Write-Host "Found $($images.Count) images. Local sizes:"
  foreach ($img in $images) {
    $sz = (docker image inspect $img --format '{{.Size}}' 2>$null)
    if ($sz) { "  {0,-60} {1,8:N0} MB" -f $img, ($sz/1MB) }
    else     { "  {0,-60} (MISSING locally — will be skipped)" -f $img }
  }

  # Probe remote — what does it already have?
  Step "Probing remote image cache"
  $remoteList = (Run-Ssh "docker image ls --format '{{.Repository}}:{{.Tag}}'" | Out-String) -split "`r?`n" |
    Where-Object { $_ -and $_.Trim() -ne "" }
  $remoteSet = @{}
  foreach ($r in $remoteList) { $remoteSet[$r.Trim()] = $true }

  $i = 0
  foreach ($img in $images) {
    $i++
    $hasLocal = (docker image inspect $img --format '{{.Id}}' 2>$null)
    if (-not $hasLocal) { Write-Host "[$i/$($images.Count)] SKIP (not local): $img" -ForegroundColor DarkYellow; continue }

    if ($remoteSet.ContainsKey($img) -and -not $ForceImages) {
      Write-Host "[$i/$($images.Count)] SKIP (remote has it): $img" -ForegroundColor DarkGray
      continue
    }

    Write-Host "[$i/$($images.Count)] xfer: $img" -ForegroundColor Cyan
    & cmd /c "docker save ""$img"" | ssh $RemoteHost ""docker load"""
    if ($LASTEXITCODE -ne 0) { throw "save|load failed for $img (exit $LASTEXITCODE)" }
  }
  Write-Host "[ok] images transferred" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 3) Bring up on remote
# ---------------------------------------------------------------------------
if (-not $SkipUp) {
  Step "Bringing up stack on remote"
  Run-Ssh "cd '$RemoteDir' && bash scripts/server-up.sh up"
  Write-Host "`n[done] verify with:  ssh $RemoteHost ""cd $RemoteDir && bash scripts/server-up.sh status""" -ForegroundColor Green
}
