# Everyday commands for text-editing-llm on Windows. Run it through the shim in the project folder:  .\textedit <command>
param([string]$Command = '', [string]$Arg = '')
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -Path $Root
. (Join-Path $PSScriptRoot 'lib.ps1')
$script:LogFile = 'data\textedit.log'
Update-PathFromRegistry

& docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail 'Docker Desktop is not running.' 'Open "Docker Desktop" from the Start menu, wait until it says "Engine running", then try again.' }
if (-not (Test-Path '.env')) { Fail 'The assistant is not installed yet.' 'Run: powershell -ExecutionPolicy Bypass -File .\install.ps1' }

function Show-Usage {
    @'
Usage: .\textedit <command>

  status            Is everything running? Shows the address to open.
  start             Start the assistant.
  stop              Stop the assistant.
  restart           Restart the assistant (after changing config\defaults.env).
  logs              Show recent messages from each part.
  doctor            Check everything and say how to fix problems.
  doctor --reprobe  Also measure the graphics card again (after a hardware change).
  backup            Save a backup of all accounts and chats now.
  restore <file>    Put back a backup from data\backups (accounts and chats).
  update            Get the latest version and restart.
  loadtest          Simulate 8 people using it at once (takes a few minutes).
  uninstall         Remove the assistant but keep all data.
  uninstall --delete-data   Remove everything, including accounts and chats.
'@ | Write-Host
}

function Get-ServiceState([string]$Service) {
    $id = (& docker compose --env-file config/versions.env --env-file config/defaults.env --env-file .env -f compose.yaml ps -q $Service 2>$null)
    if (-not $id) { return 'missing' }
    return ((& docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' $id 2>$null) | Out-String).Trim()
}

function Show-Status {
    Invoke-Dc ps --format 'table {{.Service}}\t{{.Status}}' | Out-Null
    Write-Host ''
    if (Test-StepDone $Root 'installed') { Write-Host 'Open in a web browser:'; Show-Addresses }
    Write-Host ''
    Invoke-Dc exec -T llama cat /state/ctx.env | Out-Null
    Invoke-Dc exec -T llama nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader | Out-Null
}

function Invoke-Doctor {
    $problems = 0
    Say 'Checking the assistant'
    $img = Get-ConfigValue 'config\versions.env' 'LLAMA_IMAGE'
    & docker run --rm --gpus all --entrypoint nvidia-smi $img -L *> $null
    if ($LASTEXITCODE -eq 0 -or (Test-Path 'data\ci-mode')) { Info 'OK   Docker can use the graphics card.' }
    else { Info 'FAIL Docker cannot use the graphics card. Fix: update the NVIDIA driver, restart, then run .\textedit start.'; $problems++ }
    foreach ($svc in 'llama', 'webui', 'caddy', 'backup') {
        $state = Get-ServiceState $svc
        if ($state -eq 'running healthy' -or $state -eq 'running') { Info "OK   $svc is running." }
        elseif ($state -eq 'running starting') { Info "WAIT $svc is still starting. Check again in a few minutes." }
        else { Info "FAIL $svc is not running ($state). Fix: .\textedit restart, then .\textedit logs if it fails again."; $problems++ }
    }
    $logs = (& docker compose --env-file config/versions.env --env-file config/defaults.env --env-file .env -f compose.yaml logs --no-color --tail 200 llama 2>$null) | Out-String
    if ($logs -match 'does not fit on this GPU') {
        Info 'FAIL The model does not fit on the graphics card. Fix: close other programs that use the GPU (games, video editors), then run .\textedit doctor --reprobe'
        $problems++
    }
    $freeGb = [math]::Floor((Get-Item $Root).PSDrive.Free / 1GB)
    if ($freeGb -lt 10) { Info "WARN Only $freeGb GB of disk space left. Delete old backups in data\backups or free some space." }
    else { Info "OK   $freeGb GB of disk space free." }
    Write-Host ''
    if ($problems -eq 0) { Write-Host 'Everything looks fine.' } else { Write-Host "$problems problem(s) found: see the fixes above." }
}

switch ($Command) {
    'status' { Show-Status }
    'start' { Invoke-Dc up -d | Out-Null; Write-Host 'Starting. Run .\textedit status in a minute.' }
    'stop' { Invoke-Dc stop | Out-Null; Write-Host 'Stopped. Run .\textedit start to start again.' }
    'restart' { Invoke-Dc up -d --force-recreate | Out-Null; Write-Host 'Restarting. Run .\textedit status in a minute.' }
    'logs' { Invoke-Dc logs --no-color --tail 40 | Out-Null }
    'doctor' {
        if ($Arg -eq '--reprobe') {
            Invoke-Dc exec -T llama rm -f /state/ctx.env | Out-Null
            Invoke-Dc up -d --force-recreate llama | Out-Null
            Write-Host 'Measuring the graphics card again; this takes a few minutes.'
        }
        Invoke-Doctor
    }
    'backup' { Invoke-Dc run --rm maint backup-now | Out-Null }
    'restore' {
        if (-not $Arg) { Write-Host 'Which backup? Available:'; Get-ChildItem 'data\backups' | ForEach-Object { Write-Host "  $($_.Name)" }; exit 1 }
        Invoke-Dc stop webui backup | Out-Null
        $rc = Invoke-Dc run --rm maint restore (Split-Path $Arg -Leaf)
        Invoke-Dc up -d | Out-Null
        exit $rc
    }
    'update' {
        & git pull --ff-only
        if ($LASTEXITCODE -ne 0) { Fail 'Could not get the latest version.' 'Check the internet connection. If you changed files, ask for help.' }
        Invoke-Dc pull --ignore-buildable --quiet | Out-Null
        Invoke-Dc build --quiet | Out-Null
        Invoke-Dc up -d --remove-orphans | Out-Null
        if (Wait-Healthy 'webui' 20) { Invoke-Dc run --rm seed | Out-Null; Write-Host 'Updated.' }
        else { Fail 'The web page did not start after the update.' 'Run: .\textedit doctor' }
    }
    'loadtest' { $n = if ($Arg) { $Arg } else { '200000' }; Invoke-Dc run --rm maint loadtest $n | Out-Null }
    'seed' { Invoke-Dc run --rm seed | Out-Null }
    'uninstall' {
        if ($Arg -eq '--delete-data') {
            $c = Read-Host 'This deletes ALL accounts, chats and the model. Type DELETE to confirm'
            if ($c -ne 'DELETE') { Write-Host 'Cancelled.'; exit 1 }
            Invoke-Dc --profile tools down -v --rmi local | Out-Null
            Remove-Item -Recurse -Force data, .env
            Write-Host 'Everything removed.'
        } else {
            Invoke-Dc --profile tools down | Out-Null
            Write-Host 'Removed. Accounts, chats and the model are kept; run .\textedit start to bring it back.'
        }
    }
    default { Show-Usage }
}
