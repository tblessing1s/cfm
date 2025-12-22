# cfm_cmds.ps1 - Interactive wrapper for CFM trading commands
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CfmCmdsScript = Join-Path $ScriptDir "cfm_cmds.sh"
$PythonScript = Join-Path $ScriptDir "cfm_ledger_autotemplate.py"
$CsvLogPath = Join-Path $ScriptDir "cfm_trades_log.csv"

# Function to prompt for input with default value
function Get-InputWithDefault {
    param(
        [string]$Prompt,
        [string]$DefaultValue = ""
    )
    
    if ($DefaultValue) {
        $input = Read-Host "$Prompt [$DefaultValue]"
        if ($input -eq "") { return $DefaultValue }
        return $input
    } else {
        return Read-Host $Prompt
    }
}

function Read-PositiveDouble {
    param(
        [string]$Prompt,
        [string]$DefaultValue = ""
    )

    do {
        $value = 0
        $input = Get-InputWithDefault $Prompt $DefaultValue
        if ([double]::TryParse($input, [ref]$value) -and $value -ge 0) {
            return $value
        }
        Write-Host "Please enter a valid non-negative number." -ForegroundColor Red
    } while ($true)
}

function Read-PositiveInt {
    param(
        [string]$Prompt,
        [string]$DefaultValue = "1"
    )

    do {
        $value = 0
        $input = Get-InputWithDefault $Prompt $DefaultValue
        if ([int]::TryParse($input, [ref]$value) -and $value -ge 1) {
            return $value
        }
        Write-Host "Please enter a valid positive integer." -ForegroundColor Red
    } while ($true)
}

function Read-JLAction {
    do {
        $choice = Read-Host "Action (Open/Close)"
        switch ($choice.ToLower()) {
            "open"  { return "Open" }
            "close" { return "Close" }
            default { Write-Host "Please enter Open or Close." -ForegroundColor Red }
        }
    } while ($true)
}

function Read-JLSide {
    do {
        $choice = Read-Host "Side (Call/Put)"
        switch ($choice.ToLower()) {
            "call" { return "Call" }
            "put"  { return "Put" }
            default { Write-Host "Please enter Call or Put." -ForegroundColor Red }
        }
    } while ($true)
}

# Function to display menu
function Show-Menu {
    Write-Host "=========================================="
    Write-Host "    CFM Trading Commands"
    Write-Host "=========================================="
    Write-Host "1. Open Call"
    Write-Host "2. Close Call"
    Write-Host "3. Log Juice Lever event"
    Write-Host "4. Show JL weekly totals"
    Write-Host "5. Sync Positions from Schwab"
    Write-Host "6. Sync Historical Trades from Schwab"
    Write-Host "7. Exit"
    Write-Host "=========================================="
}

# Function to get account selection
function Get-AccountSelection {
    Write-Host ""
    Write-Host "Select Account:" -ForegroundColor Cyan
    Write-Host "1. Travis"
    Write-Host "2. Christie"
    Write-Host ""
    
    do {
        $accountChoice = Read-Host "Select account (1-2)"
        switch ($accountChoice) {
            "1" { return "Travis" }
            "2" { return "Christie" }
            default { Write-Host "Invalid option. Please select 1 or 2." -ForegroundColor Red }
        }
    } while ($true)
}

# Function to get common parameters
function Get-CommonParams {
    $script:ACCOUNT = Get-AccountSelection
    $script:SYMBOL = Get-InputWithDefault "Symbol" "NVDA"
    $script:CONTRACTS = Get-InputWithDefault "Number of Contracts"
    $script:STRIKE = Get-InputWithDefault "Strike Price"
    $script:EXPIRY = Get-InputWithDefault "Expiry Date (YYYY-MM-DD)"
    $script:DATE = Get-InputWithDefault "Trade Date (YYYY-MM-DD, leave blank for today)"
    $script:TIME = Get-InputWithDefault "Trade Time (HH:MM, leave blank for current time)"
}

# Function to get premium and underlying price
function Get-PremiumAndUnderlying {
    Write-Host ""
    Write-Host "Premium and Underlying Price Input:" -ForegroundColor Cyan
    $script:PREMIUM = Get-InputWithDefault "Premium per contract"
    
    Write-Host ""
    Write-Host "How would you like to get the underlying price?" -ForegroundColor Cyan
    Write-Host "1. Enter underlying price manually"
    Write-Host "2. Auto-fetch from Yahoo Finance"
    Write-Host ""
    
    $underlyingMethod = Read-Host "Select option (1-2)"
    
    switch ($underlyingMethod) {
        "1" {
            $script:UNDERLYING = Get-InputWithDefault "Underlying stock price"
            $script:AUTO_PRICE = $false
        }
        "2" {
            $script:UNDERLYING = $null
            $script:AUTO_PRICE = $true
            Write-Host "Will auto-fetch underlying price from Yahoo Finance" -ForegroundColor Green
        }
        default {
            Write-Host "Invalid option. Using manual input method." -ForegroundColor Red
            $script:UNDERLYING = Get-InputWithDefault "Underlying stock price"
            $script:AUTO_PRICE = $false
        }
    }
}

# Function to open a call
function Open-CallInteractive {
    Write-Host ""
    Write-Host "=== OPEN CALL ===" -ForegroundColor Green
    Get-CommonParams
    Get-PremiumAndUnderlying
    
    Write-Host ""
    Write-Host "Parameters:" -ForegroundColor Yellow
    Write-Host "  Account: $ACCOUNT"
    Write-Host "  Symbol: $SYMBOL"
    Write-Host "  Contracts: $CONTRACTS"
    Write-Host "  Strike: $STRIKE"
    Write-Host "  Expiry: $EXPIRY"
    Write-Host "  Premium: $PREMIUM"
    if ($UNDERLYING) {
        Write-Host "  Underlying: $UNDERLYING"
    } else {
        Write-Host "  Underlying: Auto-fetch from Yahoo Finance"
    }
    if ($DATE) { Write-Host "  Date: $DATE" }
    if ($TIME) { Write-Host "  Time: $TIME" }
    Write-Host ""
    
    $confirm = Read-Host "Execute open_call? (y/n)"
    if ($confirm -match "^[Yy]$") {
        Write-Host "Executing open_call..." -ForegroundColor Green
        
        # Build the command with optional parameters
        $cmdArgs = @(
            "open",
            "--account", "$ACCOUNT",
            "--symbol", "$SYMBOL", 
            "--contracts", "$CONTRACTS",
            "--premium", "$PREMIUM",
            "--strike", "$STRIKE",
            "--expiry", "$EXPIRY"
        )
        
        if ($DATE) { $cmdArgs += @("--date", "$DATE") }
        if ($TIME) { $cmdArgs += @("--time", "$TIME") }
        if ($UNDERLYING) { $cmdArgs += @("--underlying", "$UNDERLYING") }
        if ($AUTO_PRICE) { $cmdArgs += "--auto-price" }
        $cmdArgs += "--csv-log"
        $cmdArgs += "$CsvLogPath"
        
        python $PythonScript @cmdArgs
        
        # Ask if user wants to create a close call
        Write-Host ""
        $createClose = Read-Host "Would you like to create a close call for this position? (y/n)"
        if ($createClose -match "^[Yy]$") {
            Write-Host ""
            Write-Host "=== CLOSE CALL (using same data) ===" -ForegroundColor Green
            Write-Host "Using the same data from the open call:"
            Write-Host "  Account: $ACCOUNT"
            Write-Host "  Symbol: $SYMBOL"
            Write-Host "  Contracts: $CONTRACTS"
            Write-Host "  Strike: $STRIKE"
            Write-Host "  Expiry: $EXPIRY"
            Write-Host ""
            
            Get-BuybackAndUnderlying
            
            Write-Host ""
            Write-Host "Close Call Parameters:" -ForegroundColor Yellow
            Write-Host "  Account: $ACCOUNT"
            Write-Host "  Symbol: $SYMBOL"
            Write-Host "  Contracts: $CONTRACTS"
            Write-Host "  Strike: $STRIKE"
            Write-Host "  Expiry: $EXPIRY"
            Write-Host "  Buyback: $BUYBACK"
            if ($UNDERLYING_CLOSE) {
                Write-Host "  Underlying: $UNDERLYING_CLOSE"
            } else {
                Write-Host "  Underlying: Auto-fetch from Yahoo Finance"
            }
            if ($DATE) { Write-Host "  Date: $DATE" }
            if ($TIME) { Write-Host "  Time: $TIME" }
            Write-Host ""
            
            $confirmClose = Read-Host "Execute close_call? (y/n)"
            if ($confirmClose -match "^[Yy]$") {
                Write-Host "Executing close_call..." -ForegroundColor Green
                
                # Build the close command with optional parameters
                $closeCmdArgs = @(
                    "close",
                    "--account", "$ACCOUNT",
                    "--symbol", "$SYMBOL",
                    "--contracts", "$CONTRACTS",
                    "--buyback", "$BUYBACK",
                    "--strike", "$STRIKE",
                    "--expiry", "$EXPIRY"
                )
                
                if ($DATE) { $closeCmdArgs += @("--date", "$DATE") }
                if ($TIME) { $closeCmdArgs += @("--time", "$TIME") }
                if ($UNDERLYING_CLOSE) { $closeCmdArgs += @("--underlying-close", "$UNDERLYING_CLOSE") }
                if ($AUTO_PRICE_CLOSE) { $closeCmdArgs += "--auto-price" }
                
                python $PythonScript @closeCmdArgs
            } else {
                Write-Host "Close call cancelled." -ForegroundColor Red
            }
        }
    } else {
        Write-Host "Operation cancelled." -ForegroundColor Red
    }
}

# Function to get buyback and underlying price for close
function Get-BuybackAndUnderlying {
    Write-Host ""
    Write-Host "Buyback and Underlying Price Input:" -ForegroundColor Cyan
    $script:BUYBACK = Get-InputWithDefault "Buyback premium per contract"
    
    Write-Host ""
    Write-Host "How would you like to get the underlying price?" -ForegroundColor Cyan
    Write-Host "1. Enter underlying price manually"
    Write-Host "2. Auto-fetch from Yahoo Finance"
    Write-Host ""
    
    $underlyingMethod = Read-Host "Select option (1-2)"
    
    switch ($underlyingMethod) {
        "1" {
            $script:UNDERLYING_CLOSE = Get-InputWithDefault "Underlying stock price"
            $script:AUTO_PRICE_CLOSE = $false
        }
        "2" {
            $script:UNDERLYING_CLOSE = $null
            $script:AUTO_PRICE_CLOSE = $true
            Write-Host "Will auto-fetch underlying price from Yahoo Finance" -ForegroundColor Green
        }
        default {
            Write-Host "Invalid option. Using manual input method." -ForegroundColor Red
            $script:UNDERLYING_CLOSE = Get-InputWithDefault "Underlying stock price"
            $script:AUTO_PRICE_CLOSE = $false
        }
    }
}

# Function to close a call
function Close-CallInteractive {
    Write-Host ""
    Write-Host "=== CLOSE CALL ===" -ForegroundColor Green
    Get-CommonParams
    Get-BuybackAndUnderlying
    
    Write-Host ""
    Write-Host "Parameters:" -ForegroundColor Yellow
    Write-Host "  Account: $ACCOUNT"
    Write-Host "  Symbol: $SYMBOL"
    Write-Host "  Contracts: $CONTRACTS"
    Write-Host "  Strike: $STRIKE"
    Write-Host "  Expiry: $EXPIRY"
    Write-Host "  Buyback: $BUYBACK"
    if ($UNDERLYING_CLOSE) {
        Write-Host "  Underlying: $UNDERLYING_CLOSE"
    } else {
        Write-Host "  Underlying: Auto-fetch from Yahoo Finance"
    }
    if ($DATE) { Write-Host "  Date: $DATE" }
    if ($TIME) { Write-Host "  Time: $TIME" }
    Write-Host ""
    
    $confirm = Read-Host "Execute close_call? (y/n)"
    if ($confirm -match "^[Yy]$") {
        Write-Host "Executing close_call..." -ForegroundColor Green
        
        # Build the command with optional parameters
        $cmdArgs = @(
            "close",
            "--account", "$ACCOUNT",
            "--symbol", "$SYMBOL",
            "--contracts", "$CONTRACTS",
            "--buyback", "$BUYBACK",
            "--strike", "$STRIKE",
            "--expiry", "$EXPIRY"
        )
        
        if ($DATE) { $cmdArgs += @("--date", "$DATE") }
        if ($TIME) { $cmdArgs += @("--time", "$TIME") }
        if ($UNDERLYING_CLOSE) { $cmdArgs += @("--underlying-close", "$UNDERLYING_CLOSE") }
        if ($AUTO_PRICE_CLOSE) { $cmdArgs += "--auto-price" }
        $cmdArgs += "--csv-log"
        $cmdArgs += "$CsvLogPath"
        
        python $PythonScript @cmdArgs
    } else {
        Write-Host "Operation cancelled." -ForegroundColor Red
    }
}

function Add-JLJuiceEvent {
    Write-Host ""
    Write-Host "=== JUICE LEVER EVENT ===" -ForegroundColor Cyan
    
    do {
        $ticker = Get-InputWithDefault "Ticker"
        if (-not $ticker) {
            Write-Host "Ticker is required." -ForegroundColor Red
        }
    } while (-not $ticker)

    $action = Read-JLAction
    $side = Read-JLSide
    $premium = Read-PositiveDouble "Premium per contract"
    $contracts = Read-PositiveInt "Contracts" "1"
    $strike = Read-PositiveDouble "Strike price"
    $expiry = Get-InputWithDefault "Expiry Date (YYYY-MM-DD, optional)"
    $date = Get-InputWithDefault "Date (YYYY-MM-DD, leave blank for today)"
    $time = Get-InputWithDefault "Time (HH:MM, leave blank for current time)"
    $autoPriceChoice = Read-Host "Fetch underlying price automatically? (y/n)"
    $useAutoPrice = $false
    $underlying = ""
    if ($autoPriceChoice -match "^[Yy]$") {
        $useAutoPrice = $true
        Write-Host "Will auto-fetch underlying price."
    } else {
        $underlying = Get-InputWithDefault "Underlying price (leave blank if unavailable)"
    }
    $note = Get-InputWithDefault "Note"
    $accountLabel = Get-InputWithDefault "Account label" "Juice Lever"

    Write-Host ""
    Write-Host "Parameters:" -ForegroundColor Yellow
    Write-Host "  Ticker: $ticker"
    Write-Host "  Action: $action"
    Write-Host "  Side:   $side"
    Write-Host "  Premium: $premium"
    Write-Host "  Contracts: $contracts"
    Write-Host "  Strike: $strike"
    if ($expiry) { Write-Host "  Expiry: $expiry" }
    if ($time) { Write-Host "  Time: $time" }
    Write-Host "  Account: $accountLabel"
    if ($date) { Write-Host "  Date: $date" }
    if ($time) { Write-Host "  Time: $time" }
    if ($autoPriceChoice -match "^[Yy]$") { Write-Host "  Underlying: auto-fetch" }
    elseif ($underlying) { Write-Host "  Underlying: $underlying" }
    if ($note) { Write-Host "  Note: $note" }
    Write-Host ""

    $confirm = Read-Host "Log this Juice Lever event? (y/n)"
    if ($confirm -match "^[Yy]$") {
        $cmdArgs = @(
            "jl",
            "--ticker", $ticker,
            "--action", $action,
            "--side", $side,
            "--strike", "$strike",
            "--premium", "$premium",
            "--contracts", "$contracts",
            "--account", "$accountLabel",
            "--csv-log", $CsvLogPath
        )
        if ($date) { $cmdArgs += @("--date", $date) }
        if ($time) { $cmdArgs += @("--time", $time) }
        if ($expiry) { $cmdArgs += @("--expiry", $expiry) }
        if ($underlying) { $cmdArgs += @("--underlying", $underlying) }
        if ($useAutoPrice) { $cmdArgs += "--auto-price" }
        if ($note) { $cmdArgs += @("--note", $note) }

        python $PythonScript @cmdArgs
    } else {
        Write-Host "Operation cancelled." -ForegroundColor Red
    }
}

function Show-JLWeeklyTotals {
    Write-Host ""
    Write-Host "=== JL WEEKLY TOTALS ===" -ForegroundColor Cyan
    python $PythonScript @("jl-summary", "--csv-log", $CsvLogPath)
}

# Function to sync from Schwab
function Sync-FromSchwab {
    Write-Host ""
    Write-Host "=== SYNC FROM SCHWAB ===" -ForegroundColor Green
    Write-Host "This will sync your current option positions from Schwab to your Excel ledger."
    Write-Host ""
    
    $script:ACCOUNT = Get-AccountSelection
    
    Write-Host ""
    Write-Host "Parameters:" -ForegroundColor Yellow
    Write-Host "  Account: $ACCOUNT"
    Write-Host "  Source: Schwab API"
    Write-Host ""
    
    $confirm = Read-Host "Proceed with sync? (y/n)"
    
    if ($confirm -eq "y" -or $confirm -eq "Y") {
        Write-Host "🔄 Syncing positions from Schwab..." -ForegroundColor Cyan
        
        $cmdArgs = @(
            "sync"
            "--account", $ACCOUNT
        )
        
        python $PythonScript @cmdArgs
    } else {
        Write-Host "Operation cancelled." -ForegroundColor Red
    }
}

# Function to sync historical trades from Schwab
function Sync-TradesFromSchwab {
    Write-Host ""
    Write-Host "=== SYNC HISTORICAL TRADES FROM SCHWAB ===" -ForegroundColor Green
    Write-Host "This will sync your historical option trades from Schwab with actual execution times."
    Write-Host ""
    
    $script:ACCOUNT = Get-AccountSelection
    
    Write-Host ""
    $daysBack = Get-InputWithDefault "Number of days to look back for trades" "30"
    
    Write-Host ""
    Write-Host "Parameters:" -ForegroundColor Yellow
    Write-Host "  Account: $ACCOUNT"
    Write-Host "  Days Back: $daysBack"
    Write-Host "  Source: Schwab API (with execution times)"
    Write-Host ""
    
    $confirm = Read-Host "Proceed with trade sync? (y/n)"
    
    if ($confirm -eq "y" -or $confirm -eq "Y") {
        Write-Host "🔄 Syncing historical trades from Schwab..." -ForegroundColor Cyan
        
        $cmdArgs = @(
            "sync-trades"
            "--account", $ACCOUNT
            "--days-back", $daysBack
        )
        
        python $PythonScript @cmdArgs
    } else {
        Write-Host "Operation cancelled." -ForegroundColor Red
    }
}

# Main menu loop
while ($true) {
    Show-Menu
    $choice = Read-Host "Select option (1-7)"
    
    switch ($choice) {
        "1" {
            Open-CallInteractive
        }
        "2" {
            Close-CallInteractive
        }
        "3" {
            Add-JLJuiceEvent
        }
        "4" {
            Show-JLWeeklyTotals
        }
        "5" {
            Sync-FromSchwab
        }
        "6" {
            Sync-TradesFromSchwab
        }
        "7" {
            Write-Host "Goodbye!" -ForegroundColor Green
            exit 0
        }
        default {
            Write-Host "Invalid option. Please select 1-7." -ForegroundColor Red
        }
    }
    
    Write-Host ""
    Read-Host "Press Enter to continue..."
    Clear-Host
}
