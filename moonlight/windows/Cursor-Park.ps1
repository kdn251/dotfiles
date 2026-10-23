param([switch]$Once)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:LOCALAPPDATA 'MoonlightCursorPark'
New-Item -ItemType Directory -Force $root | Out-Null
$log = Join-Path $root 'status.json'
$apollo = 'C:\Program Files\Apollo\config\sunshine.log'
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class CursorParkNative {
 [StructLayout(LayoutKind.Sequential)] public struct Point { public int X,Y; }
 [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool GetCursorPos(out Point p);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out Rect r);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint id);
}
'@
[CursorParkNative]::SetProcessDPIAware() | Out-Null
$mutex = New-Object Threading.Mutex($false, 'Local\MoonlightCursorPark')
if (-not $mutex.WaitOne(0)) { exit 0 }
function Save-Status($state, $extra) {
 @{time=(Get-Date).ToString('o');state=$state;session=(Get-Process -Id $PID).SessionId;detail=$extra} |
  ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $log
}
function Get-Point {
 $p=New-Object CursorParkNative+Point
 if (-not [CursorParkNative]::GetCursorPos([ref]$p)) { throw 'No interactive cursor available' }
 return $p
}
try {
 $parked=@{}; $previousCount=0; $lastWindow=[IntPtr]::Zero
 $stableSince=Get-Date; $lastPoint=Get-Point; $mouseSince=Get-Date
 Save-Status 'watching' 'Waiting for an Apollo stream; no clicks or keypresses are sent.'
 do {
  $count=0
  if ($Once) { $count=1 }
  elseif (Test-Path $apollo) {
   # Reconstruct concurrent stream count. A restart begins a new log.
   $file=[IO.File]::Open($apollo,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
   $reader=New-Object IO.StreamReader($file)
   try { $lines=$reader.ReadToEnd() -split "`n" } finally { $reader.Dispose() }
   foreach ($line in $lines) {
    if ($line -match 'Info: CLIENT CONNECTED\s*$') { $count++ }
    elseif ($line -match 'Info: CLIENT DISCONNECTED\s*$') { $count=[Math]::Max(0,$count-1) }
   }
   if (-not (Get-Process sunshine -ErrorAction SilentlyContinue)) { $count=0 }
  }
  if ($count -gt $previousCount) { $parked=@{}; $stableSince=Get-Date }
  $previousCount=$count
  $window=[CursorParkNative]::GetForegroundWindow()
  if ($window -ne $lastWindow) { $lastWindow=$window; $stableSince=Get-Date }
  $point=Get-Point
  if ($point.X -ne $lastPoint.X -or $point.Y -ne $lastPoint.Y) { $mouseSince=Get-Date }
  $lastPoint=$point
  if ($count -gt 0 -and $window -ne [IntPtr]::Zero -and -not $parked.ContainsKey($window.ToInt64()) -and
      ((Get-Date)-$stableSince).TotalSeconds -ge 3 -and ((Get-Date)-$mouseSince).TotalSeconds -ge 3) {
   $screen=[Windows.Forms.Screen]::FromHandle($window)
   $b=$screen.Bounds
   $rect=New-Object CursorParkNative+Rect
   [CursorParkNative]::GetWindowRect($window,[ref]$rect) | Out-Null
   $full=($rect.Left -le $b.Left+8 -and $rect.Top -le $b.Top+8 -and $rect.Right -ge $b.Right-8 -and $rect.Bottom -ge $b.Bottom-8)
   # Once per connection on any foreground app, then only on new fullscreen windows.
   if ($Once -or $parked.Count -eq 0 -or $full) {
    $x=$b.Right-1; $y=$b.Bottom-1
    $ok=[CursorParkNative]::SetCursorPos($x,$y)
    $actual=Get-Point
    $parked[$window.ToInt64()]=$true
    Save-Status 'parked' @{requested=@($x,$y);actual=@($actual.X,$actual.Y);success=$ok;display=$screen.DeviceName;streams=$count}
    if ($Once) { break }
   }
  }
  if ($count -eq 0) { $parked=@{} }
  Start-Sleep -Seconds 1
 } while ($true)
} catch { Save-Status 'error' $_.Exception.Message; throw }
finally { $mutex.ReleaseMutex(); $mutex.Dispose() }
