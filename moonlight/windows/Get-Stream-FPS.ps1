$ErrorActionPreference='Stop'
$root=Join-Path $env:LOCALAPPDATA 'MoonlightFPS'
$result=@()
try {
 $map=[IO.MemoryMappedFiles.MemoryMappedFile]::OpenExisting('RTSSSharedMemoryV2',[IO.MemoryMappedFiles.MemoryMappedFileRights]::Read)
 $view=$map.CreateViewAccessor(0,0,[IO.MemoryMappedFiles.MemoryMappedFileAccess]::Read)
 try {
  if($view.ReadUInt32(0) -ne 0x52545353){throw 'Invalid RTSS shared memory signature'}
  $stride=$view.ReadUInt32(8);$offset=$view.ReadUInt32(12);$count=$view.ReadUInt32(16)
  if($count -gt 4096 -or $stride -lt 284 -or ($offset+$stride*$count) -gt $view.Capacity){throw 'Unexpected RTSS shared memory layout'}
  for($i=0;$i -lt $count;$i++){
   $b=$offset+$i*$stride;$processId=$view.ReadUInt32($b)
   if(-not $processId){continue}
   $bytes=New-Object byte[] 260;$view.ReadArray($b+4,$bytes,0,260)|Out-Null
   $name=[Text.Encoding]::Default.GetString($bytes).Split([char]0)[0]
   $t0=$view.ReadUInt32($b+268);$t1=$view.ReadUInt32($b+272);$frames=$view.ReadUInt32($b+276)
   $fps=if($t1 -gt $t0){1000.0*$frames/($t1-$t0)}else{0}
   $result+=@{pid=$processId;name=$name;fps=[Math]::Round($fps,2);measurementEndTick=$t1;frames=$frames}
  }
 }finally{$view.Dispose();$map.Dispose()}
 @{time=(Get-Date -Format o);apps=$result}|ConvertTo-Json -Depth 4|Set-Content (Join-Path $root 'measured-fps.json')
}catch{@{time=(Get-Date -Format o);error=$_.Exception.Message}|ConvertTo-Json|Set-Content (Join-Path $root 'measured-fps.json');throw}
