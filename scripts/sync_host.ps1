# --- FILE: scripts/sync_host.ps1 ---
#
# Synchronising the workplace between hosts (gaming laptop, desktop PC, work laptop).
#
#   .\scripts\sync_host.ps1           — "arriving": pull code, dependencies, engine, DB, data
#   .\scripts\sync_host.ps1 -Resume   — the same + switch to the latest WIP branch from another host
#   .\scripts\sync_host.ps1 -Leave    — "leaving": commit and push everything unfinished
#   .\scripts\sync_host.ps1 -GitOnly  — git only (fast, no venv/npm/Docker)
#
# Secrets (.env), venv, node_modules, Stockfish and PGN archives do not go into git - the script
# restores them on any host; unfinished work goes to the branch wip/<host>-<time>.

[CmdletBinding()]
param(
    [switch]$Leave,
    [switch]$Resume,
    [switch]$GitOnly,
    [string]$Message = ""
)

$ErrorActionPreference = "Continue"
# Non-ASCII text in the output of git and of the script itself in Windows PowerShell 5.1.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
# Python scripts print non-ASCII text: without this, output to a non-console fails on cp1252.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
$frontendDir = Join-Path $root "frontend"
$hostTag = ($env:COMPUTERNAME).ToLower() -replace '[^a-z0-9-]', '-'
$protectedBranches = @("dev", "master")
$problems = New-Object System.Collections.Generic.List[string]

function Step([string]$text) { Write-Host "`n[*] $text" -ForegroundColor Cyan }
function Ok([string]$text) { Write-Host "    [+] $text" -ForegroundColor Green }
function Info([string]$text) { Write-Host "    $text" -ForegroundColor Gray }
function Warn([string]$text) {
    Write-Host "    [!] $text" -ForegroundColor Yellow
    $script:problems.Add($text)
}

# A simple function (not advanced): -c, --quiet and other flags go to git as is through $args.
function Invoke-Git {
    $out = & git @args
    if ($LASTEXITCODE -ne 0) { throw "git $($args -join ' ') exited with code $LASTEXITCODE" }
    return $out
}

function CurrentBranch { return (& git rev-parse --abbrev-ref HEAD).Trim() }

function HasUpstream {
    & git rev-parse --abbrev-ref --symbolic-full-name "@{u}" *> $null
    return $LASTEXITCODE -eq 0
}

function DirtyFiles { return @(& git status --porcelain) | Where-Object { $_ } }

function FileHash([string[]]$paths) {
    $existing = $paths | Where-Object { Test-Path $_ }
    if (-not $existing) { return "" }
    return (($existing | ForEach-Object { (Get-FileHash $_ -Algorithm SHA256).Hash }) -join "")
}

# Keys from KEY=VALUE, without comments and blank lines.
function EnvKeys([string]$path) {
    if (-not (Test-Path $path)) { return @() }
    return Get-Content $path | Where-Object { $_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=' } |
        ForEach-Object { $Matches[1] }
}

# Local branches that have unpushed commits or no upstream.
function UnpushedBranches {
    $result = @()
    foreach ($line in (& git for-each-ref refs/heads --format="%(refname:short)|%(upstream:short)|%(upstream:track)")) {
        $name, $upstream, $track = $line -split '\|', 3
        if (-not $upstream) { $result += "$name (not on GitHub)" }
        elseif ($track -match 'ahead') { $result += "$name $track" }
    }
    return $result
}

# ---------------------------------------------------------------------------------------------
# "Leaving" mode
# ---------------------------------------------------------------------------------------------
function Invoke-Leave {
    Write-Host "=== Regence: leaving host $hostTag ===" -ForegroundColor Cyan

    Step "Fetching the GitHub state"
    Invoke-Git fetch --prune --quiet

    $branch = CurrentBranch
    $dirty = DirtyFiles
    if ($dirty) {
        Step "Uncommitted changes ($(@($dirty).Count) file(s))"
        $dirty | ForEach-Object { Info $_ }

        if ($protectedBranches -contains $branch) {
            # dev/master are not littered with WIP commits: the work goes to a separate branch.
            $wipBranch = "wip/$hostTag-$(Get-Date -Format 'yyyyMMdd-HHmm')"
            Invoke-Git switch --quiet -c $wipBranch
            Ok "Created branch $wipBranch (from $branch)"
            $branch = $wipBranch
        }
        $text = if ($Message) { $Message } else { "unfinished work" }
        Invoke-Git add -A
        Invoke-Git commit --quiet -m "wip($hostTag): $text"
        Ok "Committed to $branch"
    }
    else {
        Ok "No uncommitted changes"
    }

    Step "Pushing branch $branch to GitHub"
    if (HasUpstream) {
        Invoke-Git push --quiet
    }
    else {
        Invoke-Git push --quiet -u origin $branch
    }
    Ok "$branch pushed"

    $leftovers = UnpushedBranches
    if ($leftovers) {
        Warn "Unpushed work in other branches (push it if you need it on other hosts): $($leftovers -join '; ')"
    }
    $stashes = @(& git stash list)
    if ($stashes) {
        Warn "There is a stash ($($stashes.Count)) - it lives only on this host: git stash list"
    }

    Summary "You can leave. On the other host: .\scripts\sync_host.ps1 -Resume"
}

# ---------------------------------------------------------------------------------------------
# "Arriving" mode
# ---------------------------------------------------------------------------------------------
function Sync-Git {
    Step "Git: repository settings"
    # Locally for the repository, so as not to touch other people's global settings.
    Invoke-Git config pull.rebase true
    Invoke-Git config fetch.prune true
    Invoke-Git config rebase.autoStash true
    Ok "pull.rebase=true, fetch.prune=true, rebase.autoStash=true"
    Info "Commit author on this host: $(& git config user.name) <$(& git config user.email)>"

    Step "Git: fetching changes from GitHub"
    Invoke-Git fetch --prune --quiet

    if ($Resume) {
        $wip = @(& git for-each-ref refs/remotes/origin/wip --sort=-committerdate --format="%(refname:lstrip=3)")
        if (-not $wip) {
            Warn "No WIP branches on GitHub - staying on $(CurrentBranch)"
        }
        elseif (DirtyFiles) {
            Warn "There are uncommitted changes - not switching to $($wip[0]). Commit them first."
        }
        else {
            $target = $wip[0]
            if (& git rev-parse --verify --quiet "refs/heads/$target") {
                Invoke-Git switch --quiet $target
            }
            else {
                Invoke-Git switch --quiet --track "origin/$target"
            }
            Ok "Switched to $target"
        }
    }

    $branch = CurrentBranch
    if (HasUpstream) {
        $before = (& git rev-parse HEAD).Trim()
        & git pull --quiet
        if ($LASTEXITCODE -ne 0) {
            Warn "git pull failed (a conflict?). Resolve manually: git status"
            return
        }
        $after = (& git rev-parse HEAD).Trim()
        if ($before -eq $after) { Ok "$branch is up to date" }
        else { Ok "$branch updated: $(@(& git rev-list "$before..$after").Count) new commit(s)" }

        $ahead = [int](& git rev-list --count "@{u}..HEAD")
        if ($ahead -gt 0) { Warn "$branch has $ahead unpushed commit(s) - run git push" }
    }
    else {
        Warn "Branch $branch has no upstream on GitHub - it exists only on this host"
    }

    # We update dev even if we work in another branch: new branches are created from it.
    foreach ($b in $protectedBranches) {
        if ($b -eq $branch) { continue }
        $behind = & git rev-list --count "$b..origin/$b" 2>$null
        $aheadB = & git rev-list --count "origin/$b..$b" 2>$null
        if ($LASTEXITCODE -ne 0) { continue }
        if ([int]$behind -gt 0 -and [int]$aheadB -eq 0) {
            Invoke-Git fetch --quiet origin "${b}:${b}"
            Ok "Local $b pulled (+$behind)"
        }
        elseif ([int]$aheadB -gt 0) {
            Warn "Local $b has $aheadB unpushed commit(s)"
        }
    }

    $wipOthers = @(& git for-each-ref refs/remotes/origin/wip --sort=-committerdate --format="%(refname:lstrip=3)  %(committerdate:relative)")
    if ($wipOthers -and -not $Resume) {
        Info "Unfinished work from other hosts (to continue: -Resume):"
        $wipOthers | ForEach-Object { Info "  $_" }
    }
}

function Sync-Env {
    Step "Secrets and settings (.env)"
    foreach ($pair in @(@($root, "root"), @($frontendDir, "frontend"))) {
        $dir, $label = $pair
        $envFile = Join-Path $dir ".env"
        $example = Join-Path $dir ".env.example"
        if (-not (Test-Path $example)) { continue }
        if (-not (Test-Path $envFile)) {
            Copy-Item $example $envFile
            Warn "$label .env created from the template - fill in the secrets from the password manager"
            continue
        }
        $missing = @(EnvKeys $example | Where-Object { (EnvKeys $envFile) -notcontains $_ })
        if ($missing) { Info "$label .env: optional keys missing $($missing -join ', ') - defaults are used" }
        else { Ok "$label .env contains all the template keys" }
    }
    # Required fields (DB password, SECRET_KEY) are checked by Settings itself: they have no defaults.
    if (Test-Path $pythonExe) {
        $err = & $pythonExe -c "from src.core.config import settings" 2>&1
        if ($LASTEXITCODE -eq 0) { Ok "Backend settings load" }
        else { Warn "Backend settings do not load - required values are missing in .env: $(($err | Select-Object -Last 3) -join ' ')" }
    }
}

function Sync-Python {
    Step "Python environment (.venv, uv)"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Warn "uv not found. Install: powershell -ExecutionPolicy ByPass -c ""irm https://astral.sh/uv/install.ps1 | iex"""
        return
    }
    # uv itself installs Python from .python-version and keeps packages strictly per uv.lock;
    # if nothing changed, the command finishes instantly.
    & uv sync --frozen --quiet
    if ($LASTEXITCODE -eq 0) { Ok "Python environment synchronised with uv.lock" }
    else { Warn "uv sync finished with an error" }
}

function Sync-Frontend {
    Step "Frontend (node_modules)"
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Warn "npm not found - install Node.js"; return }
    $lock = Join-Path $frontendDir "package-lock.json"
    $stamp = Join-Path $frontendDir "node_modules\.sync_lock"
    $hash = FileHash @($lock)
    if ((Test-Path $stamp) -and (Get-Content $stamp -Raw).Trim() -eq $hash) {
        Ok "Dependencies unchanged"
        return
    }
    if (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue) {
        Warn "Vite is running on :3000 - npm ci skipped (stop the dev server and run the script again)"
        return
    }
    Push-Location $frontendDir
    & npm ci --no-audit --no-fund --loglevel=error
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -eq 0) { Set-Content $stamp $hash; Ok "npm ci done per package-lock.json" }
    else { Warn "npm ci finished with an error" }
}

function Sync-Stockfish {
    Step "Stockfish engine (official release from GitHub)"
    # setup_stockfish.py itself skips the download if the binary is already in place.
    & $pythonExe (Join-Path $root "scripts\setup_stockfish.py")
    if ($LASTEXITCODE -ne 0) { Warn "Stockfish not installed - bots will play without an engine" }
}

function Sync-Database {
    Step "PostgreSQL and Redis (Docker)"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Warn "Docker not found"; return }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        $desktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
        if (Test-Path $desktop) {
            Info "Docker Desktop is not running - starting it and waiting for the engine (up to 2 minutes)..."
            Start-Process $desktop
            for ($i = 0; $i -lt 60; $i++) {
                Start-Sleep -Seconds 2
                & docker info *> $null
                if ($LASTEXITCODE -eq 0) { break }
            }
        }
    }
    & docker compose up -d --wait db redis
    if ($LASTEXITCODE -ne 0) { Warn "Docker Desktop is not running - migrations and data skipped"; return }
    Ok "Containers db and redis are running"

    Step "DB migrations (Alembic)"
    & $pythonExe -m alembic upgrade head
    if ($LASTEXITCODE -eq 0) { Ok "DB schema is up to date: $(& $pythonExe -m alembic current 2>$null)" }
    else { Warn "alembic upgrade head finished with an error" }

    Step "Puzzle database"
    & $pythonExe -m scripts.import_puzzles
    if ($LASTEXITCODE -eq 0) { Ok "Puzzles loaded" } else { Warn "Puzzle loading finished with an error" }

    Step "Archive of world champions' games"
    if (Test-Path (Join-Path $root "src\db\data\pgns\Steinitz.pgn")) {
        Ok "PGN archives are in place"
    }
    else {
        & $pythonExe -m src.db.seed
        if ($LASTEXITCODE -eq 0) { Ok "PGN archives downloaded and imported" }
        else { Warn "Importing champions' games failed" }
    }
}

function Summary([string]$okText) {
    Write-Host ""
    if ($problems.Count -eq 0) {
        Write-Host "=== $okText ===" -ForegroundColor Green
    }
    else {
        Write-Host "=== Done, but needs attention: ===" -ForegroundColor Yellow
        $problems | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    }
}

try {
    if ($Leave) {
        Invoke-Leave
    }
    else {
        Write-Host "=== Regence: syncing host $hostTag ===" -ForegroundColor Cyan
        Sync-Git
        if ($GitOnly) { Summary "Git synchronised"; exit $(if ($problems.Count) { 2 } else { 0 }) }
        Sync-Env
        Sync-Python
        Sync-Frontend
        Sync-Stockfish
        Sync-Database
        Summary "Host synchronised. Start: .\start_dev.ps1"
    }
}
catch {
    Write-Host "`n[x] $_" -ForegroundColor Red
    exit 1
}
if ($problems.Count -gt 0) { exit 2 }
