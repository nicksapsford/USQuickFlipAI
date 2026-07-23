@echo off
title USQuickFlip A.I. - Port 5009 (Shadow Collector)
cd /d C:\Users\abc\Desktop\USQuickFlipAI
start /min "USQuickFlip Collector" cmd /c C:\Users\abc\AppData\Local\Programs\Python\Python313\python.exe dashboard_usquickflip.py
timeout /t 5 /nobreak >nul
start http://localhost:5009
