@ECHO OFF
start "C:\Windows\SysWOW64\wscript" "C:\Program Files (x86)\Git\Git Bash.vbs" %~dp0
call ..\scripts\activate.bat
cmd /k python __init__.py