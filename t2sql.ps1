<#
.SYNOPSIS
  Text2SQL Platform — one-click control script.

.DESCRIPTION
  Single entry point to start / stop / pause / resume the full stack
  (Phase 1 walking skeleton + Phase 3 HITL + Phase 4 observability + Portainer).

.PARAMETER Command
  start | stop | pause | resume | restart | status | urls | open | logs | doctor | nuke | help

.PARAMETER Profile
  min  = walking skeleton only (Phase 1+2)
  hitl = + Argilla (Phase 3)
  obs  = observability only (Prom + Loki + Tempo + Grafana)
  all  = everything (default)

.EXAMPLE
  .\t2sql.ps1 start          # start full stack
  .\t2sql.ps1 start min      # start walking skeleton only
  .\t2sql.ps1 pause          # docker pause everything (freeze, keep RAM state)
  .\t2sql.ps1 resume         # unpause
  .\t2sql.ps1 stop           # stop containers (keep volumes)
  .\t2sql.ps1 nuke           # DESTROY everything incl. volumes (asks for confirm)
  .\t2sql.ps1 urls           # print every UI URL + credentials
  .\t2sql.ps1 open           # open the master control UI (Portainer) in browser
#>

[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [ValidateSet('start','stop','pause','resume','restart','status','urls','open','logs','doctor','nuke','help','vendor','health')]
  [string]$Command = 'help',

  [Parameter(Position = 1)]
  [ValidateSet('min','hitl','obs','all')]
  [string]$Profile = 'all',

  [Parameter(Position = 2, ValueFromRemainingArguments = $true)]
  [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# ---------- compose file groups ----------
$F_NET    = @('-f','compose/00-network.yml')
$F_MIN    = $F_NET + @(
  '-f','compose/10-state.yml',
  '-f','compose/20-platform.yml',
  '-f','compose/30-data.yml',
  '-f','compose/40-capability.yml',
  '-f','compose/50-app.yml'
)
$F_HITL   = $F_MIN + @('-f','compose/60-hitl.yml')
$F_OBS    = $F_NET + @('-f','compose/70-observability.yml')
$F_PORTAL = $F_NET + @('-f','compose/80-portal.yml')
$F_ALL    = $F_HITL + @('-f','compose/70-observability.yml','-f','compose/80-portal.yml')

function Get-ComposeArgs([string]$prof) {
  switch ($prof) {
    'min'  { return $F_MIN }
    'hitl' { return $F_HITL }
    'obs'  { return $F_OBS }
    'all'  { return $F_ALL }
  }
}

$EnvFile  = Join-Path $PSScriptRoot '.env'
$BaseArgs = @('compose','--env-file', $EnvFile)

# ---------- helpers ----------
function Write-Step($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "OK  $msg"  -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "!!  $msg"  -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "ERR $msg"  -ForegroundColor Red }

function Invoke-Compose([string[]]$files, [string[]]$action) {
  $args = $BaseArgs + $files + $action
  Write-Verbose ("docker " + ($args -join ' '))
  & docker @args
  if ($LASTEXITCODE -ne 0) { throw "docker compose exited with $LASTEXITCODE" }
}

function Test-DockerReady {
  try {
    $null = & docker info --format '{{.ServerVersion}}' 2>$null
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}

function Test-EnvFile {
  if (-not (Test-Path $EnvFile)) {
    Write-Err ".env not found. Copy .env.example to .env first:"
    Write-Host "    Copy-Item .env.example .env"
    return $false
  }
  return $true
}

function Test-PortFree([int]$port) {
  $busy = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
  return (-not $busy)
}

function Sync-Vendor {
  Write-Step "Vendoring packages/contracts into service build contexts"
  foreach ($svc in @('langgraph-app')) {
    $dst = Join-Path $PSScriptRoot "src\services\$svc\vendor\text2sql-contracts"
    if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    Copy-Item -Recurse -Force (Join-Path $PSScriptRoot 'src\packages\contracts\*') $dst
  }
  Write-Ok "contracts copied"
}

function Wait-Healthy([string]$url, [string]$name, [int]$timeoutSec = 120) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
      if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) {
        Write-Ok "$name ready ($url)"
        return $true
      }
    } catch { Start-Sleep -Milliseconds 1500 }
  }
  Write-Warn2 "$name did not become ready within ${timeoutSec}s ($url)"
  return $false
}

# ---------- service URL catalog ----------
$Urls = [ordered]@{
  'Portainer (master control)' = @{ url = 'http://localhost:9000'; note = 'first visit: create admin user (>=12 chars)' }
  'Grafana (4-role dashboards)' = @{ url = 'http://localhost:3001'; note = 'admin / admin_dev_only  (or anonymous Viewer)' }
  'LangGraph API'              = @{ url = 'http://localhost:8080/healthz'; note = 'OpenAPI: /docs   metrics: /metrics' }
  'Langfuse (LLM traces)'      = @{ url = 'http://localhost:3000'; note = 'see .env LANGFUSE_*' }
  'Argilla (HITL)'             = @{ url = 'http://localhost:6900'; note = 'owner / 12345678  apikey owner.apikey' }
  'Trino (query engine)'       = @{ url = 'http://localhost:8081'; note = 'header X-Trino-User: alice@bank' }
  'LiteLLM proxy'              = @{ url = 'http://localhost:4000/health/liveliness'; note = 'master key in .env' }
  'Prometheus'                 = @{ url = 'http://localhost:9090'; note = 'targets, alerts, PromQL' }
  'Alertmanager'               = @{ url = 'http://localhost:9093'; note = '' }
  'Loki (logs API)'            = @{ url = 'http://localhost:3100/ready'; note = 'use Grafana > Explore > Loki' }
  'Tempo (traces API)'         = @{ url = 'http://localhost:3200/ready'; note = 'use Grafana > Explore > Tempo' }
}

# ---------- commands ----------
function Cmd-Help {
  Write-Host @"
Text2SQL Platform control script
Usage:  .\t2sql.ps1 <command> [profile]

Commands:
  start    [min|hitl|obs|all]   build (if needed) and bring stack up
  stop     [profile]            stop containers, keep volumes
  pause    [profile]            docker pause (freeze processes, keep RAM/state)
  resume   [profile]            docker unpause
  restart  [profile]            stop then start
  status                        list all containers from this project
  urls                          print every UI URL + credentials
  open                          open the master control UI (Portainer)
  logs     [service]            follow logs (all services if omitted)
  health                        curl healthz on every service
  doctor                        preflight checks (docker, .env, key ports)
  vendor                        re-copy packages/contracts into service builds
  nuke                          docker compose down -v  (DESTROYS volumes; asks)

Profiles (default = all):
  hitl  = min + Argilla
  obs   = observability stack only (prom + alertmanager + loki + tempo + grafana + otel-collector)
  all   = everything above + Portainer

Examples:
  .\t2sql.ps1 start              # full stack, ~3-4 min first time
  .\t2sql.ps1 pause              # freeze every container
  .\t2sql.ps1 resume             # thaw
  .\t2sql.ps1 logs langgraph-app
  .\t2sql.ps1 urls
"@
}

function Cmd-Doctor {
  Write-Step "Doctor: preflight checks"
  $ok = $true

  if (Test-DockerReady) { Write-Ok "Docker engine reachable" }
  else { Write-Err "Docker engine not reachable. Start Docker Desktop."; $ok = $false }

  if (Test-EnvFile) { Write-Ok ".env present" } else { $ok = $false }

  $ports = @(5432,5433,3202,4000,8080,8081,3203,3204,9090,9093,3100,3200,3204,4317,4318,9000,9001,6900)
  $busy = @()
  foreach ($p in $ports) { if (-not (Test-PortFree $p)) { $busy += $p } }
  if ($busy.Count -eq 0) { Write-Ok "all required ports free" }
  else { Write-Warn2 ("ports already in use: " + ($busy -join ', ') + "  (only a problem if a non-t2sql process holds them)") }

  if (-not (Test-Path (Join-Path $PSScriptRoot 'src\packages\contracts\text2sql_contracts'))) {
    Write-Err "src/packages/contracts/text2sql_contracts missing"; $ok = $false
  } else { Write-Ok "src/packages/contracts present" }

  if ($ok) { Write-Ok "Doctor: ready to start"; exit 0 } else { Write-Err "Doctor: blockers above"; exit 1 }
}

function Cmd-Start {
  if (-not (Test-DockerReady)) { Write-Err "Docker not running"; exit 1 }
  if (-not (Test-EnvFile))     { exit 1 }

  $files = Get-ComposeArgs $Profile

  # vendor only when an app image is in the profile
  if ($Profile -in 'min','hitl','all') { Sync-Vendor }

  # Wire OTel endpoint automatically when obs is part of the profile
  if ($Profile -in 'obs','all') {
    $env:OTEL_EXPORTER_OTLP_ENDPOINT = 'http://otel-collector:4318'
    Write-Ok "OTEL_EXPORTER_OTLP_ENDPOINT = $($env:OTEL_EXPORTER_OTLP_ENDPOINT) (process scope)"
  }

  Write-Step "docker compose up -d --build  (profile=$Profile)"
  Invoke-Compose $files @('up','-d','--build')

  Write-Step "Waiting for core endpoints to become healthy"
  if ($Profile -in 'min','hitl','all') {
    Wait-Healthy 'http://localhost:8080/healthz' 'langgraph-app' 180 | Out-Null
    Wait-Healthy 'http://localhost:8081/v1/info' 'trino' 180 | Out-Null
    Wait-Healthy 'http://localhost:3030/' 'web-ui' 120 | Out-Null
  }
  if ($Profile -in 'obs','all') {
    Wait-Healthy 'http://localhost:9090/-/ready' 'prometheus' 120 | Out-Null
    Wait-Healthy 'http://localhost:3001/api/health' 'grafana' 120 | Out-Null
  }
  if ($Profile -eq 'all') {
    Wait-Healthy 'http://localhost:9000/' 'portainer' 60 | Out-Null
  }

  Write-Host ""
  Cmd-Urls
  Write-Host ""
  Write-Ok "Stack is up. Master control: http://localhost:9000  (Portainer)"
}

function Cmd-Stop    { Invoke-Compose (Get-ComposeArgs $Profile) @('stop') }
function Cmd-Pause   { Invoke-Compose (Get-ComposeArgs $Profile) @('pause') ;  Write-Ok "paused (use 'resume' to thaw)" }
function Cmd-Resume  { Invoke-Compose (Get-ComposeArgs $Profile) @('unpause'); Write-Ok "resumed" }
function Cmd-Restart { Cmd-Stop; Cmd-Start }

function Cmd-Status {
  Invoke-Compose $F_ALL @('ps')
}

function Cmd-Logs {
  $svc = if ($Rest) { $Rest } else { @() }
  Invoke-Compose (Get-ComposeArgs $Profile) (@('logs','-f','--tail=100') + $svc)
}

function Cmd-Health {
  $checks = @(
    @{n='trino';     u='http://localhost:8081/v1/info'},
    @{n='litellm';   u='http://localhost:4000/health/liveliness'},
    @{n='langfuse';  u='http://localhost:3000/api/public/health'},
    @{n='langgraph'; u='http://localhost:8080/healthz'},
    @{n='prometheus';u='http://localhost:9090/-/ready'},
    @{n='grafana';   u='http://localhost:3001/api/health'},
    @{n='loki';      u='http://localhost:3100/ready'},
    @{n='tempo';     u='http://localhost:3200/ready'},
    @{n='portainer'; u='http://localhost:9000/'}
  )
  foreach ($c in $checks) {
    try {
      $r = Invoke-WebRequest -Uri $c.u -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
      Write-Host ("[{0,-11}] {1}  {2}" -f $c.n, $r.StatusCode, $c.u) -ForegroundColor Green
    } catch {
      Write-Host ("[{0,-11}] DOWN     {1}" -f $c.n, $c.u) -ForegroundColor Red
    }
  }
}

function Cmd-Urls {
  Write-Host "Service URLs (copy/paste into browser):" -ForegroundColor Cyan
  foreach ($k in $Urls.Keys) {
    $v = $Urls[$k]
    "{0,-32} {1,-40} {2}" -f $k, $v.url, $v.note | Write-Host
  }
}

function Cmd-Open {
  Write-Step "Opening Portainer (master control UI)"
  Start-Process 'http://localhost:9000'
}

function Cmd-Nuke {
  Write-Warn2 "This will run 'docker compose down -v' on the FULL stack and DESTROY all named volumes (postgres, grafana, prometheus, tempo, loki, portainer, etc.)."
  $a = Read-Host "Type 'NUKE' to confirm"
  if ($a -ne 'NUKE') { Write-Host "aborted."; return }
  Invoke-Compose $F_ALL @('down','-v','--remove-orphans')
  Write-Ok "all volumes destroyed."
}

# ---------- dispatch ----------
switch ($Command) {
  'help'    { Cmd-Help }
  'doctor'  { Cmd-Doctor }
  'start'   { Cmd-Start }
  'stop'    { Cmd-Stop }
  'pause'   { Cmd-Pause }
  'resume'  { Cmd-Resume }
  'restart' { Cmd-Restart }
  'status'  { Cmd-Status }
  'logs'    { Cmd-Logs }
  'health'  { Cmd-Health }
  'urls'    { Cmd-Urls }
  'open'    { Cmd-Open }
  'vendor'  { Sync-Vendor }
  'nuke'    { Cmd-Nuke }
  default   { Cmd-Help }
}
