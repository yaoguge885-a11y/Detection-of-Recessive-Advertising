@echo off
cd /d "%~dp0.."
powershell.exe -NoLogo -NoExit -ExecutionPolicy Bypass -File ".\scripts\start_round1_formal_3312_v1.ps1" -AnnotatorId B
