# cfm-ledger.ps1 - PowerShell-friendly wrapper for cfm_ledger_autotemplate.py
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Prefer python.exe but fall back to python3 if needed.
$pythonExeInfo = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonExeInfo) {
    $pythonExeInfo = Get-Command python3 -ErrorAction SilentlyContinue
}

if (-not $pythonExeInfo) {
    Write-Error "Python was not found. Please install Python 3 and ensure the executable is on PATH."
    exit 1
}

$pythonScript = Join-Path $ScriptDir "cfm_ledger_autotemplate.py"

$dispatchArgs = @()
if ($args.Count -eq 0) {
  $dispatchArgs += "batch"
}
elseif ($args[0].StartsWith("-")) {
    $dispatchArgs += "batch"
    $dispatchArgs += $args
}
else {
  $dispatchArgs += $args
}

# Always default to auto pricing on commands that support it unless user explicitly asked otherwise.
$autoPriceCommands = @("open","close","jl","batch")
if ($dispatchArgs.Count -gt 0) {
    $cmdName = $dispatchArgs[0]
    if ($autoPriceCommands -contains $cmdName) {
        if (-not ($dispatchArgs -contains "--auto-price")) {
            $dispatchArgs += "--auto-price"
        }
    }
}

# If the user didn't explicitly specify a ledger file, pick one based on the provided --account.
# Batch mode rows already dedupe per-account files, so we only run this when an account flag exists.
if (-not ($dispatchArgs -contains "--file")) {
    $accountValue = $null
    for ($i = 0; $i -lt $dispatchArgs.Count; $i++) {
        if ($dispatchArgs[$i] -ieq "--account" -and ($i + 1) -lt $dispatchArgs.Count) {
            $accountValue = $dispatchArgs[$i + 1]
            break
        }
    }

    if ($accountValue) {
        $accountFiles = @{
            "Christie" = "Juice_Ledger_Christie.xlsx"
            "Travis"   = "Juice_Ledger_Travis.xlsx"
        }
        if ($accountFiles.ContainsKey($accountValue)) {
            $dispatchArgs += "--file"
            $dispatchArgs += $accountFiles[$accountValue]
        }
    }
}

& $pythonExeInfo.Source $pythonScript @dispatchArgs
exit $LASTEXITCODE
