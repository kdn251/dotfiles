$ErrorActionPreference='Stop'
$root=Join-Path $env:LOCALAPPDATA 'MoonlightCursorPark'
New-Item -ItemType Directory -Force $root | Out-Null
$source=Join-Path $PSScriptRoot 'Cursor-Park.ps1'
$target=Join-Path $root 'Cursor-Park.ps1'
if (Test-Path $target) { Copy-Item $target ($target+'.backup-'+(Get-Date -Format yyyyMMdd-HHmmss)) }
Copy-Item $source $target -Force
$user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$target+'"')
$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$trigger=New-ScheduledTaskTrigger -AtLogOn -User $user
$settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName 'Moonlight Cursor Park' -Action $action -Principal $principal -Trigger $trigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName 'Moonlight Cursor Park'
Write-Output ('Installed interactive cursor helper at '+$root)
