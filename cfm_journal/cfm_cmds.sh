#!/bin/bash
# cfm_cmds.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/cfm_ledger_autotemplate.py"

# Open a new short call
open_call() {
  local ACCOUNT=$1
  local SYMBOL=$2
  local CONTRACTS=$3
  local JUICE=$4
  local STRIKE=$5
  local EXPIRY=$6
  python3 "$PYTHON_SCRIPT" open --account "$ACCOUNT" --symbol "$SYMBOL" \
    --contracts "$CONTRACTS" --juice "$JUICE" --strike "$STRIKE" --expiry "$EXPIRY"
}

# Close an existing call
close_call() {
  local ACCOUNT=$1
  local SYMBOL=$2
  local CONTRACTS=$3
  local JUICE_BUYBACK=$4
  local STRIKE=$5
  local EXPIRY=$6
  python3 "$PYTHON_SCRIPT" close --account "$ACCOUNT" --symbol "$SYMBOL" \
    --contracts "$CONTRACTS" --juice-buyback "$JUICE_BUYBACK" --strike "$STRIKE" --expiry "$EXPIRY"
}
