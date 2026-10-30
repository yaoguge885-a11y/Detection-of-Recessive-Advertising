@echo off
cd /d "D:\Computer Science\projects\implicit-ad-agent"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start_privacy_review_A.ps1"
if errorlevel 1 (
  echo.
  echo Review exited with an error. Keep this window open.
  pause
)
