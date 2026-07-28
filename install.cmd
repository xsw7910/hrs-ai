@echo off
REM ============================================================
REM  BugPilot installer (double-click friendly)
REM  Runs install.ps1 with a one-time execution-policy bypass so
REM  it works regardless of the machine's PowerShell policy, and
REM  regardless of whether the files were downloaded (Mark-of-the-Web).
REM  Keep this file next to install.ps1 and the bugpilot-*.whl.
REM ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
