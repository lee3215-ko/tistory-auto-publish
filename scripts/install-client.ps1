param(
    [string]$SourceDir = "",
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$exeName = "TistoryPoster.exe"

if (-not $SourceDir) {
    $SourceDir = $PSScriptRoot
    if (-not (Test-Path (Join-Path $SourceDir $exeName))) {
        $parent = Split-Path $SourceDir -Parent
        if (Test-Path (Join-Path $parent "release\TistoryPoster\$exeName")) {
            $SourceDir = Join-Path $parent "release\TistoryPoster"
        } else {
            throw "TistoryPoster.exe가 있는 폴더를 -SourceDir 로 지정하세요."
        }
    }
}

$SourceDir = (Resolve-Path $SourceDir).Path
$exePath = Join-Path $SourceDir $exeName
if (-not (Test-Path $exePath)) {
    throw "실행 파일을 찾을 수 없습니다: $exePath"
}

$installDir = Join-Path $env:LOCALAPPDATA "Programs\TistoryPoster"
Write-Host "============================================"
Write-Host " TistoryPoster 설치"
Write-Host "  원본: $SourceDir"
Write-Host "  설치: $installDir"
Write-Host "============================================"

Get-ChildItem $SourceDir -Recurse -File | ForEach-Object {
    Unblock-File -LiteralPath $_.FullName -ErrorAction SilentlyContinue
}

if (Test-Path $installDir) {
    Write-Host "[1/3] 기존 설치 제거..."
    Remove-Item $installDir -Recurse -Force
}

Write-Host "[2/3] 파일 복사..."
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
Copy-Item -Path (Join-Path $SourceDir "*") -Destination $installDir -Recurse -Force
Get-ChildItem $installDir -Recurse -File | ForEach-Object {
    Unblock-File -LiteralPath $_.FullName -ErrorAction SilentlyContinue
}

$desktop = [Environment]::GetFolderPath("Desktop")
if (-not (Test-Path $desktop)) {
    $desktop = Join-Path $env:USERPROFILE "Desktop"
}
$shortcutPath = Join-Path $desktop "TistoryPoster.lnk"
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $installDir $exeName
$shortcut.WorkingDirectory = $installDir
$shortcut.Description = "Tistory auto publish"
$icon = Join-Path $installDir $exeName
if (Test-Path $icon) { $shortcut.IconLocation = "$icon,0" }
try {
    $shortcut.Save()
    Write-Host "[3/3] 바탕화면 바로가기: $shortcutPath"
} catch {
    Write-Host "[3/3] 바로가기 생성 생략 (수동 실행): $(Join-Path $installDir $exeName)"
}

Write-Host ""
Write-Host "설치 완료!"

if (-not $NoStart) {
    Write-Host "프로그램을 시작합니다..."
    Start-Process -FilePath (Join-Path $installDir $exeName) -WorkingDirectory $installDir
}
