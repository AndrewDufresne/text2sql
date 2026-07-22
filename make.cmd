@echo off
REM Windows wrapper for the Phase 1 Makefile targets.
REM Usage: make up-min  /  make down-min  /  make ps  /  make health  /  make smoke-trino
REM        make logs    /  make test-unit /  make test-e2e /  make clean

setlocal ENABLEDELAYEDEXPANSION

REM --- compose file groups (mirror the Makefile) ---
set "COMPOSE=docker compose --env-file .env"
set "F_MIN=-f compose/00-network.yml -f compose/10-state.yml -f compose/20-platform.yml -f compose/30-data.yml -f compose/40-capability.yml -f compose/50-app.yml"
set "F_HITL=%F_MIN% -f compose/60-hitl.yml"
set "F_OBS=-f compose/00-network.yml -f compose/70-observability.yml"
set "F_PORTAL=-f compose/00-network.yml -f compose/80-portal.yml"
set "F_FULL=%F_HITL% -f compose/70-observability.yml -f compose/80-portal.yml"
set "F_DH=-f compose/00-network.yml -f compose/31-datahub.yml"

if "%~1"=="" goto :help
set "TARGET=%~1"

if /I "%TARGET%"=="help"        goto :help
if /I "%TARGET%"=="up-min"      goto :up_min
if /I "%TARGET%"=="vendor"      goto :vendor
if /I "%TARGET%"=="down-min"    goto :down_min
if /I "%TARGET%"=="logs"        goto :logs
if /I "%TARGET%"=="ps"          goto :ps
if /I "%TARGET%"=="health"      goto :health
if /I "%TARGET%"=="smoke-trino" goto :smoke_trino
if /I "%TARGET%"=="test-unit"   goto :test_unit
if /I "%TARGET%"=="test-e2e"    goto :test_e2e
if /I "%TARGET%"=="test-e2e-phase2" goto :test_e2e_phase2
if /I "%TARGET%"=="test-e2e-phase3" goto :test_e2e_phase3
if /I "%TARGET%"=="up-hitl"     goto :up_hitl
if /I "%TARGET%"=="down-hitl"   goto :down_hitl
if /I "%TARGET%"=="eval"        goto :eval
if /I "%TARGET%"=="argilla-bootstrap"   goto :argilla_bootstrap
if /I "%TARGET%"=="argilla-sync-golden" goto :argilla_sync_golden
if /I "%TARGET%"=="up-obs"      goto :up_obs
if /I "%TARGET%"=="down-obs"    goto :down_obs
if /I "%TARGET%"=="up-portal"   goto :up_portal
if /I "%TARGET%"=="down-portal" goto :down_portal
if /I "%TARGET%"=="up-all"      goto :up_all
if /I "%TARGET%"=="down-all"    goto :down_all
if /I "%TARGET%"=="health-obs"  goto :health_obs
if /I "%TARGET%"=="up-datahub"   goto :up_datahub
if /I "%TARGET%"=="down-datahub" goto :down_datahub
if /I "%TARGET%"=="datahub-ingest"   goto :datahub_ingest
if /I "%TARGET%"=="datahub-glossary" goto :datahub_glossary
if /I "%TARGET%"=="health-l3"   goto :health_l3
if /I "%TARGET%"=="test"        goto :test_all
if /I "%TARGET%"=="format"      goto :format
if /I "%TARGET%"=="lint"        goto :lint
if /I "%TARGET%"=="clean"       goto :clean

echo Unknown target: %TARGET%
goto :help

:help
echo make up-min       # bring up Phase 1 walking-skeleton stack
echo make down-min     # tear down (keeps volumes)
echo make logs         # follow logs
echo make ps           # list containers
echo make health       # ping all services
echo make smoke-trino  # SELECT count(*) FROM cib.client
echo make test         # all tests
echo make test-unit    # unit + contract tests only
echo make test-e2e     # walking skeleton E2E (requires up-min)
echo make up-obs       # bring up Phase 4 observability stack
echo make down-obs     # tear down observability
echo make up-portal    # bring up Portainer
echo make up-all       # bring up everything (Phase 1-4)
echo make health-obs   # check obs stack health
echo make up-datahub   # bring up DataHub stack (http://localhost:9002, ~3min warm-up)
echo make down-datahub # tear down DataHub
echo make datahub-ingest   # crawl postgres-cib into DataHub
echo make datahub-glossary # load CIB business-glossary terms
echo make health-l3    # check Cube + DataHub health
echo make clean        # down -v (drops volumes)
goto :eof

:up_min
call "%~f0" vendor
if errorlevel 1 exit /b 1
%COMPOSE% %F_MIN% up -d --build
goto :eof

:vendor
for %%S in (langgraph-app) do (
  if exist src\services\%%S\vendor\text2sql-contracts rmdir /S /Q src\services\%%S\vendor\text2sql-contracts
  mkdir src\services\%%S\vendor\text2sql-contracts >NUL 2>&1
  xcopy /E /I /Y /Q src\packages\contracts src\services\%%S\vendor\text2sql-contracts >NUL
)
echo [vendor] contracts copied into service build context
goto :eof

:down_min
%COMPOSE% %F_MIN% down
goto :eof

:logs
%COMPOSE% %F_MIN% logs -f --tail=100
goto :eof

:ps
%COMPOSE% %F_MIN% ps
goto :eof

:health
echo [trino]     & curl -fsS http://localhost:8081/v1/info
echo.
echo [litellm]   & curl -fsS http://localhost:4000/health/liveliness
echo.
echo [langfuse]  & curl -fsS http://localhost:3000/api/public/health
echo.
echo [langgraph] & curl -fsS http://localhost:8080/healthz
echo.
goto :eof

:smoke_trino
curl -s -X POST -H "X-Trino-User: alice@bank" -H "X-Trino-Catalog: cib" -H "X-Trino-Schema: public" --data "SELECT count(*) FROM client" http://localhost:8081/v1/statement
goto :eof

:test_unit
pushd src\services\langgraph-app
python -m pytest -m "not e2e" -v
popd
goto :eof

:test_e2e
python -m pytest tests\e2e -m walking_skeleton -v
goto :eof

:test_e2e_phase2
python -m pytest tests\e2e -m phase2 -v
goto :eof

:test_e2e_phase3
python -m pytest tests\e2e -m phase3 -v
goto :eof

:up_hitl
call "%~f0" vendor
if errorlevel 1 exit /b 1
%COMPOSE% %F_HITL% up -d --build
goto :eof

:down_hitl
%COMPOSE% %F_HITL% down
goto :eof

:eval
python tests\eval\run_eval.py --base-url http://localhost:8080 --golden tests\eval\golden_set.yaml --report tests\eval\report.json
goto :eof

:argilla_bootstrap
if "%ARGILLA_PORT%"==""     set "ARGILLA_PORT=6900"
if "%ARGILLA_API_KEY%"==""  set "ARGILLA_API_KEY=owner.apikey"
if "%ARGILLA_WORKSPACE%"=="" set "ARGILLA_WORKSPACE=admin"
if "%ARGILLA_DATASET%"==""   set "ARGILLA_DATASET=text2sql-feedback"
if "%EMBEDDING_DIM%"==""    set "EMBEDDING_DIM=384"
python -m tools.argilla.bootstrap --url http://localhost:%ARGILLA_PORT% --api-key %ARGILLA_API_KEY% --workspace %ARGILLA_WORKSPACE% --dataset %ARGILLA_DATASET% --vector-dim %EMBEDDING_DIM%
goto :eof

:argilla_sync_golden
if "%ARGILLA_PORT%"==""     set "ARGILLA_PORT=6900"
if "%ARGILLA_API_KEY%"==""  set "ARGILLA_API_KEY=owner.apikey"
if "%ARGILLA_WORKSPACE%"=="" set "ARGILLA_WORKSPACE=admin"
if "%ARGILLA_DATASET%"==""   set "ARGILLA_DATASET=text2sql-feedback"
python -m tools.argilla.sync_golden --url http://localhost:%ARGILLA_PORT% --api-key %ARGILLA_API_KEY% --workspace %ARGILLA_WORKSPACE% --dataset %ARGILLA_DATASET% --golden tests\eval\golden_set.yaml
goto :eof

:up_obs
%COMPOSE% %F_OBS% up -d
goto :eof

:down_obs
%COMPOSE% %F_OBS% down
goto :eof

:up_portal
%COMPOSE% %F_PORTAL% up -d
goto :eof

:down_portal
%COMPOSE% %F_PORTAL% down
goto :eof

:up_all
call "%~f0" vendor
if errorlevel 1 exit /b 1
%COMPOSE% %F_FULL% up -d --build
goto :eof

:down_all
%COMPOSE% %F_FULL% down
goto :eof

:health_obs
echo [prometheus]   & curl -fsS http://localhost:9090/-/ready
echo.
echo [alertmanager] & curl -fsS http://localhost:9093/-/ready
echo.
echo [loki]         & curl -fsS http://localhost:3100/ready
echo.
echo [tempo]        & curl -fsS http://localhost:3200/ready
echo.
echo [grafana]      & curl -fsS http://localhost:3001/api/health
echo.
echo [langgraph /metrics] & curl -fsS http://localhost:8080/metrics ^| more +1
goto :eof

:test_all
call "%~f0" test-unit
if errorlevel 1 exit /b 1
call "%~f0" test-e2e
goto :eof

:format
ruff format services packages tests
goto :eof

:lint
ruff check services packages tests
goto :eof

:clean
%COMPOSE% %F_MIN% down -v
goto :eof

goto :eof

goto :eof

:up_datahub
%COMPOSE% %F_DH% up -d
goto :eof

:down_datahub
%COMPOSE% %F_DH% down
goto :eof

:datahub_ingest
docker run --rm --network t2sql-net --env-file .env -v "%CD%\config\datahub:/config/datahub:ro" acryldata/datahub-ingestion:v0.13.3 ingest -c /config/datahub/recipes/postgres-cib.yml
goto :eof

:datahub_glossary
docker run --rm --network t2sql-net --env-file .env -v "%CD%\config\datahub:/config/datahub:ro" acryldata/datahub-ingestion:v0.13.3 ingest -c /config/datahub/recipes/glossary.yml
goto :eof

:health_l3
echo.
echo [dh-gms]   & curl -fsS http://localhost:8090/health
echo.
echo [dh-front] & curl -fsS -o NUL -w "%%{http_code}\n" http://localhost:9002/admin
goto :eof
