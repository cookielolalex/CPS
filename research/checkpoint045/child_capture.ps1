function Child([string]$name,[string]$exe,[string[]]$arguments,[string]$stdinPath,[int]$runtime,[int]$cleanup,[string]$observeResponse='') {
  $psi=[Diagnostics.ProcessStartInfo]::new();$psi.FileName=$exe;$psi.WorkingDirectory=$destination
  $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.WindowStyle=[Diagnostics.ProcessWindowStyle]::Hidden
  $psi.RedirectStandardInput=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
  foreach($arg in $arguments){$psi.ArgumentList.Add($arg)}
  $p=[Diagnostics.Process]::new();$p.StartInfo=$psi
  $outName=$(if($name -eq 'model'){'stdout.raw'}else{$name+'.stdout.raw'})
  $errName=$(if($name -eq 'model'){'stderr.raw'}else{$name+'.stderr.raw'})
  $out=[IO.File]::Open((Join-Path $destination $outName),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
  $err=[IO.File]::Open((Join-Path $destination $errName),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
  $times=[IO.File]::Open((Join-Path $destination ($name+'.stdout-observations.jsonl')),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
  $watch=[Diagnostics.Stopwatch]::StartNew();$total=$runtime+$cleanup
  $r=[ordered]@{name=$name;started_utc=[DateTime]::UtcNow.ToString('o');pid=$null;exit_code=$null;timed_out=$false;own_tree_cleanup_requested=$false;own_process_exited=$false;capture_complete=$false;error=$null;child_exit_first_observed_ms=$null;child_exit_first_observed_utc=$null;response_first_exists_ms=$null;response_first_exists_utc=$null;response_observations=@();timing_semantics='Parent read/HasExited/file-stat observations, not child emission or precise OS creation timestamps';poll_interval_ms=10}
  $oc=$null;$ec=$null;$lastSize=-1
  try {
    if(-not $p.Start()){throw 'CHILD_NOT_STARTED'};$r.pid=$p.Id
    $oc=[CPS036TimedCapture]::Pump($p.StandardOutput.BaseStream,$out,$times,$watch)
    $ec=[CPS036TimedCapture]::Pump($p.StandardError.BaseStream,$err,$null,$watch)
    if($stdinPath){$b=[IO.File]::ReadAllBytes($stdinPath);$p.StandardInput.BaseStream.Write($b,0,$b.Length)}
    $p.StandardInput.Close()
    while($true){
      if($observeResponse -and [IO.File]::Exists($observeResponse)){
        $size=([IO.FileInfo]::new($observeResponse)).Length
        if($null -eq $r.response_first_exists_ms){$r.response_first_exists_ms=$watch.ElapsedMilliseconds;$r.response_first_exists_utc=[DateTime]::UtcNow.ToString('o')}
        if($size -ne $lastSize){$r.response_observations+=@([ordered]@{observed_ms=$watch.ElapsedMilliseconds;observed_utc=[DateTime]::UtcNow.ToString('o');bytes=$size});$lastSize=$size}
      }
      if($p.HasExited){$r.child_exit_first_observed_ms=$watch.ElapsedMilliseconds;$r.child_exit_first_observed_utc=[DateTime]::UtcNow.ToString('o');if($r.child_exit_first_observed_ms -gt $runtime){$r.timed_out=$true};break}
      if($watch.ElapsedMilliseconds -ge $runtime){$r.timed_out=$true;$r.own_tree_cleanup_requested=$true;$p.Kill($true);break}
      [Threading.Thread]::Sleep(10)
    }
    $r.own_process_exited=$p.WaitForExit([Math]::Max(0,$total-[int]$watch.ElapsedMilliseconds))
    if($r.own_process_exited){$r.exit_code=$p.ExitCode;if($null -eq $r.child_exit_first_observed_ms){$r.child_exit_first_observed_ms=$watch.ElapsedMilliseconds;$r.child_exit_first_observed_utc=[DateTime]::UtcNow.ToString('o')}}
    $r.capture_complete=[Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]@($oc,$ec),[Math]::Max(0,$total-[int]$watch.ElapsedMilliseconds))
    if($observeResponse -and [IO.File]::Exists($observeResponse)){
      $r.response_available_after_exit_ms=$watch.ElapsedMilliseconds;$r.response_available_after_exit_utc=[DateTime]::UtcNow.ToString('o');$r.response_bytes_after_exit=([IO.FileInfo]::new($observeResponse)).Length
      if($null -eq $r.response_first_exists_ms){$r.response_first_exists_ms=$r.response_available_after_exit_ms;$r.response_first_exists_utc=$r.response_available_after_exit_utc}
    }
  } catch {$r.error=$_.Exception.Message} finally {
    if($null -ne $r.pid){try{if(-not $p.HasExited){$r.own_tree_cleanup_requested=$true;$p.Kill($true);$null=$p.WaitForExit([Math]::Max(0,$total-[int]$watch.ElapsedMilliseconds))};$r.own_process_exited=$p.HasExited;if($p.HasExited){$r.exit_code=$p.ExitCode}}catch{$r.cleanup_error=$_.Exception.Message}}
    if($null -ne $r.pid){try{$p.StandardOutput.Close();$p.StandardError.Close()}catch{}}
    $out.Dispose();$err.Dispose();$times.Dispose();$p.Dispose();$r.elapsed_ms=$watch.ElapsedMilliseconds;$r.ended_utc=[DateTime]::UtcNow.ToString('o')
    SaveJson (Join-Path $destination ($name+'.result.json')) $r
  }
  if($r.error -or $r.timed_out -or -not $r.own_process_exited -or -not $r.capture_complete -or $r.exit_code -ne 0){throw ('CHILD_HELD:'+ $name)}
  return $r
}
