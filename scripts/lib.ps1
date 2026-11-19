# Shared helpers for install.ps1 and textedit.ps1 (Windows). ASCII only, works in PowerShell 5.1 and 7.
$script:MinDriver = 570
$script:LogFile = 'data\install.log'

function Say([string]$Text) { Write-Host ""; Write-Host "==> $Text" -ForegroundColor Cyan }
function Info([string]$Text) { Write-Host "    $Text" }

function Fail([string]$What, [string]$Fix = '') {
    Write-Host ""
    Write-Host "!!! $What" -ForegroundColor Red
    if ($Fix) { Write-Host "    What to do: $Fix" -ForegroundColor Yellow }
    Write-Host "    Full details are in: $script:LogFile"
    Write-Host ""
    try { Stop-Transcript | Out-Null } catch { }
    exit 1
}

function Test-ValidEmail([string]$Email) { return $Email -match '^[^@\s]+@[^@\s]+\.[^@\s]+$' }

function Read-AdminEmail {
    param([scriptblock]$Reader = { Read-Host 'Administrator email (used to log in)' },
          [scriptblock]$Writer = { param($m) Write-Host $m })
    while ($true) {
        $email = ([string](& $Reader)).Trim()
        if (Test-ValidEmail $email) { return $email }
        & $Writer 'That does not look like an email address. Please try again.'
    }
}

function ConvertFrom-Secure([Security.SecureString]$Secure) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Read-AdminPassword {
    param([scriptblock]$Reader = $null, [scriptblock]$Writer = { param($m) Write-Host $m })
    $first = $true
    while ($true) {
        if ($Reader) { $pw = [string](& $Reader) }
        else { $pw = ConvertFrom-Secure (Read-Host 'Choose an administrator password (at least 8 characters)' -AsSecureString) }
        if ($pw.Length -lt 8) { & $Writer 'The password must be at least 8 characters. Please try again.'; continue }
        if ($pw -match "[\s`$#'`"\\``]") { & $Writer ('The password cannot contain spaces or any of these characters: $ # '' " \ ` ' + ' Please choose another.'); continue }
        if ($Reader) { $again = [string](& $Reader) }
        else { $again = ConvertFrom-Secure (Read-Host 'Type the same password again' -AsSecureString) }
        if ($again -ne $pw) { & $Writer 'The two passwords did not match. Please try again.'; continue }
        return $pw
    }
}

function New-RandomString([int]$Length) {
    $chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'.ToCharArray()
    $bytes = New-Object byte[] ($Length * 2)
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $sb = New-Object Text.StringBuilder
    foreach ($b in $bytes) {
        if ($b -lt 248) { [void]$sb.Append($chars[$b % 62]) }   # 248 = 4*62, avoids bias
        if ($sb.Length -eq $Length) { break }
    }
    while ($sb.Length -lt $Length) { [void]$sb.Append((New-RandomString 1)) }
    return $sb.ToString()
}

function Write-LfFile([string]$Path, [string]$Text) {
    $enc = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Text.Replace("`r`n", "`n"), $enc)
}

# Writes .env and data/secrets/llama_key the first time only (LF endings: they are read by Linux containers).
function Write-EnvOnce {
    param([string]$Root, [string]$Email, [string]$Password, [string]$Sites)
    $envPath = Join-Path $Root '.env'
    if ((Test-Path $envPath) -and (Select-String -Path $envPath -Pattern '^WEBUI_SECRET_KEY=' -Quiet)) { return }
    $secrets = Join-Path $Root 'data/secrets'
    New-Item -ItemType Directory -Force -Path $secrets | Out-Null
    $key = New-RandomString 40
    Write-LfFile (Join-Path $secrets 'llama_key') "$key`n"
    $lines = @(
        '# Created by the installer. Keep this file private; never share or commit it.',
        "WEBUI_SECRET_KEY=$(New-RandomString 48)",
        "LLAMA_API_KEY=$key",
        "WEBUI_ADMIN_EMAIL=$Email",
        "WEBUI_ADMIN_PASSWORD=$Password",
        "SITE_ADDRESSES=$Sites"
    )
    Write-LfFile $envPath (($lines -join "`n") + "`n")
}

function Clear-AdminPassword([string]$Root) {
    $envPath = Join-Path $Root '.env'
    if (Test-Path $envPath) {
        $text = [IO.File]::ReadAllText($envPath) -replace '(?m)^WEBUI_ADMIN_PASSWORD=.*$', 'WEBUI_ADMIN_PASSWORD='
        Write-LfFile $envPath $text
    }
}

function Get-SiteAddresses([string]$HostName, [string[]]$IPs) {
    $out = @("https://$($HostName.ToLower()).local")
    foreach ($ip in $IPs) {
        if ($ip -match '^(127\.|169\.254\.|172\.(1[6-9]|2[0-9]|3[01])\.)' -or $ip -match ':') { continue }
        $out += "https://$ip"
    }
    $out += 'https://localhost'
    return ($out -join ', ')
}

function Test-DriverOk([string]$Version) {
    $major = 0
    if (-not [int]::TryParse(($Version -split '\.')[0], [ref]$major)) { return $false }
    return $major -ge $script:MinDriver
}

function Test-StepDone([string]$Root, [string]$Step) {
    $f = Join-Path $Root 'data/install-state'
    return (Test-Path $f) -and ((Get-Content $f) -contains $Step)
}
function Set-StepDone([string]$Root, [string]$Step) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root 'data') | Out-Null
    Add-Content -Path (Join-Path $Root 'data/install-state') -Value $Step
}

function Update-PathFromRegistry {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Get-ConfigValue([string]$File, [string]$Key) {
    $line = Get-Content $File | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
    if ($line) { return $line.Substring($Key.Length + 1) } else { return '' }
}

# docker compose with this project's settings files
function Invoke-Dc {
    $files = @('-f', 'compose.yaml')
    if (Test-Path 'data/ci-mode') { $files += @('-f', 'compose.ci.yaml') }
    & docker compose --env-file config/versions.env --env-file config/defaults.env --env-file .env @files @args | Out-Host
    return $LASTEXITCODE
}

function Show-Addresses {
    $port = Get-ConfigValue 'config/defaults.env' 'HTTPS_PORT'
    $sites = Get-ConfigValue '.env' 'SITE_ADDRESSES'
    foreach ($a in ($sites -split ',')) {
        $a = $a.Trim()
        if ($port -eq '443') { Write-Host "      $a" } else { Write-Host "      ${a}:$port" }
    }
}

function Wait-Healthy([string]$Service, [int]$Minutes) {
    for ($i = 1; $i -le $Minutes * 6; $i++) {
        $id = (& docker compose --env-file config/versions.env --env-file config/defaults.env --env-file .env -f compose.yaml ps -q $Service 2>$null)
        if ($id) {
            $status = (& docker inspect -f '{{.State.Health.Status}}' $id 2>$null)
            if ($status -eq 'healthy') { return $true }
        }
        Start-Sleep -Seconds 10
        if ($i % 6 -eq 0) { Info "Still starting ($($i / 6) min)..." }
    }
    return $false
}

# Makes Docker Desktop start when the user logs in. Written without a byte-order mark,
# which Docker Desktop cannot read. Does nothing if Docker Desktop has not created its settings yet.
function Set-DockerAutoStart([string]$SettingsPath = (Join-Path $env:APPDATA 'Docker\settings-store.json')) {
    if (-not (Test-Path $SettingsPath)) { return }
    try {
        $json = [IO.File]::ReadAllText($SettingsPath) | ConvertFrom-Json
        $json | Add-Member -NotePropertyName AutoStart -NotePropertyValue $true -Force
        Write-LfFile $SettingsPath ($json | ConvertTo-Json -Depth 20)
    } catch { }
}
