@echo off
color 50
title theButton
echo Starting The Button

:: taskkill /F /FI "WINDOWTITLE eq theButton"

:: taskkill /F /FI "WINDOWTITLE eq theButtonPython"

:loop
start "theButtonPython" "C:\\Users\\Bot 00\\AppData\\Local\\Programs\\Python\\Python311\\python.exe" "Z:\\WubHub\\TheButton\\bot_code\\theButton.py"

:: Wait for 2 hours (7200 seconds)
timeout /t 3600 /nobreak

:: Close the command prompt window by its title
taskkill /F /FI "WINDOWTITLE eq theButton"

:: Close the command prompt window by its title
taskkill /F /FI "WINDOWTITLE eq theButtonPython"

:: Close the command prompt window by its title
taskkill /F /FI "WINDOWTITLE eq Select theButton"

:: Close the command prompt window by its title
taskkill /F /FI "WINDOWTITLE eq Select theButtonPython"


timeout /t 10 /nobreak
goto loop