@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
if defined PYEMUERA_PYTHON (
    "%PYEMUERA_PYTHON%" -B PyEmuera.pyz . %* 2>logs\diagnostics.log
) else if exist "pypy\pypy3.exe" (
    "pypy\pypy3.exe" -B PyEmuera.pyz . %* 2>logs\diagnostics.log
) else (
    python -B PyEmuera.pyz . %* 2>logs\diagnostics.log
)
if errorlevel 1 (
    type logs\diagnostics.log
    pause
)
endlocal
