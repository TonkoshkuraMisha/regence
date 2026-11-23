# --- FILE: start_dev.ps1 ---

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
$frontendDir = Join-Path $root "frontend"
$stockfishBin = Join-Path $root "bin\stockfish.exe"

Write-Host "=== Starting the Regence development environment ===" -ForegroundColor Cyan

# 1. Auto-create .env files from templates if they are not on this machine yet
if (-not (Test-Path (Join-Path $root ".env")) -and (Test-Path (Join-Path $root ".env.example")))
{
    Copy-Item (Join-Path $root ".env.example") (Join-Path $root ".env")
    Write-Host "[+] Created the root .env from .env.example" -ForegroundColor Green
}
if (-not (Test-Path (Join-Path $frontendDir ".env")) -and (Test-Path (Join-Path $frontendDir ".env.example")))
{
    Copy-Item (Join-Path $frontendDir ".env.example") (Join-Path $frontendDir ".env")
    Write-Host "[+] Created frontend/.env from the template" -ForegroundColor Green
}

# 2. Stop old background jobs and node processes and free ports 8000 and 3000
Get-Job -Name "RegenceBackend", "RegenceWorker", "RegenceFrontend" -ErrorAction SilentlyContinue | Stop-Job -PassThru | Remove-Job -Force -ErrorAction SilentlyContinue

# Processes left over from previous runs from OTHER windows (Get-Job sees only the jobs of its own session):
# this project's Celery worker (it has no port) and Vite from the frontend folder. Other people's node processes
# (for example, Claude Code itself or other projects) are not touched - only those whose command line points here.
$stale = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and (
        ($_.Name -like "python*" -and $_.CommandLine -like "*celery*src.worker.celery_app*") -or
        ($_.Name -eq "node.exe" -and $_.CommandLine -like "*$frontendDir*vite*")
    )
}
foreach ($p in $stale)
{
    Write-Host "[*] Stopping the old process $( $p.Name ) (PID: $( $p.ProcessId ))..." -ForegroundColor DarkYellow
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}

# This project's server (uvicorn src.main:app, including one started by hand) and its child processes: with --reload the port
# is held not by the process visible in the command line, so descendants are killed too, otherwise port 8000 stays busy.
$uv = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine -like "*uvicorn*src.main:app*"
}
$uvIds = @($uv | ForEach-Object { $_.ProcessId })
$kids = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $uvIds -contains $_.ParentProcessId }
foreach ($p in @($uv) + @($kids))
{
    if ($p)
    {
        Write-Host "[*] Stopping the old server $( $p.Name ) (PID: $( $p.ProcessId ))..." -ForegroundColor DarkYellow
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

# Free the ports and WAIT until they are really free (up to 10 s): otherwise the new server fails with "port in use",
# and the script sees only "port 8000 did not open" with no reason.
foreach ($port in @(8000, 3000))
{
    for ($try = 0; $try -lt 10; $try++)
    {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if (-not $conns) { break }
        foreach ($procId in ($conns | Select-Object -ExpandProperty OwningProcess -Unique))
        {
            if ($procId -gt 0)
            {
                Write-Host "[*] Freeing port $port (PID: $procId)..." -ForegroundColor DarkYellow
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Seconds 1
    }
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    {
        Write-Host "[!] Port $port is held by a process that could not be stopped. Close it and retry (netstat -ano | findstr :$port)." -ForegroundColor Red
        exit 1
    }
}

# 3. Auto-check and creation of the Python virtual environment on any machine
if (-not (Test-Path $pythonExe))
{
    Write-Host "[*] Creating the Python environment (.venv) via uv..." -ForegroundColor Yellow
    if (-not (Get-Command uv -ErrorAction SilentlyContinue))
    {
        Write-Host "[!] uv not found. Install: powershell -ExecutionPolicy ByPass -c ""irm https://astral.sh/uv/install.ps1 | iex""" -ForegroundColor Red
        exit 1
    }
    Push-Location $root
    & uv sync --frozen
    Pop-Location
}

# 4. Auto-check and download of the Stockfish 19 engine
if (-not (Test-Path $stockfishBin))
{
    Write-Host "[*] Stockfish binary not found in bin/. Downloading..." -ForegroundColor Yellow
    & $pythonExe (Join-Path $root "scripts\setup_stockfish.py")
}

# 4.1. Finding Node.js. The PyCharm terminal may inherit a PATH without the Node.js folder (the IDE was started before Node was installed
# or with an old environment) - then we look in standard places and add the folder to the PATH of this process and child windows.
$npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $npmCmd)
{
    $npmCmd = @(
        (Join-Path $env:ProgramFiles "nodejs\npm.cmd"),
        (Join-Path ${env:ProgramFiles(x86)} "nodejs\npm.cmd"),
        (Join-Path $env:APPDATA "nvm\nodejs\npm.cmd"),
        (Join-Path $env:LOCALAPPDATA "Programs\nodejs\npm.cmd")
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}
if (-not $npmCmd)
{
    Write-Host "[!] Node.js (npm.cmd) not found. Install Node.js LTS and restart PyCharm." -ForegroundColor Red
    exit 1
}
$nodeDir = Split-Path $npmCmd -Parent
if (($env:Path -split ";") -notcontains $nodeDir)
{
    $env:Path = "$nodeDir;$env:Path"
}

# 5. Auto-check of node_modules in the frontend
if (-not (Test-Path (Join-Path $frontendDir "node_modules")))
{
    Write-Host "[*] Installing the frontend npm dependencies..." -ForegroundColor Yellow
    Set-Location $frontendDir
    # npm.cmd, not npm: the npm.ps1 wrapper does not run when scripts are prohibited (the default execution policy).
    & $npmCmd install
    Set-Location $root
}

# 6. Bringing up the database and Redis through Docker
Write-Host "[*] Checking Docker and containers (PostgreSQL: 15432, Redis: 6379)..." -ForegroundColor Cyan
if (-not (Get-Command docker -ErrorAction SilentlyContinue))
{
    Write-Host "[!] The docker command was not found. Install Docker Desktop and run the script again." -ForegroundColor Red
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0)
{
    $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktop)
    {
        Write-Host "[*] Docker Desktop is not running - starting it and waiting (up to 120 s)..." -ForegroundColor Yellow
        Start-Process $dockerDesktop
        for ($i = 0; $i -lt 60; $i++)
        {
            Start-Sleep -Seconds 2
            docker info *> $null
            if ($LASTEXITCODE -eq 0) { break }
        }
    }
    if ($LASTEXITCODE -ne 0)
    {
        Write-Host "[!] Docker is unavailable. Start Docker Desktop, wait for the 'Engine running' status and retry." -ForegroundColor Red
        exit 1
    }
}
docker compose up -d db redis
if ($LASTEXITCODE -ne 0)
{
    Write-Host "[!] Failed to bring up the db and redis containers (docker compose up). Startup aborted." -ForegroundColor Red
    exit 1
}

# 6.1. Waiting for PostgreSQL to be ready: the container port opens earlier than the database accepts connections
$dbReady = $false
for ($i = 0; $i -lt 30; $i++)
{
    docker compose exec -T db pg_isready *> $null
    if ($LASTEXITCODE -eq 0)
    {
        $dbReady = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $dbReady)
{
    Write-Host "[!] PostgreSQL did not start accepting connections within 30 seconds. See: docker compose logs db" -ForegroundColor Red
    exit 1
}

# 7. Applying DB migrations
Write-Host "[*] Applying database migrations (Alembic)..." -ForegroundColor Cyan
& $pythonExe -m alembic upgrade head
if ($LASTEXITCODE -ne 0)
{
    Write-Host "[!] Alembic migrations finished with an error (see the output above). Startup aborted." -ForegroundColor Red
    exit 1
}

# 7.0. Puzzle database (a selection from the open lichess database, data/puzzles); puzzles already loaded are skipped
Write-Host "[*] Loading the puzzle database..." -ForegroundColor Cyan
& $pythonExe -m scripts.import_puzzles
if ($LASTEXITCODE -ne 0)
{
    Write-Host "[!] Loading the puzzle database finished with an error (see the output above). Startup aborted." -ForegroundColor Red
    exit 1
}

# 7.1. Auto-check and top-up of the game archives of 21 world champions
$steinitzPgn = Join-Path $root "src\db\data\pgns\Steinitz.pgn"
if (-not (Test-Path $steinitzPgn))
{
    Write-Host "[*] The world champions' PGN archives were not found on this PC. Downloading and importing into the DB..." -ForegroundColor Yellow
    & $pythonExe -m src.db.seed
}

# 8. Start the FastAPI backend in the background
Write-Host "[+] Starting the FastAPI backend (port 8000)..." -ForegroundColor Green
# Server log: the job console is not visible, so a rotating json file logs/api.jsonl (src/core/logging_setup.py);
# analysis - python scripts/trace_logs.py game_id=<id> logs/api.jsonl logs/worker.jsonl.
New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null
Start-Job -Name "RegenceBackend" -ScriptBlock {
    param($py, $r)
    Set-Location $r
    $env:LOG_FILE = Join-Path $r "logs\api.jsonl"
    & $py -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
} -ArgumentList $pythonExe, $root | Out-Null

# 8.0. Start the Celery worker (background analysis of finished games) in the background.
# On Windows the Celery prefork pool does not work - we use solo (one task at a time).
Write-Host "[+] Starting the Celery worker (background game analysis)..." -ForegroundColor Green
Start-Job -Name "RegenceWorker" -ScriptBlock {
    param($py, $r)
    Set-Location $r
    $env:LOG_FILE = Join-Path $r "logs\worker.jsonl"
    # One worker listens to both queues (analysis - game analysis, simulation - bot games in tournaments).
    & $py -m celery -A src.worker.celery_app worker --loglevel=INFO --pool=solo -Q analysis,simulation
} -ArgumentList $pythonExe, $root | Out-Null

# 8.1. Start the Vite frontend in a separate visible terminal window
Write-Host "[+] Starting the Vite frontend (port 3000 in a new window)..." -ForegroundColor Green
# The window is PowerShell 7 (pwsh) if present; otherwise Windows PowerShell 5.1 (powershell is always 5.1). In 5.1 scripts, and
# with them the npm.ps1 wrapper, are prohibited by default: hence npm.cmd and -ExecutionPolicy Bypass for this process only
# (system settings are not changed).
$frontendShell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
# Vite output is duplicated into frontend/vite-dev.log (*.log is in .gitignore): if the window fails to bring the server up, the script shows
# the log tail here, and not only in a separate window that is easy to lose behind others.
$viteLog = Join-Path $frontendDir "vite-dev.log"
Remove-Item $viteLog -Force -ErrorAction SilentlyContinue
# The folder is set through -WorkingDirectory, not through cd inside -Command: from the PyCharm terminal the window opened at the project
# root, and npm failed with ENOENT on package.json. The path to package.json is also passed explicitly (--prefix) - in case
# the shell still changes the directory at startup.
Start-Process $frontendShell -WorkingDirectory $frontendDir -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", "`$env:Path = '$nodeDir;' + `$env:Path; Set-Location -LiteralPath '$frontendDir'; & '$npmCmd' --prefix '$frontendDir' run dev 2>&1 | Tee-Object -FilePath '$viteLog'"

# 9. Wait for ports 3000 (Vite) and 8000 (backend) to actually open before launching the browser.
# The first Vite start (dependency optimisation) and uvicorn --reload can take noticeably more than 15 seconds.
$waitSeconds = 60
$frontendReady = $false
$backendReady = $false
for ($i = 0; $i -lt $waitSeconds * 2; $i++)
{
    if (-not $frontendReady -and (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)) { $frontendReady = $true }
    if (-not $backendReady -and (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) { $backendReady = $true }
    if ($frontendReady -and $backendReady) { break }
    # The backend job crashed at once (an import error, etc.) - there is no point waiting for the port
    if (-not $backendReady -and (Get-Job -Name "RegenceBackend" -ErrorAction SilentlyContinue).State -in @("Failed", "Completed", "Stopped")) { break }
    Start-Sleep -Milliseconds 500
}
$workerJob = Get-Job -Name "RegenceWorker" -ErrorAction SilentlyContinue
$workerAlive = $workerJob -and $workerJob.State -eq "Running"

if ($frontendReady)
{
    Write-Host "[+] Opening the browser at http://127.0.0.1:3000 ..." -ForegroundColor Magenta
    Start-Process "http://127.0.0.1:3000"
}
else
{
    Write-Host "[!] Port 3000 did not respond within $waitSeconds seconds. Check the opened Vite terminal window." -ForegroundColor Red
    if (Test-Path $viteLog)
    {
        Write-Host "    Last lines of frontend/vite-dev.log:" -ForegroundColor Red
        Get-Content $viteLog -Tail 20 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    }
    else
    {
        Write-Host "    The Vite log is empty: the window did not start npm (no npm.cmd in PATH or the window closed at once)." -ForegroundColor Red
    }
}
if (-not $backendReady)
{
    Write-Host "[!] The backend did not open port 8000. Logs: Receive-Job -Name RegenceBackend -Keep" -ForegroundColor Red
}
if (-not $workerAlive)
{
    Write-Host "[!] The Celery worker stopped. Logs: Receive-Job -Name RegenceWorker -Keep" -ForegroundColor Red
}

$allOk = $frontendReady -and $backendReady -and $workerAlive
$statusColor = if ($allOk) { "Green" } else { "Yellow" }
Write-Host "========================================================" -ForegroundColor $statusColor
if ($allOk)
{
    Write-Host " All services started! The local server is running." -ForegroundColor Green
}
else
{
    Write-Host " Startup finished with problems - see the [!] messages above." -ForegroundColor Yellow
}
Write-Host " Frontend: http://127.0.0.1:3000" -ForegroundColor Cyan
Write-Host " API Docs: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host " Backend log view: Receive-Job -Name RegenceBackend -Keep" -ForegroundColor Gray
Write-Host " Celery worker logs:   Receive-Job -Name RegenceWorker -Keep" -ForegroundColor Gray
Write-Host " To stop the backend: Get-Job | Stop-Job; Get-Job | Remove-Job" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Green