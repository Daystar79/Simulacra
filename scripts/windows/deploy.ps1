# Windows launcher — deploy Simulacra to a sibling book folder.
# AI agents on Windows: run this (or: python scripts/run.py deploy …).
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/windows/deploy.ps1 [target]

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

function Invoke-PythonScript {
    param([string]$ScriptPath, [string[]]$ScriptArgs)
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 $ScriptPath @ScriptArgs
        return $LASTEXITCODE
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python $ScriptPath @ScriptArgs
        return $LASTEXITCODE
    }
    if (Get-Command python3 -ErrorAction SilentlyContinue) {
        & python3 $ScriptPath @ScriptArgs
        return $LASTEXITCODE
    }
    throw "Python 3 not found on PATH. Install Python 3 or the Windows py launcher."
}

$script = Join-Path $Root "deploy_framework.py"
$code = Invoke-PythonScript -ScriptPath $script -ScriptArgs $args
exit $code
