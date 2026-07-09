$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
& .\.venv\Scripts\pip.exe install -q -r requirements.txt
& .\.venv\Scripts\pip.exe install -q pyinstaller

& .\.venv\Scripts\pyinstaller.exe --noconfirm --clean build.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$release = Join-Path $PSScriptRoot "release\TistoryPoster"
if (Test-Path (Join-Path $PSScriptRoot "release")) {
    Remove-Item (Join-Path $PSScriptRoot "release") -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $release | Out-Null
Copy-Item -Path (Join-Path $PSScriptRoot "dist\TistoryPoster\*") -Destination $release -Recurse -Force

$dataDir = Join-Path $release "data"
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
}

$launcher = Join-Path $release "run.bat"
@(
    "@echo off",
    "cd /d `"%~dp0`"",
    "powershell -NoProfile -ExecutionPolicy Bypass -Command ""Get-ChildItem -LiteralPath '%~dp0' -Recurse -File | Unblock-File -ErrorAction SilentlyContinue""",
    'start "" "%~dp0TistoryPoster.exe"'
) | Out-File -FilePath $launcher -Encoding ascii

$installBat = Join-Path $release "install.bat"
@(
    "@echo off",
    "cd /d `"%~dp0`"",
    "powershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0install.ps1`"",
    "if errorlevel 1 pause"
) | Out-File -FilePath $installBat -Encoding ascii

Copy-Item -Path (Join-Path $PSScriptRoot "scripts\install-client.ps1") -Destination (Join-Path $release "install.ps1") -Force

Write-Host "Build complete: $release"
