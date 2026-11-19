# Installs and starts text-editing-llm on Windows 10/11.
# Usage (PowerShell opened with "Run as administrator"):
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
# Run it again at any time: it continues where it stopped.
param([switch]$CI)
$ErrorActionPreference = 'Continue'
Set-Location -Path $PSScriptRoot
New-Item -ItemType Directory -Force -Path data | Out-Null
. (Join-Path $PSScriptRoot 'scripts\lib.ps1')
try { Start-Transcript -Path $script:LogFile -Append | Out-Null } catch { }
if ($CI) { New-Item -ItemType File -Force -Path 'data\ci-mode' | Out-Null }

Write-Host '================================================================'
Write-Host ' text-editing-llm installer'
Write-Host ' This takes 20-60 minutes the first time (mostly downloading).'
Write-Host ' You can stop it at any time and run the same command again.'
Write-Host '================================================================'

Update-PathFromRegistry

if (-not $CI) {
    # --- 1. Checks ----------------------------------------------------------------
    Say 'Checking this computer'
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Fail 'The installer needs administrator rights.' 'Close this window, right-click "Windows PowerShell", choose "Run as administrator", and run the same command again.'
    }
    $gpu = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'NVIDIA' } | Select-Object -First 1
    if (-not $gpu) { Fail 'No NVIDIA graphics card was found.' 'This software needs an NVIDIA GPU.' }
    $drive = (Get-Item $PSScriptRoot).PSDrive
    $freeGb = [math]::Floor($drive.Free / 1GB)
    if ($freeGb -lt 100) { Fail "Only $freeGb GB of disk space is free on drive $($drive.Name):; 100 GB is needed." 'Free up space (or move this folder to a bigger drive) and run the same command again.' }
    try { Invoke-WebRequest -Uri 'https://huggingface.co' -Method Head -UseBasicParsing -TimeoutSec 20 | Out-Null }
    catch { Fail 'This computer cannot reach the internet.' 'Check the network connection and run the same command again.' }

    # --- 2. NVIDIA driver -----------------------------------------------------------------
    Say 'Checking the NVIDIA driver'
    $drv = ''
    try { $drv = (& nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>$null | Select-Object -First 1).Trim() } catch { }
    if (-not (Test-DriverOk $drv)) {
        Fail "The NVIDIA driver is missing or too old (found: $(if ($drv) { $drv } else { 'none' }); need $script:MinDriver or newer)." `
            'Download and install the latest "Game Ready" or "Studio" driver from https://www.nvidia.com/Download/index.aspx, restart the computer, and run the same command again.'
    }
    Info "Driver $drv is fine."

    # --- 3. WSL (Windows Subsystem for Linux) ------------------------------------------------
    if (-not (Test-StepDone $PSScriptRoot 'wsl')) {
        Say 'Checking the Windows Subsystem for Linux'
        & wsl.exe --status *> $null
        if ($LASTEXITCODE -ne 0) {
            $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
            if ($cpu.VirtualizationFirmwareEnabled -eq $false) {
                Fail 'Hardware virtualization is switched off in this computer''s BIOS/UEFI settings.' `
                    'Restart, open the BIOS setup (usually F2 or Del while starting), enable "Intel VT-x" or "AMD-V/SVM", save, and run the same command again.'
            }
            Info 'Installing it now...'
            & wsl.exe --install --no-distribution
            Set-StepDone $PSScriptRoot 'wsl'
            Write-Host ''
            Write-Host 'Windows needs to restart to finish this step.' -ForegroundColor Yellow
            Write-Host 'After restarting, open PowerShell as administrator again, go to this folder, and run the same command:'
            Write-Host '    powershell -ExecutionPolicy Bypass -File .\install.ps1'
            try { Stop-Transcript | Out-Null } catch { }
            exit 0
        }
        & wsl.exe --update *> $null
        Set-StepDone $PSScriptRoot 'wsl'
    }

    # --- 4. Docker Desktop ---------------------------------------------------------------------
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Say 'Installing Docker Desktop (the software that runs the assistant)'
        & winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
        Update-PathFromRegistry
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            Fail 'Docker Desktop could not be installed automatically.' 'Install it from https://www.docker.com/products/docker-desktop/, restart, and run the same command again.'
        }
    }
    & net.exe localgroup docker-users "$env:USERNAME" /add *> $null
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Say 'Starting Docker Desktop'
        Info 'If a Docker window asks you to accept its terms, click "Accept". You can skip signing in.'
        $exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
        if (Test-Path $exe) { Start-Process $exe }
        $ok = $false
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 5
            & docker info *> $null
            if ($LASTEXITCODE -eq 0) { $ok = $true; break }
        }
        if (-not $ok) { Fail 'Docker Desktop did not start.' 'Open "Docker Desktop" from the Start menu, wait until it says "Engine running", then run the same command again.' }
    }
    Set-DockerAutoStart

    Say 'Checking that Docker can use the graphics card'
    $llamaImage = Get-ConfigValue 'config\versions.env' 'LLAMA_IMAGE'
    & docker run --rm --gpus all --entrypoint nvidia-smi $llamaImage -L *> $null
    if ($LASTEXITCODE -ne 0) {
        Fail 'Docker cannot use the graphics card.' 'Update the NVIDIA driver, restart the computer, and run the same command again. See docs\admin-guide.md, "Troubleshooting".'
    }
}

# --- 5. Settings and passwords (first time only) -------------------------------------------------
if (-not (Test-Path '.env')) {
    Say 'Setting up the administrator account'
    if ($CI) {
        $email = if ($env:CI_ADMIN_EMAIL) { $env:CI_ADMIN_EMAIL } else { 'admin@example.com' }
        $password = if ($env:CI_ADMIN_PASSWORD) { $env:CI_ADMIN_PASSWORD } else { 'ci-password-1' }
    } else {
        Write-Host 'You will log in to the assistant with this email and password.'
        $email = Read-AdminEmail
        $password = Read-AdminPassword
    }
    $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -notmatch 'vEthernet|WSL|Loopback|Docker' } | ForEach-Object { $_.IPAddress })
    Write-EnvOnce -Root $PSScriptRoot -Email $email -Password $password -Sites (Get-SiteAddresses -HostName $env:COMPUTERNAME -IPs $ips)
}

# --- 6. Download and start --------------------------------------------------------------------------
Say 'Downloading the software (a few GB)'
if ((Invoke-Dc pull --ignore-buildable --quiet) -ne 0) { Fail 'The software could not be downloaded.' 'Check the internet connection and run the same command again.' }
if ((Invoke-Dc build --quiet setup) -ne 0) { Fail 'The software could not be prepared.' 'Run the same command again.' }

Say 'Preparing the AI model (about 17 GB; this is the longest step)'
if ((Invoke-Dc run --rm setup) -ne 0) { Fail 'The AI model could not be prepared.' 'Run the same command again; the download continues where it stopped.' }

Say 'Starting the assistant (the first start measures the graphics card and can take 10-20 minutes)'
if ((Invoke-Dc up -d) -ne 0) { Fail 'The assistant could not be started.' 'Run: .\textedit doctor   and follow what it says.' }
if (-not (Wait-Healthy 'llama' 60)) { Fail 'The AI model did not start.' 'Run: .\textedit doctor   and follow what it says.' }
if (-not (Wait-Healthy 'webui' 20)) { Fail 'The web page did not start.' 'Run: .\textedit doctor   and follow what it says.' }

Say 'Installing the editing presets'
if ((Invoke-Dc run --rm seed) -ne 0) { Fail 'The editing presets could not be installed.' 'Run the same command again.' }
Clear-AdminPassword $PSScriptRoot
Set-StepDone $PSScriptRoot 'installed'

Write-Host ''
Write-Host '================================================================' -ForegroundColor Green
Write-Host ' Done! The assistant is running.' -ForegroundColor Green
Write-Host ''
Write-Host ' Open one of these addresses in a web browser (on this network):'
Show-Addresses
Write-Host ''
Write-Host ' The browser will warn that the connection is not private the first'
Write-Host ' time. This is expected: click "Advanced", then "Continue".'
Write-Host ''
Write-Host ' Log in with the administrator email and password you just chose,'
Write-Host ' then add your colleagues: see docs\admin-guide.md'
Write-Host ''
Write-Host ' After a restart, log in to Windows: Docker Desktop then starts the assistant.'
Write-Host ' Useful commands:  .\textedit status   .\textedit doctor'
Write-Host '================================================================' -ForegroundColor Green
try { Stop-Transcript | Out-Null } catch { }
