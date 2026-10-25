# The optional "Run Vixl host for AI Server Studio" installer task (#547): a per-user Scheduled Task, no admin rights.
#
#   host-task.ps1 -Action Install -App <install folder>   register and start it; writes the token and host.json
#   host-task.ps1 -Action Remove                           stop and unregister it; deletes host.json and the token
#
# Install generates a 32-byte token, writes it to %LOCALAPPDATA%\Vixl\host-token and
# %LOCALAPPDATA%\Vixl\host.json {url, token_file}, both readable by the current user only, and registers the task
# "Vixl host" (at logon, restart on failure) running
#   vixl.exe host --root %LOCALAPPDATA%\Vixl\host --offline --bind 127.0.0.1 --token-file %LOCALAPPDATA%\Vixl\host-token
# The updater restarts the task after it activates a version (schtasks /End, /Run) when host.json exists.
# A machine-wide Windows service (admin rights) is not built; which of the two AI Server Studio detects is unconfirmed.
param(
    [Parameter(Mandatory = $true)][ValidateSet('Install', 'Remove')][string]$Action,
    [string]$App = ''
)
$ErrorActionPreference = 'Stop'
$TaskName = 'Vixl host'
$Port = 8767
$Base = Join-Path $env:LOCALAPPDATA 'Vixl'
$Config = Join-Path $Base 'host.json'
$TokenFile = Join-Path $Base 'host-token'
$Root = Join-Path $Base 'host'

function Restrict-ToUser([string]$Path) {
    # Only the current user: no inherited entries, full control for this user's SID.
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $Path /inheritance:r /grant:r "*${sid}:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not restrict access to $Path" }
}

function Write-Private([string]$Path, [string]$Text) {
    # Created empty and locked down before the secret is written into it.
    if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Force }
    New-Item -ItemType File -Path $Path -Force | Out-Null
    Restrict-ToUser $Path
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}

if ($Action -eq 'Remove') {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    foreach ($file in @($Config, $TokenFile)) {
        if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force }
    }
    # The workspaces under host\ are the user's documents and stay.
    exit 0
}

if (-not $App) { throw 'Install needs -App, the Vixl install folder' }
$Exe = Join-Path $App 'bin\vixl.exe'
if (-not (Test-Path -LiteralPath $Exe)) { throw "No Vixl launcher at $Exe" }
New-Item -ItemType Directory -Path $Root -Force | Out-Null

$bytes = New-Object byte[] 32
$random = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $random.GetBytes($bytes) } finally { $random.Dispose() }
$token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
Write-Private $TokenFile $token
$hostJson = [ordered]@{ url = "http://127.0.0.1:$Port"; token_file = $TokenFile } | ConvertTo-Json
Write-Private $Config $hostJson

$arguments = "host --root `"$Root`" --offline --bind 127.0.0.1 --port $Port --token-file `"$TokenFile`""
$taskAction = New-ScheduledTaskAction -Execute $Exe -Argument $arguments -WorkingDirectory $Base
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Settings $settings `
    -Principal $principal -Description 'Vixl host for AI Server Studio (per user, loopback only)' -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
exit 0
