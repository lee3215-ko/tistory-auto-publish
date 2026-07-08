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
    'start "" "TistoryPoster.exe"'
) | Set-Content -Path $launcher -Encoding ASCII

Write-Host "Build complete: $release"
