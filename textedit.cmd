@echo off
rem Lets you type  .\textedit status  (runs scripts\textedit.ps1 without changing PowerShell settings).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\textedit.ps1" %*
