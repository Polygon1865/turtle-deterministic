' Launch the Caddy origin for daily.polygon1865.com at logon.
'
' Install (no admin needed): copy this file into
'   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
' (paste that path into the Explorer address bar). Delete it to disable.
'
' Without this, a reboot leaves cloudflared running but 127.0.0.1:8080 dead,
' and every request ends in 502 / Error 1033 with "connectex ... actively
' refused it" in logs\cloudflared.log. See docs\daily-server.md, "Caddy".
Set shell = CreateObject("WScript.Shell")
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\PyProject\turtle-framework\scripts\run_caddy.ps1""", 0, False
