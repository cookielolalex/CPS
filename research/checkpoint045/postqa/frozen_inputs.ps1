function Assert-FrozenFile($pin){
  if($pin.path -isnot [string] -or $pin.sha256 -isnot [string] -or $pin.sha256 -cnotmatch '^[a-f0-9]{64}$' -or $null -eq $pin.bytes -or $pin.bytes -lt 0 -or $pin.bytes -ne [Math]::Truncate([double]$pin.bytes)){throw 'FROZEN_PIN_SHAPE_INVALID'}
  if(-not [IO.Path]::IsPathFullyQualified($pin.path) -or [IO.Path]::GetFullPath($pin.path) -cne $pin.path){throw 'FROZEN_PIN_PATH_NOT_CANONICAL'}
  $item=Get-Item -LiteralPath $pin.path -ErrorAction Stop
  if($item.PSIsContainer -or $item.Length -ne $pin.bytes -or (Get-FileHash -LiteralPath $pin.path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pin.sha256){throw 'FROZEN_INPUT_CHANGED'}
}
function Get-VerifiedFrozenPinMap($pins){
  if(@($pins).Count -eq 0){throw 'FROZEN_PIN_CENSUS_EMPTY'}
  $seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  $map=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
  foreach($pin in $pins){
    if($pin.path -isnot [string] -or -not $seen.Add($pin.path)){throw 'DUPLICATE_FROZEN_PATH'}
    Assert-FrozenFile $pin
    $map.Add($pin.path,$pin)
  }
  return $map
}
function Require-FrozenInput($map,[string]$path){
  if(-not $map.ContainsKey($path)){throw 'ORIGINAL_QA_INPUT_NOT_IN_OUTCOME_FREEZE'}
  $pin=$map[$path]
  Assert-FrozenFile $pin
  return $pin
}
