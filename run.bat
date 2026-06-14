@echo off
setlocal

set SCRIPT=%~dp0executor.py

:: Python Launcher (стандартный установщик Windows)
where py >nul 2>&1
if %errorlevel%==0 (
    py "%SCRIPT%" %*
    exit /b %errorlevel%
)

:: python в PATH
where python >nul 2>&1
if %errorlevel%==0 (
    python "%SCRIPT%" %*
    exit /b %errorlevel%
)

:: python3 в PATH
where python3 >nul 2>&1
if %errorlevel%==0 (
    python3 "%SCRIPT%" %*
    exit /b %errorlevel%
)

:: Типичные пути установки
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
) do (
    if exist %%P (
        %%P "%SCRIPT%" %*
        exit /b %errorlevel%
    )
)

echo ERROR: Python not found >&2
exit /b 1
