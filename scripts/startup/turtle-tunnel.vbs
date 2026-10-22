' Launch the Cloudflare tunnel connector for daily.polygon1865.com at logon.
'
' Install (no admin needed): copy this file into
'   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
' (paste that path into the Explorer address bar). Delete it to disable.
'
' Why not the Windows service: `cloudflared service install` writes the bare exe
' path, so the service runs as LocalSystem and reads
' C:\Windows\System32\config\systemprofile\.cloudflared\config.yml instead of the
' user's config. It shows Running but never registers a connector, and Access
' ends in Error 1033. This login item passes the user config explicitly.
'
' -Supervise makes run_tunnel.ps1 restart the connector if it exits, so a dropped
' QUIC connection does not kill the site until the next logon. Every invocation
' is recorded in logs\tunnel-launch.log.
Set shell = CreateObject("WScript.Shell")
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\PyProject\turtle-framework\scripts\run_tunnel.ps1"" -Supervise", 0, False
