# Run one spike script inside FreeCAD (hidden GUI by default, or FreeCADCmd with -Console).
# Usage: powershell -NoProfile -File scripts\spike\run_spike.ps1 -Name s1_titleblock [-Console] [-TimeoutSec 240]
# Output goes to out\spike\ (git-ignored). The FreeCAD process ends itself with os._exit.
param(
    [Parameter(Mandatory)][string]$Name,
    [switch]$Console,
    [int]$TimeoutSec = 240
)
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$bin = Join-Path $env:LOCALAPPDATA 'Programs\FreeCAD 1.1\bin'
$out = Join-Path $repo 'out\spike'
New-Item -ItemType Directory -Force $out | Out-Null
$env:SPIKE_DIR = $PSScriptRoot
$env:SPIKE_OUT = $out
$env:PYTHONPATH = $PSScriptRoot
$script = Join-Path $PSScriptRoot ($Name + '.py')
if (-not (Test-Path $script)) { throw "script not found: $script" }
$exe = if ($Console) { Join-Path $bin 'FreeCADCmd.exe' } else { Join-Path $bin 'freecad.exe' }
$args = if ($Console) { @("`"$script`"") } else { @('--hidden', "`"$script`"") }
$sw = [Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath $exe -ArgumentList $args -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $out "$Name.stdout.txt") -RedirectStandardError (Join-Path $out "$Name.stderr.txt")
if (-not $p.WaitForExit($TimeoutSec * 1000)) { Stop-Process -Id $p.Id -Force; Write-Host "TIMEOUT after $TimeoutSec s (killed)" }
else { Write-Host ("finished in {0:N1}s" -f $sw.Elapsed.TotalSeconds) }
$log = Join-Path $out "$Name.log"
if (Test-Path $log) { Get-Content $log -Encoding UTF8 } else { Write-Host "(no $Name.log written)" }
