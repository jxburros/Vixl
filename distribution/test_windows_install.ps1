# Exercise the actual frozen launcher, installer, registry PATH and uninstaller.
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path "$PSScriptRoot\..").Path
$Python = (Get-Command python).Source
$Version = (& $Python -c "from vixl import __version__; print(__version__)").Trim()
$Install = Join-Path $env:RUNNER_TEMP 'Vixl installation with spaces'
$Installer = Join-Path $Root "dist\release\Vixl-Setup-$Version-windows-x64.exe"
$OriginalPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$env:VIXL_NO_UPDATE = '1'
# The installer also copies the launcher into WindowsApps (on PATH for already-running
# processes) when that folder exists, is on PATH, and holds no other program's vixl.exe.
$SessionPath = $env:PATH
$AliasDir = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps'
$Alias = Join-Path $AliasDir 'vixl.exe'
function Test-PathEntry([string]$Value, [string]$Folder) {
    foreach ($Entry in ($Value -split ';')) {
        $Expanded = [Environment]::ExpandEnvironmentVariables($Entry.Trim()).TrimEnd('\')
        if ($Expanded -and ($Expanded -ieq $Folder.TrimEnd('\'))) { return $true }
    }
    return $false
}
$AliasOnPath = (Test-PathEntry "$OriginalPath" $AliasDir) -or (Test-PathEntry $SessionPath $AliasDir)
$ForeignAlias = if (Test-Path $Alias) { (Get-FileHash $Alias).Hash } else { $null }
$AliasExpected = (Test-Path $AliasDir -PathType Container) -and $AliasOnPath -and -not $ForeignAlias
# The "Run Vixl host for AI Server Studio" task path (#547) registers a real Scheduled Task, so it runs only when
# VIXL_TEST_HOST_TASK=1. Manual checklist on a clean, non-admin Windows account (docs/reference/releases.md):
#   1. Run the installer, tick "Run Vixl host for AI Server Studio"; it finishes without a UAC prompt.
#   2. %LOCALAPPDATA%\Vixl\host.json is {url: http://127.0.0.1:8767, token_file}; icacls shows only your account on it
#      and on host-token.
#   3. Task Scheduler lists "Vixl host" (at logon, restart on failure, your account); it is running, and
#      GET /host/health with the token answers {ok: true}; without the token it answers 401.
#   4. Sign out and in: the task starts again. End vixl-engine.exe in Task Manager: it restarts within a minute.
#   5. vixl update (or a pending update on the next launch) restarts the task onto the new version (GET /host/info).
#   6. Uninstall: the task, host.json and host-token are gone; %LOCALAPPDATA%\Vixl\host\ (workspaces) stays.
$HostTask = $env:VIXL_TEST_HOST_TASK -eq '1'
$HostConfig = Join-Path $env:LOCALAPPDATA 'Vixl\host.json'
try {
    $Process = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=`"$Install`"") -Wait -PassThru
    if ($Process.ExitCode -ne 0) { throw "Installer failed: $($Process.ExitCode)" }
    $NewPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not $NewPath.StartsWith("$Install\bin", [StringComparison]::OrdinalIgnoreCase)) { throw 'Installer did not prepend its user PATH' }
    $env:PATH = "$NewPath;" + $env:PATH
    # Resolve vixl through PATH, as a newly opened terminal would.
    if ((Get-Command vixl).Source -ne "$Install\bin\vixl.exe") { throw 'PATH resolved the wrong Vixl command' }
    if ((vixl --version).Trim() -ne $Version) { throw 'Wrong installed version' }
    if ($AliasExpected) {
        if (-not (Test-Path $Alias)) { throw 'Installer did not add the WindowsApps vixl alias' }
        if ((Get-FileHash $Alias).Hash -ne (Get-FileHash "$Install\bin\vixl.exe").Hash) { throw 'Alias is not the Vixl launcher' }
        # A session started before installation resolves the alias. The custom /DIR is
        # found through the installer's HKCU\Software\Vixl InstallRoot record.
        $InstalledPath = $env:PATH
        $env:PATH = $SessionPath
        try {
            # Another vixl (here the runner's pip install) may come earlier on that PATH; the
            # alias must still be found there.
            $Found = @(Get-Command vixl -All -CommandType Application -ErrorAction SilentlyContinue | ForEach-Object { $_.Source })
            if ((Test-PathEntry $SessionPath $AliasDir) -and -not ($Found -contains $Alias)) {
                throw "Old session did not find the alias; it found: $($Found -join ', ')"
            }
            if ((& $Alias --version).Trim() -ne $Version) { throw 'Alias launched the wrong installation' }
            $AliasStatus = (& $Alias updates status --json | ConvertFrom-Json)
            if ($LASTEXITCODE -ne 0 -or -not $AliasStatus) { throw 'Alias could not read the installation state' }
        } finally {
            $env:PATH = $InstalledPath
        }
    } elseif ($ForeignAlias) {
        if ((Get-FileHash $Alias).Hash -ne $ForeignAlias) { throw 'Installer replaced another program''s vixl.exe' }
    } elseif (Test-Path $Alias) {
        throw 'Installer added an alias although WindowsApps is not on PATH'
    }
    vixl new 120x80 -o "$Install\test-project.vixl"
    if ($LASTEXITCODE -ne 0) { throw 'Installed create failed' }
    vixl -p "$Install\test-project.vixl" text add 'Installed' --size 16
    if ($LASTEXITCODE -ne 0) { throw 'Installed font rendering failed' }
    vixl -p "$Install\test-project.vixl" export "$Install\test.png"
    if ($LASTEXITCODE -ne 0) { throw 'Installed export failed' }
    & $Python distribution/test_native_mcp.py "$Install\bin\vixl.exe"
    if ($LASTEXITCODE -ne 0) { throw 'Installed MCP verification failed' }
    & $Python distribution/test_native_design.py "$Install\bin\vixl.exe"
    if ($LASTEXITCODE -ne 0) { throw 'Installed logo workflow verification failed' }
    if ($HostTask) {
        $Process = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/DIR=`"$Install`"", '/TASKS="studiohost"') -Wait -PassThru
        if ($Process.ExitCode -ne 0) { throw "Installer with the host task failed: $($Process.ExitCode)" }
        $HostInfo = Get-Content -Raw $HostConfig | ConvertFrom-Json
        if ($HostInfo.url -ne 'http://127.0.0.1:8767') { throw "host.json names $($HostInfo.url)" }
        $Sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        foreach ($Secret in @($HostConfig, $HostInfo.token_file)) {
            $Rules = (Get-Acl $Secret).Access
            if ($Rules.Count -ne 1 -or $Rules[0].IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -ne $Sid) {
                throw "$Secret is readable by more than the current user"
            }
        }
        if (-not (Get-ScheduledTask -TaskName 'Vixl host' -ErrorAction SilentlyContinue)) { throw 'The host task was not registered' }
        $Token = (Get-Content -Raw $HostInfo.token_file).Trim()
        $Healthy = $false
        foreach ($Attempt in 1..60) {
            try {
                $Health = Invoke-RestMethod -Uri "$($HostInfo.url)/host/health" -Headers @{ Authorization = "Bearer $Token" }
                if ($Health.ok) { $Healthy = $true; break }
            } catch { Start-Sleep -Seconds 1 }
        }
        if (-not $Healthy) { throw 'The host task did not answer /host/health' }
    }
    vixl updates off
    if ($LASTEXITCODE -ne 0) { throw 'Update preferences failed' }
    $Status = (vixl updates status --json | ConvertFrom-Json)
    if ($Status.automatic -ne $false) { throw 'Preference did not persist' }
    vixl updates on
    & $Python distribution/test_native_update.py "$Install" "dist/release/vixl-$Version-windows-x64.zip"
    if ($LASTEXITCODE -ne 0) { throw 'Native update verification failed' }
    $Process = Start-Process "$Install\unins000.exe" -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -Wait -PassThru
    if ($Process.ExitCode -ne 0) { throw 'Uninstaller failed' }
    if (Test-Path "$Install\bin\vixl.exe") { throw 'Launcher was not uninstalled' }
    if ($AliasExpected -and (Test-Path $Alias)) { throw 'Alias was not uninstalled' }
    if ($ForeignAlias -and ((Get-FileHash $Alias).Hash -ne $ForeignAlias)) { throw 'Uninstaller touched another program''s vixl.exe' }
    if (Get-ItemProperty 'HKCU:\Software\Vixl' -Name InstallRoot -ErrorAction SilentlyContinue) { throw 'Install root record was not removed' }
    if (-not (Test-Path "$Install\test-project.vixl")) { throw 'Uninstaller removed a user project' }
    if ([Environment]::GetEnvironmentVariable('Path', 'User') -ne $OriginalPath) { throw 'Uninstaller changed unrelated PATH entries' }
    if ($HostTask) {
        if (Get-ScheduledTask -TaskName 'Vixl host' -ErrorAction SilentlyContinue) { throw 'Uninstaller left the host task' }
        if (Test-Path $HostConfig) { throw 'Uninstaller left host.json' }
    }
} finally {
    [Environment]::SetEnvironmentVariable('Path', $OriginalPath, 'User')
    if ($AliasExpected -and (Test-Path $Alias)) { Remove-Item -Force $Alias }
}
