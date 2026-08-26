# Builds YAHT from source with PyInstaller and installs it for the
# current user only (no admin rights needed): app files under
# %LOCALAPPDATA%\Programs\YAHT and a Start Menu shortcut. If a previous
# install is found, asks before touching it.
$ErrorActionPreference = "Stop"
Set-Location -Path (Split-Path -Parent $PSScriptRoot)

$AppName = "YAHT"
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\YAHT"
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$Shortcut = Join-Path $StartMenuDir "YAHT.lnk"
$UninstallShortcut = Join-Path $StartMenuDir "Uninstall YAHT.lnk"

# Registers/unregisters $InstallDir on the current *user's* PATH (not
# the system-wide one, so no admin rights needed) -- since YAHT.exe
# already lives there, this is all "yaht" on the command line needs to
# resolve to it; no separate wrapper script required. Only takes effect
# in *new* terminal windows/processes -- existing open ones keep
# whatever PATH they started with, same as any other PATH change.
function Add-ToUserPath($dir) {
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = if ($current) { $current -split ";" } else { @() }
    if ($parts -notcontains $dir) {
        $new = if ($current) { "$current;$dir" } else { $dir }
        [Environment]::SetEnvironmentVariable("Path", $new, "User")
    }
}

function Remove-FromUserPath($dir) {
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $current) { return }
    $parts = $current -split ";" | Where-Object { $_ -and ($_ -ne $dir) }
    [Environment]::SetEnvironmentVariable("Path", ($parts -join ";"), "User")
}

if (Test-Path $InstallDir) {
    Write-Host "An existing $AppName installation was found at $InstallDir."
    $reply = Read-Host "Uninstall it and continue installing? [y/N]"
    if ($reply -match '^[Yy]') {
        Write-Host "Removing previous installation..."
        Remove-Item -Recurse -Force $InstallDir
        Remove-Item -Force $Shortcut -ErrorAction SilentlyContinue
        Remove-Item -Force $UninstallShortcut -ErrorAction SilentlyContinue
        Remove-FromUserPath $InstallDir
    } else {
        Write-Host "Aborting install. Nothing was changed."
        exit 1
    }
}

Write-Host "Setting up build environment..."
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .venv\Scripts\python.exe -m pip install --upgrade pip -q
& .venv\Scripts\python.exe -m pip install -r requirements-build.txt -q

Write-Host "Building $AppName..."
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
& .venv\Scripts\pyinstaller.exe packaging\yaht.spec --noconfirm

Write-Host "Installing to $InstallDir..."
New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir) | Out-Null
Copy-Item -Recurse "dist\YAHT" $InstallDir
Remove-Item -Recurse -Force "build", "dist"
Add-ToUserPath $InstallDir

New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
$WshShell = New-Object -ComObject WScript.Shell

$lnk = $WshShell.CreateShortcut($Shortcut)
$lnk.TargetPath = Join-Path $InstallDir "YAHT.exe"
$lnk.WorkingDirectory = $InstallDir
$lnk.Save()

# A standalone uninstaller inside the install dir, plus a Start Menu
# entry for it -- the source repo (and this script) don't need to still
# be around to uninstall later.
$UninstallScript = Join-Path $InstallDir "uninstall.ps1"
@"
`$current = [Environment]::GetEnvironmentVariable('Path', 'User')
if (`$current) {
    `$parts = `$current -split ';' | Where-Object { `$_ -and (`$_ -ne '$InstallDir') }
    [Environment]::SetEnvironmentVariable('Path', (`$parts -join ';'), 'User')
}
Remove-Item -Recurse -Force '$InstallDir'
Remove-Item -Force '$Shortcut' -ErrorAction SilentlyContinue
Remove-Item -Force '$UninstallShortcut' -ErrorAction SilentlyContinue
Write-Host '$AppName uninstalled.'
"@ | Set-Content -Path $UninstallScript

$uninstallLnk = $WshShell.CreateShortcut($UninstallShortcut)
$uninstallLnk.TargetPath = "powershell.exe"
$uninstallLnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$UninstallScript`""
$uninstallLnk.Save()

Write-Host ""
Write-Host "$AppName installed. Find it in the Start Menu, or run: yaht"
Write-Host "(open a *new* terminal window first -- PATH changes don't reach ones already open)"
Write-Host "To uninstall later: use the 'Uninstall $AppName' Start Menu shortcut."
