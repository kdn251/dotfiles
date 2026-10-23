param([switch]$Restore)
$ErrorActionPreference='Stop'
$root=Join-Path $env:LOCALAPPDATA 'MoonlightFPS'
$rtss='C:\Program Files (x86)\RivaTuner Statistics Server'
$apollo='C:\Program Files\Apollo\config\sunshine.log'
$backup=Join-Path $root 'previous-limit.json'
$env:Path="$rtss;$env:Path"
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class StreamFPSNative {
 [DllImport("RTSSHooks64.dll", CallingConvention=CallingConvention.StdCall,CharSet=CharSet.Ansi)] public static extern void LoadProfile(string profile);
 [DllImport("RTSSHooks64.dll", CallingConvention=CallingConvention.StdCall,CharSet=CharSet.Ansi)] public static extern bool GetProfileProperty(string name,IntPtr data,uint size);
 [DllImport("RTSSHooks64.dll", CallingConvention=CallingConvention.StdCall,CharSet=CharSet.Ansi)] public static extern bool SetProfileProperty(string name,IntPtr data,uint size);
 [DllImport("RTSSHooks64.dll", CallingConvention=CallingConvention.StdCall,CharSet=CharSet.Ansi)] public static extern void SaveProfile(string profile);
 [DllImport("RTSSHooks64.dll", CallingConvention=CallingConvention.StdCall)] public static extern void UpdateProfiles();
}
'@
function Get-Limit {
 [StreamFPSNative]::LoadProfile('')
 $ptr=[Runtime.InteropServices.Marshal]::AllocHGlobal(4)
 try {
  if(-not [StreamFPSNative]::GetProfileProperty('FramerateLimit',$ptr,4)){throw 'Cannot read RTSS limit'}
  return [Runtime.InteropServices.Marshal]::ReadInt32($ptr)
 } finally {[Runtime.InteropServices.Marshal]::FreeHGlobal($ptr)}
}
function Set-Limit([int]$value) {
 [StreamFPSNative]::LoadProfile('')
 $ptr=[Runtime.InteropServices.Marshal]::AllocHGlobal(4)
 try {
  [Runtime.InteropServices.Marshal]::WriteInt32($ptr,$value)
  if(-not [StreamFPSNative]::SetProfileProperty('FramerateLimit',$ptr,4)){throw 'RTSS rejected frame limit'}
  [StreamFPSNative]::SaveProfile('');[StreamFPSNative]::UpdateProfiles()
 } finally {[Runtime.InteropServices.Marshal]::FreeHGlobal($ptr)}
 if((Get-Limit) -ne $value){throw 'RTSS frame limit read-back mismatch'}
 Add-Content (Join-Path $root 'events.log') "$(Get-Date -Format o) limit=$value"
}
function Restore-Limit {
 if(Test-Path $backup){$old=Get-Content -Raw $backup|ConvertFrom-Json;Set-Limit ([int]$old.limit);Remove-Item $backup}
}
function Read-Stream {
 $count=0;$fps=0.0
 if((Test-Path $apollo) -and (Get-Process sunshine -ErrorAction SilentlyContinue)){
  $file=[IO.File]::Open($apollo,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
  $reader=New-Object IO.StreamReader($file)
  try {$lines=$reader.ReadToEnd() -split "`n"} finally {$reader.Dispose()}
  foreach($line in $lines){
   if($line -match 'Info: CLIENT CONNECTED\s*$'){$count++}
   elseif($line -match 'Info: CLIENT DISCONNECTED\s*$'){$count=[Math]::Max(0,$count-1);if($count -eq 0){$fps=0}}
   elseif($line -match 'Info: Requested frame rate \[([0-9.]+)fps\]'){$fps=[double]::Parse($Matches[1],[Globalization.CultureInfo]::InvariantCulture)}
  }
 }
 return @{count=$count;fps=$fps}
}
New-Item -ItemType Directory -Force $root|Out-Null
$mutex=New-Object Threading.Mutex($false,'Local\MoonlightStreamFPS')
if(-not $mutex.WaitOne(0)){throw 'Stop the Moonlight FPS task before launching another instance'}
try {
 if($Restore){Restore-Limit;exit}
 while($true){
  try {
   $stream=Read-Stream
   # One global GPU limiter cannot honor two different clients simultaneously.
   # Fractional rates need denominator handling; don't silently round them.
   $supported=$stream.count -eq 1 -and $stream.fps -ge 10 -and $stream.fps -le 360 -and $stream.fps -eq [Math]::Floor($stream.fps)
   if($supported){
    if(-not (Get-Process RTSS -ErrorAction SilentlyContinue)){Start-Process (Join-Path $rtss 'RTSS.exe');Start-Sleep -Seconds 2}
    if(-not (Test-Path $backup)){
     @{limit=(Get-Limit);time=(Get-Date -Format o)}|ConvertTo-Json|Set-Content ($backup+'.tmp')
     Move-Item ($backup+'.tmp') $backup -Force
    }
    $target=[int]$stream.fps
    if((Get-Limit) -ne $target){Set-Limit $target}
    $state='limited'
   }else{Restore-Limit;$state=if($stream.count -eq 0){'idle'}else{'unsupported-stream-count-or-fps'}}
   @{time=(Get-Date -Format o);state=$state;streams=$stream.count;requestedFPS=$stream.fps;actualLimit=(Get-Limit);session=(Get-Process -Id $PID).SessionId}|ConvertTo-Json|Set-Content (Join-Path $root 'status.json')
  }catch{
   @{time=(Get-Date -Format o);state='error';message=$_.Exception.Message}|ConvertTo-Json|Set-Content (Join-Path $root 'status.json')
  }
  Start-Sleep -Seconds 1
 }
}finally{try{Restore-Limit}finally{$mutex.ReleaseMutex();$mutex.Dispose()}}
