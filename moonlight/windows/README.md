# Windows cursor parking for Apollo

Copy both PowerShell scripts to the Windows gaming PC, then run
`Install-Cursor-Park.ps1` as the Windows account used for gaming, from an
administrator PowerShell session. It installs a limited, interactive scheduled
task named `Moonlight Cursor Park`, started immediately and at that user's login.
No password is stored. Apollo configuration and services are not modified.

The helper reads Apollo's connection events from its default log location. While
a stream is connected, after the foreground window and mouse have been stable
for three seconds, it parks the pointer at that window's display's bottom-right
pixel. It does this once for the initial foreground window and once for each new
fullscreen foreground window in the connection. A new client connection resets
that list. Multiple connected clients are counted. This avoids continuously
fighting intentional mouse movement or a game's camera controls.

It sends no clicks or keys and never closes games. Games that repeatedly recenter
their pointer may still need game-specific cursor hiding. The foreground display
must be the display being streamed; this is not a per-client cursor because
Windows has one shared desktop pointer. A missing/restarted Apollo log is treated
as no stream until connection events appear. On log rotation the count is rebuilt
from the new log; a connection predating that log might need a reconnect.

Installed files and status: `%LOCALAPPDATA%\MoonlightCursorPark`. `status.json`
records the interactive session, target display and actual pointer coordinates.
Source backups are kept when reinstalling. To stop: `Stop-ScheduledTask -TaskName
'Moonlight Cursor Park'`. To uninstall: stop it, then `Unregister-ScheduledTask
-TaskName 'Moonlight Cursor Park' -Confirm:$false`.

Verified on 2026-10-23: task ran in desktop session 1; SetCursorPos succeeded on
DISPLAY16 with requested and actual coordinates both (1919, 1079). Apollo stayed
running. Reconnect and per-game visual behavior still merit user confirmation.
