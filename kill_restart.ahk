; #Warn  ; Enable warnings to assist with detecting common errors.
#SingleInstance Force
SendMode, Input  ; Recommended for new scripts due to its superior speed and reliability.
SetWorkingDir %A_ScriptDir%  ; Ensures a consistent starting directory.

; SetTimer, CloseTheButtonWindows, 900000 ; 900000 milliseconds = 15 minutes
; Return

; CloseTheButtonWindows:
;     WinClose, Select theButton
;     WinClose, theButton
; Return

loop {
    WinClose, theButton
    Sleep, 900000
}