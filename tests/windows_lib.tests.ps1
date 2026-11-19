# Plain PowerShell tests for scripts/lib.ps1. Run: pwsh -File tests/windows_lib.tests.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../scripts/lib.ps1')
$script:failures = 0
function Assert($cond, $name) {
    if ($cond) { Write-Host "PASS $name" } else { Write-Host "FAIL $name"; $script:failures++ }
}
function Queue([string[]]$items) { $q = New-Object System.Collections.Queue; $items | ForEach-Object { $q.Enqueue($_) }; return ,$q }

# email re-asked until valid
$q = Queue @('not-an-email', 'bad@', 'prof@iiit.ac.in')
$out = @()
$email = Read-AdminEmail -Reader { $q.Dequeue() } -Writer { param($m) $script:out += $m }
Assert ($email -eq 'prof@iiit.ac.in') 'email accepted when valid'
Assert (($out | Where-Object { $_ -like '*does not look like an email*' }).Count -eq 2) 'email re-asked twice'

# password mismatch re-asked
$q = Queue @('short', 'longenough1', 'different1', 'goodpass99', 'goodpass99')
$out = @()
$pw = Read-AdminPassword -Reader { $q.Dequeue() } -Writer { param($m) $script:out += $m }
Assert ($pw -eq 'goodpass99') 'password accepted after match'
Assert (($out -join ' ') -like '*at least 8 characters*') 'short password rejected'
Assert (($out -join ' ') -like '*did not match*') 'mismatch rejected'

# password with characters that would break the settings file is re-asked
$q = Queue @('Pa$sw0rd!', 'has space1', "quote'1234", 'Good-Pass_99!', 'Good-Pass_99!')
$out = @()
$pw = Read-AdminPassword -Reader { $q.Dequeue() } -Writer { param($m) $script:out += $m }
Assert ($pw -eq 'Good-Pass_99!') 'special-character password re-asked'
Assert (($out | Where-Object { $_ -like '*cannot contain*' }).Count -eq 3) 'three bad passwords rejected'

# .env written once, LF only, key file without newline problems
$dir = Join-Path ([IO.Path]::GetTempPath()) ("te-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path (Join-Path $dir 'data') | Out-Null
Write-EnvOnce -Root $dir -Email 'a@b.co' -Password 'secret123' -Sites 'https://localhost'
$first = [IO.File]::ReadAllText((Join-Path $dir '.env'))
$key = [IO.File]::ReadAllText((Join-Path $dir 'data/secrets/llama_key'))
Assert ($first -like '*WEBUI_ADMIN_PASSWORD=secret123*') '.env has admin password'
Assert (-not $first.Contains("`r")) '.env uses LF line endings'
Assert ($key.Trim().Length -eq 40 -and -not $key.Contains("`r")) 'llama key is 40 chars, no CR'
Assert ($first -like "*LLAMA_API_KEY=$($key.Trim())*") '.env and key file agree'
Write-EnvOnce -Root $dir -Email 'x@y.co' -Password 'other1234' -Sites 'https://x'
Assert ([IO.File]::ReadAllText((Join-Path $dir '.env')) -eq $first) '.env not regenerated'

# driver version
Assert (-not (Test-DriverOk '552.44')) 'old driver rejected'
Assert (Test-DriverOk '576.02') 'new driver accepted'

# site addresses
$s = Get-SiteAddresses -HostName 'LABPC' -IPs @('192.168.1.5', '172.20.0.1', '169.254.3.3', '10.0.0.2')
Assert ($s -eq 'https://labpc.local, https://192.168.1.5, https://10.0.0.2, https://localhost') 'site addresses'

# install state
Set-StepDone -Root $dir -Step 'docker'
Assert (Test-StepDone -Root $dir -Step 'docker') 'step marked done'
Assert (-not (Test-StepDone -Root $dir -Step 'model')) 'other step not done'

# Docker Desktop auto-start is written without a byte-order mark (Docker cannot read one)
$settings = Join-Path $dir 'settings-store.json'
Write-LfFile $settings '{"AutoStart": false, "Other": 1}'
Set-DockerAutoStart -SettingsPath $settings
$bytes = [IO.File]::ReadAllBytes($settings)
Assert (-not ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB)) 'settings written without BOM'
$j = [IO.File]::ReadAllText($settings) | ConvertFrom-Json
Assert ($j.AutoStart -eq $true -and $j.Other -eq 1) 'AutoStart switched on, other settings kept'
Set-DockerAutoStart -SettingsPath (Join-Path $dir 'missing.json')
Assert (-not (Test-Path (Join-Path $dir 'missing.json'))) 'missing settings file left alone'

# Invoke-Dc returns only docker's exit code, not its printed output
$stub = Join-Path $dir 'bin'; New-Item -ItemType Directory -Path $stub | Out-Null
if ($IsWindows) { Set-Content (Join-Path $stub 'docker.cmd') "@echo some output`r`n@echo more`r`n@exit /b 3" }
else { Set-Content (Join-Path $stub 'docker') "#!/bin/sh`necho some output`necho more`nexit 3"; chmod +x (Join-Path $stub 'docker') }
$oldPath = $env:PATH; $env:PATH = "$stub$([IO.Path]::PathSeparator)$env:PATH"
$rc = Invoke-Dc ps
$env:PATH = $oldPath
Assert ($rc -is [int] -and $rc -eq 3) 'Invoke-Dc returns the exit code only'

Remove-Item -Recurse -Force $dir
if ($script:failures) { Write-Host "$script:failures test(s) failed"; exit 1 } else { Write-Host 'All tests passed' }
