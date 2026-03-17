@echo off
cd /d "%~dp0"
set PYTHONPATH=%~dp0

if "%1"=="" (
    echo Usage: run.bat [cli^|xianyu^|ozon]
    echo   cli    - Interactive CLI demo
    echo   xianyu - Xianyu live mode (Playwright)
    echo   ozon   - Ozon marketplace mode (API)
    echo.
    set MODE=cli
) else (
    set MODE=%1
)

"C:\Users\More\AppData\Local\Programs\Python\Python311\python.exe" -m app.main %MODE%
