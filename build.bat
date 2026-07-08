@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q pyinstaller

pyinstaller --noconfirm --clean build.spec
if errorlevel 1 exit /b 1

set "RELEASE=release\TistoryPoster"
if exist "release" rmdir /s /q "release"
mkdir "%RELEASE%"
xcopy /E /I /Y "dist\TistoryPoster\*" "%RELEASE%\" >nul

if not exist "%RELEASE%\data" mkdir "%RELEASE%\data"

> "%RELEASE%\실행.bat" echo @echo off
>> "%RELEASE%\실행.bat" echo cd /d "%%~dp0"
>> "%RELEASE%\실행.bat" echo start "" "TistoryPoster.exe"

endlocal
