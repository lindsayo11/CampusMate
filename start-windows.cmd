@echo off
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%backend\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Install dependencies first. See README.md.
  exit /b 1
)
"%PY%" "%ROOT%scripts\start_local.py" %*
endlocal
