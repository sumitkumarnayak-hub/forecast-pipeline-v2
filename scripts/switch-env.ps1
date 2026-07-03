# Switch env profile (run from repo root)
# Usage: .\scripts\switch-env.ps1 local | render | status | init
param(
    [Parameter(Position = 0)]
    [ValidateSet("local", "render", "status", "init")]
    [string]$Profile = "status"
)
$Root = Split-Path -Parent $PSScriptRoot
python "$Root\scripts\switch_env.py" $Profile
