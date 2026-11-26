@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist logs mkdir logs
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if defined PYEMUERA_PYTHON (
    "%PYEMUERA_PYTHON%" -B console_utf8.py PyEmuera.pyz . %* 2>logs\diagnostics.log
) else if exist "pypy\pypy3.exe" (
    "pypy\pypy3.exe" -B console_utf8.py PyEmuera.pyz . %* 2>logs\diagnostics.log
) else (
    python -B console_utf8.py PyEmuera.pyz . %* 2>logs\diagnostics.log
)
set "BA_EXIT_CODE=%ERRORLEVEL%"
if not "%BA_EXIT_CODE%"=="0" (
    echo.
    echo Bad Apple ERB stopped with error %BA_EXIT_CODE%.
    echo Open logs\diagnostics.log as UTF-8 for details.
    pause
)
endlocal & exit /b %BA_EXIT_CODE%
