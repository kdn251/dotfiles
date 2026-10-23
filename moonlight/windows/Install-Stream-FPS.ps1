$ErrorActionPreference='Stop'
$rtss='C:\Program Files (x86)\RivaTuner Statistics Server\RTSS.exe'
if(-not (Test-Path $rtss)){throw 'Install Guru3D.RTSS with winget first, then run this installer again.'}
$root=Join-Path $env:LOCALAPPDATA 'MoonlightFPS'
New-Item -ItemType Directory -Force $root|Out-Null
$task=Get-ScheduledTask -TaskName 'Moonlight FPS' -ErrorAction SilentlyContinue
if($task){
 Stop-ScheduledTask -TaskName 'Moonlight FPS'
 Start-Sleep -Seconds 1
 $old=Join-Path $root 'Stream-FPS.ps1'
 if(Test-Path $old){& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $old -Restore;if($LASTEXITCODE -ne 0){throw 'Could not restore previous limiter state'}}
}
foreach($name in @('Stream-FPS.ps1','Get-Stream-FPS.ps1')){
 $src=Join-Path $PSScriptRoot $name;$dst=Join-Path $root $name
 if([IO.Path]::GetFullPath($src) -ne [IO.Path]::GetFullPath($dst)){
  if(Test-Path $dst){Copy-Item $dst ($dst+'.backup-'+(Get-Date -Format yyyyMMdd-HHmmss))}
  Copy-Item $src $dst -Force
 }
 $tokens=$null;$errors=$null
 [Management.Automation.Language.Parser]::ParseFile($dst,[ref]$tokens,[ref]$errors)|Out-Null
 if($errors){throw ($errors|Out-String)}
}
$user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$trigger=New-ScheduledTaskTrigger -AtLogOn -User $user
$settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$a=New-ScheduledTaskAction -Execute $rtss
Register-ScheduledTask -TaskName 'Moonlight RTSS' -Action $a -Principal $principal -Trigger $trigger -Settings $settings -Force|Out-Null
foreach($entry in @(@('Moonlight FPS','Stream-FPS.ps1'),@('Moonlight FPS Measure','Get-Stream-FPS.ps1'))){
 $a=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+(Join-Path $root $entry[1])+'"')
 if($entry[0] -eq 'Moonlight FPS'){
  Register-ScheduledTask -TaskName $entry[0] -Action $a -Principal $principal -Trigger $trigger -Settings $settings -Force|Out-Null
 }else{Register-ScheduledTask -TaskName $entry[0] -Action $a -Principal $principal -Settings $settings -Force|Out-Null}
}
Start-ScheduledTask -TaskName 'Moonlight RTSS'
Start-ScheduledTask -TaskName 'Moonlight FPS'
Write-Output "Installed at $root. Apollo configuration was not modified. Restart a previously running game to allow RTSS to attach."
