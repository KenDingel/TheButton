@echo off

title theButton

:loop
start "theButtonPython" "C:\\Users\\Bot 00\\AppData\\Local\\Programs\\Python\\Python311\\python.exe" "Z:\\WubHub\\TheButton\\theButton.py"

:: Wait for 2 hours (7200 seconds)
timeout /t 3600 /nobreak

:: Close the command prompt window by its title
taskkill /F /FI "WINDOWTITLE eq theButtonPython"

goto loop