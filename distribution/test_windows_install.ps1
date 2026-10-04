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
            if ((Test-PathEntry $SessionPath $AliasDir) -and ((Get-Command vixl).Source -ne $Alias)) { throw 'Old session did not resolve the alias' }
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
} finally {
    [Environment]::SetEnvironmentVariable('Path', $OriginalPath, 'User')
    if ($AliasExpected -and (Test-Path $Alias)) { Remove-Item -Force $Alias }
}
