@echo off
REM Run in a SECOND window after run_demo.bat is up. Labelled SIMULATED on the dashboard.
python ..\tools\simulator.py --scenario cycle --interval 3
pause
