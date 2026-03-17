@echo off
cd /d "%~dp0"
set PYTHONPATH=%~dp0
"C:\Users\More\AppData\Local\Programs\Python\Python311\python.exe" -m app.main %*
